from __future__ import annotations

import ast
import builtins
import importlib.util
import io
import os
import socket
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from hyc_evaluation.local_pilot import validate_public_safe_tree
from hyc_evaluation.preflight import (
    PreflightDecision,
    PreflightReasonCode,
    ProviderPreflightPolicy,
    ProviderScope,
    PublicPreflightReport,
    SyntheticDryRunDescriptor,
    evaluate_provider_preflight,
    evidence_binding_sha256,
)


def scope_payload() -> dict[str, object]:
    return {
        "provider": "provider-scope-001",
        "model": "model-scope-001",
        "version": "version-scope-001",
        "endpoint": "endpoint-scope-001",
        "region": "region-scope-001",
    }


def evidence(
    index: int,
    *,
    attests_dimension: str = "residency",
    scope: dict[str, object] | None = None,
    account: str = "account-scope-001",
    verified: date = date(2026, 8, 1),
    valid: date = date(2026, 8, 3),
) -> dict[str, object]:
    reference, digest, verifier = (
        f"evidence-ref-{index:03d}",
        f"{index:064x}",
        f"verifier-ref-{index:03d}",
    )
    provider_scope = ProviderScope.model_validate(scope or scope_payload())
    return {
        "reference": reference,
        "attests_dimension": attests_dimension,
        "evidence_sha256": digest,
        "provider_scope": provider_scope.model_dump(),
        "account_scope_ref": account,
        "verifier_reference": verifier,
        "verified_on": verified,
        "valid_until": valid,
        "evidence_binding_sha256": evidence_binding_sha256(
            attests_dimension=attests_dimension,  # type: ignore[arg-type]
            reference=reference,
            evidence_sha256=digest,
            provider_scope=provider_scope,
            account_scope_ref=account,
            verifier_reference=verifier,
            verified_on=verified,
            valid_until=valid,
        ),
        "status": "CONFIRMED",
    }


def policy_payload() -> dict[str, object]:
    return {
        "policy_schema_version": "hyc.provider-preflight-policy.v2",
        "assessment_date": date(2026, 8, 2),
        "external_execution_enabled": False,
        "provider_scope": scope_payload(),
        "account_scope_ref": "account-scope-001",
        "residency": {
            "data_residency_decision": "APPROVED_IN_REGION",
            "cross_border_transfer_decision": "PROHIBITED",
            "evidence": evidence(1, attests_dimension="residency"),
        },
        "retention": {
            "retention_days": 30,
            "retention_start_event": "REQUEST_COMPLETED",
            "exceptional_retention": "NOT_PERMITTED",
            "deletion_method": "ATTESTED_DELETION",
            "deletion_sla_days": 7,
            "retention_evidence": evidence(2, attests_dimension="retention"),
            "deletion_evidence": evidence(3, attests_dimension="deletion"),
        },
        "training": {
            "training_use": "PROHIBITED",
            "service_improvement_use": "PROHIBITED",
            "opt_out_state": "CONFIRMED",
            "evidence": evidence(4, attests_dimension="training"),
        },
        "third_party": {
            "subprocessors_reference": "subprocessors-ref-001",
            "subprocessor_evidence": evidence(5, attests_dimension="subprocessors"),
            "dpa_evidence": evidence(6, attests_dimension="dpa"),
            "security_evidence": evidence(7, attests_dimension="security"),
        },
        "credentials": {
            "credential_owner_ref": "credential-owner-001",
            "secret_reference": "secret-reference-001",
            "secret_reference_type": "SECRET_STORE_REFERENCE",
            "rotation_period_days": 30,
            "least_privilege_scopes": ["scope-submit-001"],
            "revocation_reference": "revocation-reference-001",
            "credential_evidence": evidence(8, attests_dimension="credentials"),
            "value_loaded": False,
        },
        "pricing": {
            "pricing_version": "pricing-version-001",
            "effective_on": date(2026, 8, 1),
            "currency": "USD",
            "unit_pricing_model": "PER_REQUEST",
            "per_unit_cost": "1.50",
            "hard_budget_cap": "10.00",
            "evidence": evidence(9, attests_dimension="pricing"),
        },
        "audit": {
            "audit_event_allow_list": ["event_type"],
            "prohibited_log_fields": ["raw_ocr"],
            "raw_response_policy": "NOT_STORED",
            "audit_retention_days": 30,
            "access_policy": "ROLE_LIMITED",
            "deletion_policy": "ATTESTED_DELETION",
            "evidence": evidence(10, attests_dimension="audit"),
        },
        "incident": {
            "incident_owner_ref": "incident-owner-001",
            "escalation_reference": "escalation-reference-001",
            "containment_control": "KILL_SWITCH",
            "revocation_control": "CREDENTIAL_REVOCATION",
            "evidence": evidence(11, attests_dimension="incident"),
        },
        "destination": {
            "approved_destination": "destination-001",
            "p4b_packet_id": "p4b-packet-001",
            "pilot_manifest_id": "pilot-manifest-001",
            "pilot_manifest_version": "hyc.local-pilot-manifest.v1",
            "intersection_evidence": evidence(12, attests_dimension="destination_intersection"),
        },
        "payload_policy": {
            "redaction_method": "FIELD_ALLOWLIST_REDACTION",
            "redaction_version": "redaction-version-001",
            "redaction_evidence": evidence(13, attests_dimension="payload_redaction"),
            "allow_list": ["document_kind", "synthetic_case_id"],
            "forbidden_fields": ["raw_ocr"],
            "max_request_bytes": 1024,
            "max_batch_size": 2,
            "max_rate_per_minute": 4,
            "max_concurrency": 1,
        },
        "provider_approval": {
            "approved_scope": scope_payload(),
            "approver_reference": "approver-reference-001",
            "approval_date": date(2026, 8, 2),
            "approval_evidence": evidence(14, attests_dimension="provider_approval"),
            "final_status": "APPROVED",
        },
    }


