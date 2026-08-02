"""Pure, provider-neutral P4-C evidence-consistency preflight.

This module validates supplied, scoped attestations.  It neither loads a secret nor
opens a file, starts a process, reads an environment variable, or contacts a network.
Its positive result is evidence metadata only and is never execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hyc_evaluation.local_pilot import SHA256_PATTERN, validate_public_safe_tree
from hyc_evaluation.schema import CanonicalDecimal, Identifier

_COST_CONTEXT = Context(
    prec=28, rounding=ROUND_HALF_EVEN, traps=[InvalidOperation, Overflow, Inexact, Rounded]
)
type EvidenceId = Annotated[str, Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")]
type PayloadField = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]
type Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
type EvidenceDimension = Literal[
    "residency",
    "retention",
    "deletion",
    "training",
    "subprocessors",
    "dpa",
    "security",
    "credentials",
    "pricing",
    "audit",
    "incident",
    "destination_intersection",
    "payload_redaction",
    "provider_approval",
]


class PreflightModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)


class ProviderScope(PreflightModel):
    provider: Identifier | None = None
    model: Identifier | None = None
    version: Identifier | None = None
    endpoint: Identifier | None = None
    region: Identifier | None = None

    def is_complete(self) -> bool:
        return all(
            getattr(self, name) is not None
            for name in ("provider", "model", "version", "endpoint", "region")
        )


def evidence_binding_sha256(
    *,
    attests_dimension: EvidenceDimension,
    reference: str,
    evidence_sha256: str,
    provider_scope: ProviderScope,
    account_scope_ref: str,
    verifier_reference: str,
    verified_on: date,
    valid_until: date,
) -> str:
    """Bind typed evidence metadata with compact, sorted UTF-8 JSON before hashing."""
    preimage = {
        "account_scope_ref": account_scope_ref,
        "attests_dimension": attests_dimension,
        "evidence_sha256": evidence_sha256,
        "provider_scope": provider_scope.model_dump(mode="json"),
        "reference": reference,
        "valid_until": valid_until.isoformat(),
        "verified_on": verified_on.isoformat(),
        "verifier_reference": verifier_reference,
    }
    return hashlib.sha256(
        json.dumps(preimage, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


class EvidenceMetadata(PreflightModel):
    attests_dimension: EvidenceDimension
    reference: EvidenceId
    evidence_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    provider_scope: ProviderScope
    account_scope_ref: EvidenceId
    verifier_reference: EvidenceId
    verified_on: date
    valid_until: date
    evidence_binding_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    status: Literal["CONFIRMED"]

    @model_validator(mode="after")
    def require_valid_window(self) -> EvidenceMetadata:
        if self.valid_until < self.verified_on:
            raise ValueError("evidence valid-until date cannot precede verified-on date")
        if self.evidence_binding_sha256 != evidence_binding_sha256(
            attests_dimension=self.attests_dimension,
            reference=self.reference,
            evidence_sha256=self.evidence_sha256,
            provider_scope=self.provider_scope,
            account_scope_ref=self.account_scope_ref,
            verifier_reference=self.verifier_reference,
            verified_on=self.verified_on,
            valid_until=self.valid_until,
        ):
            raise ValueError("evidence binding digest mismatch")
        return self


class PayloadPolicy(PreflightModel):
    redaction_method: Literal["FIELD_ALLOWLIST_REDACTION"]
    redaction_version: EvidenceId
    redaction_evidence: EvidenceMetadata
    allow_list: tuple[PayloadField, ...]
    forbidden_fields: tuple[PayloadField, ...]
    max_request_bytes: Annotated[int, Field(gt=0)]
    max_batch_size: Annotated[int, Field(gt=0)]
    max_rate_per_minute: Annotated[int, Field(gt=0)]
    max_concurrency: Annotated[int, Field(gt=0)]

    @field_validator("allow_list", "forbidden_fields", mode="before")
    @classmethod
    def freeze_and_order_fields(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != len(set(value)):
                raise ValueError("payload field policies must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def require_nonempty_disjoint_payload_policy(self) -> PayloadPolicy:
        if not self.allow_list:
            raise ValueError("payload allow-list must be non-empty")
        if set(self.allow_list).intersection(self.forbidden_fields):
            raise ValueError("payload allow-list and forbidden fields must be disjoint")
        return self


class ResidencyPolicy(PreflightModel):
    data_residency_decision: Literal["APPROVED_IN_REGION"]
    cross_border_transfer_decision: Literal["PROHIBITED"]
    evidence: EvidenceMetadata


class RetentionPolicy(PreflightModel):
    retention_days: Annotated[int, Field(gt=0)]
    retention_start_event: Literal["REQUEST_COMPLETED"]
    exceptional_retention: Literal["NOT_PERMITTED"]
    deletion_method: Literal["ATTESTED_DELETION"]
    deletion_sla_days: Annotated[int, Field(gt=0)]
    retention_evidence: EvidenceMetadata
    deletion_evidence: EvidenceMetadata


class TrainingPolicy(PreflightModel):
    training_use: Literal["PROHIBITED"]
    service_improvement_use: Literal["PROHIBITED"]
    opt_out_state: Literal["CONFIRMED"]
    evidence: EvidenceMetadata


class ThirdPartyPolicy(PreflightModel):
    subprocessors_reference: EvidenceId
    subprocessor_evidence: EvidenceMetadata
    dpa_evidence: EvidenceMetadata
    security_evidence: EvidenceMetadata


class CredentialPolicy(PreflightModel):
    credential_owner_ref: EvidenceId
    secret_reference: EvidenceId
    secret_reference_type: Literal["SECRET_STORE_REFERENCE"]
    rotation_period_days: Annotated[int, Field(gt=0, le=90)]
    least_privilege_scopes: tuple[EvidenceId, ...]
    revocation_reference: EvidenceId
    credential_evidence: EvidenceMetadata
    value_loaded: Literal[False] = False

    @field_validator("least_privilege_scopes", mode="before")
    @classmethod
    def freeze_scopes(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if not value or len(value) != len(set(value)):
                raise ValueError("least-privilege scopes must be non-empty and unique")
            return tuple(sorted(value))
        return value


class PricingPolicy(PreflightModel):
    pricing_version: EvidenceId
    effective_on: date
    currency: Currency
    unit_pricing_model: Literal["PER_REQUEST", "PER_PAGE"]
    per_unit_cost: CanonicalDecimal
    hard_budget_cap: CanonicalDecimal
    evidence: EvidenceMetadata


class AuditResponsePolicy(PreflightModel):
    audit_event_allow_list: tuple[PayloadField, ...]
    prohibited_log_fields: tuple[PayloadField, ...]
    raw_response_policy: Literal["NOT_STORED"]
    audit_retention_days: Annotated[int, Field(gt=0)]
    access_policy: Literal["ROLE_LIMITED"]
    deletion_policy: Literal["ATTESTED_DELETION"]
    evidence: EvidenceMetadata

    @field_validator("audit_event_allow_list", "prohibited_log_fields", mode="before")
    @classmethod
    def freeze_fields(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != len(set(value)):
                raise ValueError("audit field lists must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def require_audit_contract(self) -> AuditResponsePolicy:
        if not self.audit_event_allow_list:
            raise ValueError("audit event allow-list must be non-empty")
        if set(self.audit_event_allow_list).intersection(self.prohibited_log_fields):
            raise ValueError("audit allow-list and prohibited log fields must be disjoint")
        return self


class IncidentPolicy(PreflightModel):
    incident_owner_ref: EvidenceId
    escalation_reference: EvidenceId
    containment_control: Literal["KILL_SWITCH"]
    revocation_control: Literal["CREDENTIAL_REVOCATION"]
    evidence: EvidenceMetadata


class DestinationPolicy(PreflightModel):
    approved_destination: EvidenceId
    p4b_packet_id: EvidenceId
    pilot_manifest_id: EvidenceId
    pilot_manifest_version: Literal["hyc.local-pilot-manifest.v1"]
    intersection_evidence: EvidenceMetadata


class ProviderApproval(PreflightModel):
    approved_scope: ProviderScope
    approver_reference: EvidenceId
    approval_date: date
    approval_evidence: EvidenceMetadata
    final_status: Literal["APPROVED"]


class ProviderPreflightPolicy(PreflightModel):
    policy_schema_version: Literal["hyc.provider-preflight-policy.v2"] = (
        "hyc.provider-preflight-policy.v2"
    )
    assessment_date: date | None = None
    external_execution_enabled: Literal[False] = False
    provider_scope: ProviderScope = Field(default_factory=ProviderScope)
    account_scope_ref: EvidenceId | None = None
    residency: ResidencyPolicy | None = None
    retention: RetentionPolicy | None = None
    training: TrainingPolicy | None = None
    third_party: ThirdPartyPolicy | None = None
    credentials: CredentialPolicy | None = None
    pricing: PricingPolicy | None = None
    audit: AuditResponsePolicy | None = None
    incident: IncidentPolicy | None = None
    destination: DestinationPolicy | None = None
    payload_policy: PayloadPolicy | None = None
    provider_approval: ProviderApproval | None = None

    @model_validator(mode="after")
    def bind_distinct_dimension_evidence(self) -> ProviderPreflightPolicy:
        """Bind each present evidence slot to its exact control dimension.

        A deliberately incomplete policy remains constructible so evaluation can
        return its fail-closed required-dimension decision. Any supplied evidence,
        however, is still checked against its slot; a complete policy therefore
        always has all fourteen distinct, dimension-bound attestations.
        """
        slots: tuple[tuple[EvidenceDimension, EvidenceMetadata | None], ...] = (
            ("residency", self.residency.evidence if self.residency else None),
            ("retention", self.retention.retention_evidence if self.retention else None),
            ("deletion", self.retention.deletion_evidence if self.retention else None),
            ("training", self.training.evidence if self.training else None),
            ("subprocessors", self.third_party.subprocessor_evidence if self.third_party else None),
            ("dpa", self.third_party.dpa_evidence if self.third_party else None),
            ("security", self.third_party.security_evidence if self.third_party else None),
            ("credentials", self.credentials.credential_evidence if self.credentials else None),
            ("pricing", self.pricing.evidence if self.pricing else None),
            ("audit", self.audit.evidence if self.audit else None),
            ("incident", self.incident.evidence if self.incident else None),
            (
                "destination_intersection",
                self.destination.intersection_evidence if self.destination else None,
            ),
            (
                "payload_redaction",
                self.payload_policy.redaction_evidence if self.payload_policy else None,
            ),
            (
                "provider_approval",
                self.provider_approval.approval_evidence if self.provider_approval else None,
            ),
        )
        evidence = tuple(item for _, item in slots if item is not None)
        if any(item.attests_dimension != expected for expected, item in slots if item is not None):
            raise ValueError("provider evidence attests a different dimension than its slot")
        for values in (
            tuple(item.reference for item in evidence),
            tuple(item.evidence_sha256 for item in evidence),
            tuple(item.evidence_binding_sha256 for item in evidence),
        ):
            if len(values) != len(set(values)):
                raise ValueError(
                    "provider evidence references and digests must be globally distinct"
                )
        return self


class SyntheticDryRunDescriptor(PreflightModel):
    descriptor_schema_version: Literal["hyc.synthetic-dry-run-descriptor.v2"]
    scope: ProviderScope
    account_scope_ref: EvidenceId
    approved_destination: EvidenceId
    p4b_packet_id: EvidenceId
    pilot_manifest_id: EvidenceId
    pilot_manifest_version: Literal["hyc.local-pilot-manifest.v1"]
    payload_fields: tuple[PayloadField, ...]
    request_payload_bytes: Annotated[int, Field(gt=0)]
    batch_size: Annotated[int, Field(gt=0)]
    requested_rate_per_minute: int | None = None
    requested_concurrency: int | None = None
    billable_unit_count: int | None
    currency: Currency | None
    unit_pricing_model: Literal["PER_REQUEST", "PER_PAGE"]
    per_unit_cost: CanonicalDecimal | None
    caller_projected_total: CanonicalDecimal | None = None
    provenance_marker: Literal["generated-non-sensitive-synthetic"]

    @field_validator("payload_fields", mode="before")
    @classmethod
    def freeze_fields(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if not value or len(value) != len(set(value)):
                raise ValueError("request payload fields must be non-empty and unique")
            return tuple(sorted(value))
        return value


type PreflightReasonCode = Literal[
    "ACCOUNT_SCOPE_ABSENT_OR_MISMATCH",
    "APPROVAL_DATE_INVALID",
    "APPROVAL_EVIDENCE_INVALID",
    "APPROVED_DESTINATION_MISMATCH",
    "APPROVED_SCOPE_MISMATCH",
    "EVIDENCE_SCOPE_OR_DATE_INVALID",
    "HARD_BUDGET_EXCEEDED",
    "PAYLOAD_CONTRACT_INVALID",
    "PILOT_MANIFEST_INTERSECTION_MISMATCH",
    "PRICING_CONTRACT_INVALID",
    "PROJECTED_COST_ARITHMETIC_INVALID",
    "PROJECTED_COST_MISMATCH",
    "REQUEST_BILLABLE_COUNT_INVALID",
    "REQUEST_CURRENCY_MISMATCH",
    "REQUEST_CONCURRENCY_EXCEEDED",
    "REQUEST_CONCURRENCY_INVALID",
    "REQUEST_RATE_PER_MINUTE_EXCEEDED",
    "REQUEST_RATE_PER_MINUTE_INVALID",
    "REQUEST_UNIT_COST_MISMATCH",
    "REQUEST_UNIT_COST_INVALID",
    "REQUEST_UNIT_PRICING_MODEL_MISMATCH",
    "REQUIRED_DIMENSION_ABSENT",
    "SCOPE_ABSENT_OR_MISMATCH",
]


class PreflightDecision(PreflightModel):
    decision_schema_version: Literal["hyc.provider-preflight-decision.v2"]
    status: Literal["DENY", "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR"]
    reason_codes: tuple[PreflightReasonCode, ...]
    authorization_effect: Literal["EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY"]
    side_effects: Literal["NONE"]
    external_execution_performed: Literal[False]
    manual_fallback: Literal["HUMAN_REVIEW"]

    @field_validator("reason_codes", mode="before")
    @classmethod
    def freeze_reasons(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != len(set(value)):
                raise ValueError("preflight reason codes must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def bind_status_to_reasons(self) -> PreflightDecision:
        if (self.status == "DENY") != bool(self.reason_codes):
            raise ValueError("preflight DENY status must exactly reflect reason codes")
        # These fields are typed literals, so safe-tree checks cannot be bypassed by
        # arbitrary strings masquerading as a public status/reason.
        validate_public_safe_tree(
            {
                "decision_schema_version": self.decision_schema_version,
                "status": self.status,
                "authorization_effect": self.authorization_effect,
                "side_effects": self.side_effects,
                "manual_fallback": self.manual_fallback,
                "reason_codes": self.reason_codes,
            }
        )
        return self


class PublicLocalPilotReport(PreflightModel):
    aggregate_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    cohort_size_bucket: Literal["LT_3", "3_TO_9", "10_PLUS"]
    empty_status: Literal[
        "INSUFFICIENT_ELIGIBLE_CORPUS",
        "HUMAN_EVIDENCE_REQUIRED",
        "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY",
    ]
    small_cohort_suppression_verified: bool


class PublicAP02Report(PreflightModel):
    complete_status: Literal["DENY", "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR"]
    default_deny_reason_count: Annotated[int, Field(ge=0)]
    default_status: Literal["DENY"]
    execution_effect: Literal["EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY"]
    side_effects: Literal["NONE"]


class PublicPreflightReport(PreflightModel):
    """Strict safe model for the CLI's deliberately coarse public stdout."""

    check_schema_version: Literal["hyc.synthetic-p4-preflight-check.v2"]
    markers: tuple[
        Literal["GENERATED_SYNTHETIC_EVIDENCE"],
        Literal["HUMAN_REVIEW_REQUIRED"],
        Literal["NON_REPRESENTATIVE"],
        Literal["NOT_A_RELEASE_GATE"],
    ]
    local_pilot: PublicLocalPilotReport
    ap02: PublicAP02Report

    @model_validator(mode="after")
    def validate_public_report(self) -> PublicPreflightReport:
        rendered = self.model_dump(mode="json")
        # The aggregate digest and all nested public values are structurally
        # constrained by the strict submodels. Validate the remaining public tree
        # through the generic protected-material guard.
        rendered["local_pilot"].pop("aggregate_sha256")
        validate_public_safe_tree(rendered)
        return self