def request_payload() -> dict[str, object]:
    return {
        "descriptor_schema_version": "hyc.synthetic-dry-run-descriptor.v2",
        "scope": scope_payload(),
        "account_scope_ref": "account-scope-001",
        "approved_destination": "destination-001",
        "p4b_packet_id": "p4b-packet-001",
        "pilot_manifest_id": "pilot-manifest-001",
        "pilot_manifest_version": "hyc.local-pilot-manifest.v1",
        "payload_fields": ["document_kind", "synthetic_case_id"],
        "request_payload_bytes": 512,
        "batch_size": 2,
        "requested_rate_per_minute": 4,
        "requested_concurrency": 1,
        "billable_unit_count": 2,
        "currency": "USD",
        "unit_pricing_model": "PER_REQUEST",
        "per_unit_cost": "1.50",
        "caller_projected_total": "3.00",
        "provenance_marker": "generated-non-sensitive-synthetic",
    }


def decision(
    policy: dict[str, object] | None = None, request: dict[str, object] | None = None
) -> PreflightDecision:
    return evaluate_provider_preflight(
        ProviderPreflightPolicy.model_validate(policy or policy_payload()),
        SyntheticDryRunDescriptor.model_validate(request or request_payload()),
    )


def test_complete_synthetic_policy_is_structurally_evidential_only() -> None:
    result = decision()
    assert result.status == "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR"
    assert result.reason_codes == ()
    assert result.authorization_effect == "EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY"
    assert result.side_effects == "NONE" and result.external_execution_performed is False


def test_defaults_and_each_required_typed_dimension_fail_closed() -> None:
    result = evaluate_provider_preflight(
        ProviderPreflightPolicy(), SyntheticDryRunDescriptor.model_validate(request_payload())
    )
    assert result.status == "DENY" and "REQUIRED_DIMENSION_ABSENT" in result.reason_codes
    for field in (
        "residency",
        "retention",
        "training",
        "third_party",
        "credentials",
        "pricing",
        "audit",
        "incident",
        "destination",
        "payload_policy",
        "provider_approval",
    ):
        payload = policy_payload()
        payload[field] = None
        assert "REQUIRED_DIMENSION_ABSENT" in decision(payload).reason_codes


@pytest.mark.parametrize(
    "path",
    [
        ("residency", "evidence"),
        ("retention", "retention_evidence"),
        ("retention", "deletion_evidence"),
        ("training", "evidence"),
        ("third_party", "subprocessor_evidence"),
        ("third_party", "dpa_evidence"),
        ("third_party", "security_evidence"),
        ("credentials", "credential_evidence"),
        ("pricing", "evidence"),
        ("audit", "evidence"),
        ("incident", "evidence"),
        ("destination", "intersection_evidence"),
        ("payload_policy", "redaction_evidence"),
        ("provider_approval", "approval_evidence"),
    ],
)
def test_every_governance_control_and_approval_evidence_is_scope_account_and_date_bound(
    path: tuple[str, str],
) -> None:
    payload = policy_payload()
    item = payload[path[0]][path[1]]  # type: ignore[index]
    item["account_scope_ref"] = "foreign-account-001"  # type: ignore[index]
    # Rebinds the altered data so this exercises scope binding, not merely hash syntax.
    dimensions = {
        ("residency", "evidence"): "residency",
        ("retention", "retention_evidence"): "retention",
        ("retention", "deletion_evidence"): "deletion",
        ("training", "evidence"): "training",
        ("third_party", "subprocessor_evidence"): "subprocessors",
        ("third_party", "dpa_evidence"): "dpa",
        ("third_party", "security_evidence"): "security",
        ("credentials", "credential_evidence"): "credentials",
        ("pricing", "evidence"): "pricing",
        ("audit", "evidence"): "audit",
        ("incident", "evidence"): "incident",
        ("destination", "intersection_evidence"): "destination_intersection",
        ("payload_policy", "redaction_evidence"): "payload_redaction",
        ("provider_approval", "approval_evidence"): "provider_approval",
    }
    item.update(  # type: ignore[union-attr]
        evidence(90, attests_dimension=dimensions[path], account="foreign-account-001")
    )
    assert "EVIDENCE_SCOPE_OR_DATE_INVALID" in decision(payload).reason_codes


def test_evidence_is_distinct_and_bound_to_each_of_the_fourteen_slots() -> None:
    payload = policy_payload()
    slots = (
        ("residency", "evidence"),
        ("retention", "retention_evidence"),
        ("retention", "deletion_evidence"),
        ("training", "evidence"),
        ("third_party", "subprocessor_evidence"),
        ("third_party", "dpa_evidence"),
        ("third_party", "security_evidence"),
        ("credentials", "credential_evidence"),
        ("pricing", "evidence"),
        ("audit", "evidence"),
        ("incident", "evidence"),
        ("destination", "intersection_evidence"),
        ("payload_policy", "redaction_evidence"),
        ("provider_approval", "approval_evidence"),
    )
    evidence_items = [payload[group][field] for group, field in slots]  # type: ignore[index]
    assert len(evidence_items) == 14
    assert len({item["reference"] for item in evidence_items}) == 14  # type: ignore[index]
    assert len({item["evidence_sha256"] for item in evidence_items}) == 14  # type: ignore[index]
    assert len({item["evidence_binding_sha256"] for item in evidence_items}) == 14  # type: ignore[index]

    payload = policy_payload()
    payload["retention"]["retention_evidence"] = evidence(2, attests_dimension="deletion")  # type: ignore[index]
    with pytest.raises(ValidationError, match="different dimension"):
        ProviderPreflightPolicy.model_validate(payload)

    for field in ("reference", "evidence_sha256"):
        payload = policy_payload()
        target = payload["training"]["evidence"]  # type: ignore[index]
        target[field] = payload["residency"]["evidence"][field]  # type: ignore[index]
        target["evidence_binding_sha256"] = evidence_binding_sha256(
            attests_dimension="training",
            reference=target["reference"],
            evidence_sha256=target["evidence_sha256"],
            provider_scope=ProviderScope.model_validate(target["provider_scope"]),
            account_scope_ref=target["account_scope_ref"],
            verifier_reference=target["verifier_reference"],
            verified_on=target["verified_on"],
            valid_until=target["valid_until"],
        )
        with pytest.raises(ValidationError, match="globally distinct"):
            ProviderPreflightPolicy.model_validate(payload)

    payload = policy_payload()
    payload["training"]["evidence"]["evidence_binding_sha256"] = payload["residency"]["evidence"][  # type: ignore[index]
        "evidence_binding_sha256"
    ]
    with pytest.raises(ValidationError, match="binding"):
        ProviderPreflightPolicy.model_validate(payload)