def _same_scope(left: ProviderScope, right: ProviderScope) -> bool:
    return left.is_complete() and right.is_complete() and left == right


def _valid_evidence(evidence: EvidenceMetadata, policy: ProviderPreflightPolicy) -> bool:
    return (
        policy.assessment_date is not None
        and policy.account_scope_ref is not None
        and evidence.status == "CONFIRMED"
        and _same_scope(evidence.provider_scope, policy.provider_scope)
        and evidence.account_scope_ref == policy.account_scope_ref
        and evidence.verified_on <= policy.assessment_date <= evidence.valid_until
    )


def _calculate_projected_total(count: int, unit_cost: Decimal) -> Decimal | None:
    try:
        with localcontext(_COST_CONTEXT):
            return count * unit_cost
    except (InvalidOperation, Overflow, Inexact, Rounded):
        return None


def evaluate_provider_preflight(
    policy: ProviderPreflightPolicy, request: SyntheticDryRunDescriptor
) -> PreflightDecision:
    """Fail closed on missing, stale, foreign, contradictory, or over-budget metadata."""
    reasons: set[PreflightReasonCode] = set()
    if not _same_scope(policy.provider_scope, request.scope):
        reasons.add("SCOPE_ABSENT_OR_MISMATCH")
    if policy.account_scope_ref is None or policy.account_scope_ref != request.account_scope_ref:
        reasons.add("ACCOUNT_SCOPE_ABSENT_OR_MISMATCH")
    required = (
        policy.residency,
        policy.retention,
        policy.training,
        policy.third_party,
        policy.credentials,
        policy.pricing,
        policy.audit,
        policy.incident,
        policy.destination,
        policy.payload_policy,
        policy.provider_approval,
    )
    if any(item is None for item in required) or policy.assessment_date is None:
        reasons.add("REQUIRED_DIMENSION_ABSENT")
    if any(item is None for item in required):
        return _decision(reasons)
    assert (
        policy.residency
        and policy.retention
        and policy.training
        and policy.third_party
        and policy.credentials
    )
    assert (
        policy.pricing
        and policy.audit
        and policy.incident
        and policy.destination
        and policy.payload_policy
        and policy.provider_approval
    )
    evidence_groups: tuple[tuple[EvidenceMetadata, ...], ...] = (
        (policy.residency.evidence,),
        (policy.retention.retention_evidence, policy.retention.deletion_evidence),
        (policy.training.evidence,),
        (
            policy.third_party.subprocessor_evidence,
            policy.third_party.dpa_evidence,
            policy.third_party.security_evidence,
        ),
        (policy.credentials.credential_evidence,),
        (policy.pricing.evidence,),
        (policy.audit.evidence,),
        (policy.incident.evidence,),
        (policy.destination.intersection_evidence,),
        (policy.payload_policy.redaction_evidence,),
        (policy.provider_approval.approval_evidence,),
    )
    if any(not _valid_evidence(item, policy) for group in evidence_groups for item in group):
        reasons.add("EVIDENCE_SCOPE_OR_DATE_INVALID")
    if policy.retention.retention_start_event != "REQUEST_COMPLETED":
        raise AssertionError("validated retention policy must use REQUEST_COMPLETED")
    if (
        policy.pricing.per_unit_cost <= 0
        or policy.pricing.hard_budget_cap <= 0
        or policy.pricing.effective_on > (policy.assessment_date or date.min)
    ):
        reasons.add("PRICING_CONTRACT_INVALID")
    if policy.destination.approved_destination != request.approved_destination:
        reasons.add("APPROVED_DESTINATION_MISMATCH")
    if (
        policy.destination.p4b_packet_id != request.p4b_packet_id
        or policy.destination.pilot_manifest_id != request.pilot_manifest_id
        or policy.destination.pilot_manifest_version != request.pilot_manifest_version
    ):
        reasons.add("PILOT_MANIFEST_INTERSECTION_MISMATCH")
    payload = policy.payload_policy
    if (
        not request.payload_fields
        or request.request_payload_bytes > payload.max_request_bytes
        or request.batch_size > payload.max_batch_size
        or not set(request.payload_fields).issubset(payload.allow_list)
        or set(request.payload_fields).intersection(payload.forbidden_fields)
    ):
        reasons.add("PAYLOAD_CONTRACT_INVALID")
    if request.requested_rate_per_minute is None or request.requested_rate_per_minute <= 0:
        reasons.add("REQUEST_RATE_PER_MINUTE_INVALID")
    elif request.requested_rate_per_minute > payload.max_rate_per_minute:
        reasons.add("REQUEST_RATE_PER_MINUTE_EXCEEDED")
    if request.requested_concurrency is None or request.requested_concurrency <= 0:
        reasons.add("REQUEST_CONCURRENCY_INVALID")
    elif request.requested_concurrency > payload.max_concurrency:
        reasons.add("REQUEST_CONCURRENCY_EXCEEDED")
    approval = policy.provider_approval
    if not _same_scope(approval.approved_scope, policy.provider_scope):
        reasons.add("APPROVED_SCOPE_MISMATCH")
    if policy.assessment_date is None or approval.approval_date > policy.assessment_date:
        reasons.add("APPROVAL_DATE_INVALID")
    if not _valid_evidence(approval.approval_evidence, policy):
        reasons.add("APPROVAL_EVIDENCE_INVALID")
    if request.billable_unit_count is None or request.billable_unit_count <= 0:
        reasons.add("REQUEST_BILLABLE_COUNT_INVALID")
    if request.currency is None or request.currency != policy.pricing.currency:
        reasons.add("REQUEST_CURRENCY_MISMATCH")
    if request.unit_pricing_model != policy.pricing.unit_pricing_model:
        reasons.add("REQUEST_UNIT_PRICING_MODEL_MISMATCH")
    if request.per_unit_cost is None or request.per_unit_cost <= 0:
        reasons.add("REQUEST_UNIT_COST_INVALID")
    elif request.per_unit_cost != policy.pricing.per_unit_cost:
        reasons.add("REQUEST_UNIT_COST_MISMATCH")
    if (
        request.billable_unit_count is not None
        and request.billable_unit_count > 0
        and policy.pricing.per_unit_cost > 0
    ):
        projected = _calculate_projected_total(
            request.billable_unit_count, policy.pricing.per_unit_cost
        )
        if projected is None:
            reasons.add("PROJECTED_COST_ARITHMETIC_INVALID")
        else:
            if (
                request.caller_projected_total is not None
                and request.caller_projected_total != projected
            ):
                reasons.add("PROJECTED_COST_MISMATCH")
            if (
                request.currency == policy.pricing.currency
                and projected > policy.pricing.hard_budget_cap
            ):
                reasons.add("HARD_BUDGET_EXCEEDED")
    return _decision(reasons)


def _decision(reasons: set[PreflightReasonCode]) -> PreflightDecision:
    ordered = tuple(sorted(reasons))
    return PreflightDecision(
        decision_schema_version="hyc.provider-preflight-decision.v2",
        status="DENY" if ordered else "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR",
        reason_codes=ordered,
        authorization_effect="EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY",
        side_effects="NONE",
        external_execution_performed=False,
        manual_fallback="HUMAN_REVIEW",
    )


__all__ = [
    "EvidenceMetadata",
    "PreflightDecision",
    "ProviderPreflightPolicy",
    "ProviderScope",
    "PublicAP02Report",
    "PublicLocalPilotReport",
    "PublicPreflightReport",
    "SyntheticDryRunDescriptor",
    "evaluate_provider_preflight",
    "evidence_binding_sha256",
]