def test_evidence_digest_binding_tampering_swapping_stale_and_future_fail_closed() -> None:
    payload = policy_payload()
    payload["residency"]["evidence"]["evidence_sha256"] = "f" * 64  # type: ignore[index]
    with pytest.raises(ValidationError, match="binding"):
        ProviderPreflightPolicy.model_validate(payload)
    payload = policy_payload()
    payload["residency"]["evidence"] = evidence(
        91, verified=date(2026, 7, 1), valid=date(2026, 8, 1)
    )  # type: ignore[index]
    assert "EVIDENCE_SCOPE_OR_DATE_INVALID" in decision(payload).reason_codes
    payload = policy_payload()
    payload["residency"]["evidence"] = evidence(
        92, verified=date(2026, 8, 3), valid=date(2026, 8, 4)
    )  # type: ignore[index]
    assert "EVIDENCE_SCOPE_OR_DATE_INVALID" in decision(payload).reason_codes


def test_exact_scope_account_destination_and_intersection_mismatches_deny() -> None:
    request = request_payload()
    request["scope"]["region"] = "foreign-region-001"  # type: ignore[index]
    assert "SCOPE_ABSENT_OR_MISMATCH" in decision(request=request).reason_codes
    request = request_payload()
    request["account_scope_ref"] = "foreign-account-001"
    assert "ACCOUNT_SCOPE_ABSENT_OR_MISMATCH" in decision(request=request).reason_codes
    request = request_payload()
    request["approved_destination"] = "foreign-destination-001"
    assert "APPROVED_DESTINATION_MISMATCH" in decision(request=request).reason_codes
    request = request_payload()
    request["p4b_packet_id"] = "foreign-packet-001"
    assert "PILOT_MANIFEST_INTERSECTION_MISMATCH" in decision(request=request).reason_codes


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("billable_unit_count", None, "REQUEST_BILLABLE_COUNT_INVALID"),
        ("billable_unit_count", 0, "REQUEST_BILLABLE_COUNT_INVALID"),
        ("per_unit_cost", None, "REQUEST_UNIT_COST_INVALID"),
        ("per_unit_cost", "0", "REQUEST_UNIT_COST_INVALID"),
        ("currency", None, "REQUEST_CURRENCY_MISMATCH"),
        ("currency", "KRW", "REQUEST_CURRENCY_MISMATCH"),
        ("per_unit_cost", "1.49", "REQUEST_UNIT_COST_MISMATCH"),
        ("per_unit_cost", "5.01", "REQUEST_UNIT_COST_MISMATCH"),
        ("caller_projected_total", "3.01", "PROJECTED_COST_MISMATCH"),
    ],
)
def test_cost_is_explicit_decimal_count_times_unit_cost_in_same_currency(
    field: str, value: object, reason: str
) -> None:
    request = request_payload()
    request[field] = value
    assert reason in decision(request=request).reason_codes


def test_cost_context_overflow_and_policy_currency_or_effective_date_fail_closed() -> None:
    request = request_payload()
    request["billable_unit_count"] = 10**100
    assert "PROJECTED_COST_ARITHMETIC_INVALID" in decision(request=request).reason_codes
    payload = policy_payload()
    payload["pricing"]["effective_on"] = date(2026, 8, 3)  # type: ignore[index]
    assert "PRICING_CONTRACT_INVALID" in decision(payload).reason_codes
    payload = policy_payload()
    payload["provider_approval"]["approval_date"] = date(2026, 8, 3)  # type: ignore[index]
    assert "APPROVAL_DATE_INVALID" in decision(payload).reason_codes


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("unit_pricing_model", "PER_PAGE", "REQUEST_UNIT_PRICING_MODEL_MISMATCH"),
        ("requested_rate_per_minute", None, "REQUEST_RATE_PER_MINUTE_INVALID"),
        ("requested_rate_per_minute", 0, "REQUEST_RATE_PER_MINUTE_INVALID"),
        ("requested_rate_per_minute", 5, "REQUEST_RATE_PER_MINUTE_EXCEEDED"),
        ("requested_concurrency", None, "REQUEST_CONCURRENCY_INVALID"),
        ("requested_concurrency", 0, "REQUEST_CONCURRENCY_INVALID"),
        ("requested_concurrency", 2, "REQUEST_CONCURRENCY_EXCEEDED"),
    ],
)
def test_pricing_model_and_requested_rate_concurrency_are_policy_bound(
    field: str, value: object, reason: str
) -> None:
    request = request_payload()
    request[field] = value
    result = decision(request=request)
    assert result.status == "DENY"
    assert reason in result.reason_codes


def test_projected_total_uses_approved_unit_cost_after_request_cost_tampering() -> None:
    request = request_payload()
    request["per_unit_cost"] = "5.00"
    request["caller_projected_total"] = "3.00"
    result = decision(request=request)
    assert "REQUEST_UNIT_COST_MISMATCH" in result.reason_codes
    assert "PROJECTED_COST_MISMATCH" not in result.reason_codes
    assert "HARD_BUDGET_EXCEEDED" not in result.reason_codes


def test_payload_and_typed_dimension_contradictions_fail_closed() -> None:
    payload = policy_payload()
    payload["payload_policy"]["allow_list"] = []  # type: ignore[index]
    with pytest.raises(ValidationError, match="non-empty"):
        ProviderPreflightPolicy.model_validate(payload)
    payload = policy_payload()
    payload["payload_policy"]["forbidden_fields"] = ["document_kind"]  # type: ignore[index]
    with pytest.raises(ValidationError, match="disjoint"):
        ProviderPreflightPolicy.model_validate(payload)
    request = request_payload()
    request["payload_fields"] = []
    with pytest.raises(ValidationError, match="non-empty"):
        SyntheticDryRunDescriptor.model_validate(request)
    request = request_payload()
    request["request_payload_bytes"] = 2048
    assert "PAYLOAD_CONTRACT_INVALID" in decision(request=request).reason_codes
    payload = policy_payload()
    payload["training"]["opt_out_state"] = "UNKNOWN"  # type: ignore[index]
    with pytest.raises(ValidationError):
        ProviderPreflightPolicy.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("residency", "cross_border_transfer_decision"), "APPROVED_WITH_ATTESTATION"),
        (("retention", "exceptional_retention"), "APPROVED_EXCEPTION"),
        (("training", "training_use"), "OPT_OUT"),
        (("training", "service_improvement_use"), "OPT_OUT"),
        (("retention", "retention_start_event"), "REQUEST_ACCEPTED"),
        (("credentials", "rotation_period_days"), 91),
    ],
)
def test_permissive_or_over_ceiling_policy_values_are_rejected_before_complete_status(
    path: tuple[str, str], value: object
) -> None:
    payload = policy_payload()
    payload[path[0]][path[1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        ProviderPreflightPolicy.model_validate(payload)


def test_public_decision_and_stdout_report_are_strict_and_public_safe() -> None:
    result = decision()
    payload = result.model_dump(mode="json")
    payload["unexpected"] = "x"
    with pytest.raises(ValidationError):
        PreflightDecision.model_validate(payload)
    report = {
        "check_schema_version": "hyc.synthetic-p4-preflight-check.v2",
        "markers": (
            "GENERATED_SYNTHETIC_EVIDENCE",
            "HUMAN_REVIEW_REQUIRED",
            "NON_REPRESENTATIVE",
            "NOT_A_RELEASE_GATE",
        ),
        "local_pilot": {
            "aggregate_sha256": "a" * 64,
            "cohort_size_bucket": "3_TO_9",
            "empty_status": "HUMAN_EVIDENCE_REQUIRED",
            "small_cohort_suppression_verified": True,
        },
        "ap02": {
            "complete_status": result.status,
            "default_deny_reason_count": 0,
            "default_status": "DENY",
            "execution_effect": result.authorization_effect,
            "side_effects": result.side_effects,
        },
    }
    assert PublicPreflightReport.model_validate(report).check_schema_version.endswith("v2")
    report["local_pilot"]["aggregate_sha256"] = "/private/source.pdf"
    with pytest.raises(ValidationError):
        PublicPreflightReport.model_validate(report)
    with pytest.raises(ValueError, match="prohibited value"):
        validate_public_safe_tree({"free_value": "/private/source.pdf"})


@pytest.mark.parametrize(
    ("section", "keys"),
    [
        (
            "local_pilot",
            (
                "aggregate_sha256",
                "cohort_size_bucket",
                "empty_status",
                "small_cohort_suppression_verified",
            ),
        ),
        (
            "ap02",
            (
                "complete_status",
                "default_deny_reason_count",
                "default_status",
                "execution_effect",
                "side_effects",
            ),
        ),
    ],
)
def test_public_report_nested_submodels_require_every_key_and_forbid_extras(
    section: str, keys: tuple[str, ...]
) -> None:
    report = {
        "check_schema_version": "hyc.synthetic-p4-preflight-check.v2",
        "markers": (
            "GENERATED_SYNTHETIC_EVIDENCE",
            "HUMAN_REVIEW_REQUIRED",
            "NON_REPRESENTATIVE",
            "NOT_A_RELEASE_GATE",
        ),
        "local_pilot": {
            "aggregate_sha256": "a" * 64,
            "cohort_size_bucket": "3_TO_9",
            "empty_status": "INSUFFICIENT_ELIGIBLE_CORPUS",
            "small_cohort_suppression_verified": True,
        },
        "ap02": {
            "complete_status": "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR",
            "default_deny_reason_count": 1,
            "default_status": "DENY",
            "execution_effect": "EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY",
            "side_effects": "NONE",
        },
    }
    for key in keys:
        missing = {**report, section: {**report[section]}}  # type: ignore[index]
        missing[section].pop(key)  # type: ignore[index]
        with pytest.raises(ValidationError):
            PublicPreflightReport.model_validate(missing)
    extra = {**report, section: {**report[section], "unexpected": "x"}}  # type: ignore[index]
    with pytest.raises(ValidationError):
        PublicPreflightReport.model_validate(extra)


def test_preflight_reason_codes_are_a_closed_typed_set() -> None:
    payload = decision().model_dump(mode="json")
    payload["status"] = "DENY"
    payload["reason_codes"] = ["arbitrary-string"]
    with pytest.raises(ValidationError):
        PreflightDecision.model_validate(payload)


def test_every_remaining_preflight_reason_code_is_emitted_by_a_validated_mutation() -> None:
    def mutated_request(**changes: object) -> PreflightDecision:
        request = request_payload()
        request.update(changes)
        return decision(request=request)

    def mutated_policy(path: tuple[str, str], value: object) -> PreflightDecision:
        policy = policy_payload()
        policy[path[0]][path[1]] = value  # type: ignore[index]
        return decision(policy=policy)

    results = [
        evaluate_provider_preflight(
            ProviderPreflightPolicy(), SyntheticDryRunDescriptor.model_validate(request_payload())
        ),
        mutated_request(scope={**scope_payload(), "region": "foreign-region-001"}),
        mutated_request(account_scope_ref="foreign-account-001"),
        mutated_request(approved_destination="foreign-destination-001"),
        mutated_request(p4b_packet_id="foreign-packet-001"),
        mutated_request(request_payload_bytes=2048),
        mutated_request(requested_rate_per_minute=None),
        mutated_request(requested_rate_per_minute=5),
        mutated_request(requested_concurrency=None),
        mutated_request(requested_concurrency=2),
        mutated_request(billable_unit_count=None),
        mutated_request(currency="KRW"),
        mutated_request(unit_pricing_model="PER_PAGE"),
        mutated_request(per_unit_cost=None),
        mutated_request(per_unit_cost="1.49"),
        mutated_request(caller_projected_total="3.01"),
        mutated_request(billable_unit_count=10, caller_projected_total="15.00"),
        mutated_request(billable_unit_count=10**100),
        mutated_policy(("pricing", "effective_on"), date(2026, 8, 3)),
        mutated_policy(("provider_approval", "approval_date"), date(2026, 8, 3)),
    ]
    stale_approval = policy_payload()
    stale_approval["provider_approval"]["approval_evidence"] = evidence(  # type: ignore[index]
        14,
        attests_dimension="provider_approval",
        verified=date(2026, 7, 1),
        valid=date(2026, 8, 1),
    )
    results.append(decision(policy=stale_approval))
    foreign_approval_scope = policy_payload()
    foreign_approval_scope["provider_approval"]["approved_scope"]["region"] = "foreign-region-001"  # type: ignore[index]
    results.append(decision(policy=foreign_approval_scope))

    emitted = {reason for result in results for reason in result.reason_codes}
    assert emitted == set(get_args(PreflightReasonCode.__value__))


@pytest.mark.parametrize(
    "markers",
    [
        (),
        ("GENERATED_SYNTHETIC_EVIDENCE",),
        (
            "GENERATED_SYNTHETIC_EVIDENCE",
            "GENERATED_SYNTHETIC_EVIDENCE",
            "NON_REPRESENTATIVE",
            "NOT_A_RELEASE_GATE",
        ),
        (
            "HUMAN_REVIEW_REQUIRED",
            "GENERATED_SYNTHETIC_EVIDENCE",
            "NON_REPRESENTATIVE",
            "NOT_A_RELEASE_GATE",
        ),
        (
            "GENERATED_SYNTHETIC_EVIDENCE",
            "HUMAN_REVIEW_REQUIRED",
            "NON_REPRESENTATIVE",
            "NOT_A_RELEASE_GATE",
            "EXTRA",
        ),
    ],
)
def test_public_report_markers_are_exact_fixed_canonical_tuple(markers: tuple[str, ...]) -> None:
    report = {
        "check_schema_version": "hyc.synthetic-p4-preflight-check.v2",
        "markers": markers,
        "local_pilot": {
            "aggregate_sha256": "a" * 64,
            "cohort_size_bucket": "LT_3",
            "empty_status": "INSUFFICIENT_ELIGIBLE_CORPUS",
            "small_cohort_suppression_verified": False,
        },
        "ap02": {
            "complete_status": "DENY",
            "default_deny_reason_count": 1,
            "default_status": "DENY",
            "execution_effect": "EVIDENCE_ONLY_NOT_EXECUTION_AUTHORITY",
            "side_effects": "NONE",
        },
    }
    with pytest.raises(ValidationError):
        PublicPreflightReport.model_validate(report)


def test_ast_claim_is_limited_to_the_new_modules_and_script() -> None:
    root = Path(__file__).parents[2]
    targets = [
        root / "src/hyc_evaluation/local_pilot.py",
        root / "src/hyc_evaluation/preflight.py",
        root / "scripts/run_p4_preflight.py",
    ]
    forbidden = {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "environ",
        "getenv",
        "__import__",
        "eval",
        "exec",
        "compile",
        "system",
        "popen",
        "run",
        "Popen",
        "socket",
        "create_connection",
        "urlopen",
    }

    def assert_no_prohibited_surface(source: str) -> None:
        tree = ast.parse(source)
        names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)} | {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        }
        assert names.isdisjoint(forbidden)

    for target in targets:
        assert_no_prohibited_surface(target.read_text())
    for mutation in ("path.read_text()", "os.environ", "eval('x')", "socket.socket()"):
        with pytest.raises(AssertionError):
            assert_no_prohibited_surface(mutation)


def test_generated_preflight_runtime_does_not_use_common_network_process_env_or_file_surfaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = Path(__file__).parents[2] / "scripts/run_p4_preflight.py"
    spec = importlib.util.spec_from_file_location("p4_preflight_script", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("side-effect surface called")

    monkeypatch.setattr(builtins, "open", blocked)
    monkeypatch.setattr(os, "getenv", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(subprocess, "Popen", blocked)

    class Stdout:
        buffer = io.BytesIO()

    monkeypatch.setattr(sys, "stdout", Stdout())
    assert module.main() == 0
