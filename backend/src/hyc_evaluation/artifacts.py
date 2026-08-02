from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext
from typing import Annotated, Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hyc_evaluation.normalization import NormalizationBinding
from hyc_evaluation.schema import (
    CanonicalDecimal,
    GoldenGeometry,
    GoldenIdentity,
    GoldenValue,
    Identifier,
    SemanticVersion,
    ValueKind,
    VersionBindings,
)

SHA256_PATTERN = r"^[0-9a-f]{64}$"
ARTIFACT_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)

type EvaluationReason = Literal[
    "BINDING_MISMATCH",
    "DOCUMENT_CLASSIFICATION_MISMATCH",
    "DUPLICATE_FIELD",
    "HANDWRITING_REFERENCE_ONLY",
    "LOGIC_CONFLICT",
    "LOW_CONFIDENCE",
    "PAGE_MISMATCH",
    "MISSING_ARTIFACT",
    "MISSING_REQUIRED",
    "UNAPPROVED_NORMALIZATION",
    "UNMAPPED",
    "UPSTREAM_FAILURE",
    "VALUE_MISMATCH",
]
type FieldOutcomeName = Literal[
    "DUPLICATE_FIELD",
    "EXCLUDED_IGNORED",
    "HANDWRITING_REFERENCE_ONLY",
    "LOGIC_CONFLICT",
    "LOW_CONFIDENCE",
    "MATCH",
    "MISMATCH",
    "MISSING_REQUIRED",
    "NORMALIZED_MATCH",
    "UNMAPPED",
]


def _ordered_reasons(value: object) -> tuple[EvaluationReason, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("reason codes must be an ordered collection")
    values = tuple(value)
    if len(values) != len(set(values)):
        raise ValueError("reason codes must be unique")
    return cast(tuple[EvaluationReason, ...], tuple(sorted(values)))


def _outcome_for_reasons(
    reasons: set[EvaluationReason],
) -> FieldOutcomeName:
    for reason, outcome in (
        ("HANDWRITING_REFERENCE_ONLY", "HANDWRITING_REFERENCE_ONLY"),
        ("DUPLICATE_FIELD", "DUPLICATE_FIELD"),
        ("MISSING_REQUIRED", "MISSING_REQUIRED"),
        ("UNMAPPED", "UNMAPPED"),
        ("LOGIC_CONFLICT", "LOGIC_CONFLICT"),
        ("LOW_CONFIDENCE", "LOW_CONFIDENCE"),
    ):
        if reason in reasons:
            return cast(FieldOutcomeName, outcome)
    return "MISMATCH" if reasons else "MATCH"


class ArtifactModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


type StageName = Literal[
    "TEXT_LAYER_DETECTION",
    "PAGE_RENDER",
    "ROTATION_DESKEW_CONTRAST",
    "TABLE_DETECTION",
    "SYNTHETIC_FIXTURE_EXTRACTION",
    "PARSE",
    "SCHEMA_VALIDATION",
    "LOGIC_VALIDATION",
]
type StageStatus = Literal["SUCCESS", "FAILED", "SKIPPED_UPSTREAM_FAILURE"]
type StageWarningCode = Literal[
    "HANDWRITING_REFERENCE_ONLY",
    "LOW_CONFIDENCE",
    "STAMP_OVERLAP",
]
type StageErrorCode = Literal[
    "CORRUPT_SYNTHETIC_INPUT",
    "ENCRYPTED_SYNTHETIC_INPUT",
    "LOGIC_VALIDATION_FAILED",
    "SCHEMA_VALIDATION_FAILED",
    "SKIPPED_UPSTREAM_FAILURE",
    "UPLOAD_READ_RACE",
]

STAGE_ERROR_COMPATIBILITY: dict[StageName, frozenset[StageErrorCode]] = {
    "TEXT_LAYER_DETECTION": frozenset(
        {"CORRUPT_SYNTHETIC_INPUT", "ENCRYPTED_SYNTHETIC_INPUT"}
    ),
    "PAGE_RENDER": frozenset({"UPLOAD_READ_RACE"}),
    "ROTATION_DESKEW_CONTRAST": frozenset(),
    "TABLE_DETECTION": frozenset(),
    "SYNTHETIC_FIXTURE_EXTRACTION": frozenset(),
    "PARSE": frozenset(),
    "SCHEMA_VALIDATION": frozenset({"SCHEMA_VALIDATION_FAILED"}),
    "LOGIC_VALIDATION": frozenset({"LOGIC_VALIDATION_FAILED"}),
}

STAGE_ORDER: tuple[StageName, ...] = (
    "TEXT_LAYER_DETECTION",
    "PAGE_RENDER",
    "ROTATION_DESKEW_CONTRAST",
    "TABLE_DETECTION",
    "SYNTHETIC_FIXTURE_EXTRACTION",
    "PARSE",
    "SCHEMA_VALIDATION",
    "LOGIC_VALIDATION",
)


class StageArtifact(ArtifactModel):
    stage_schema_version: Literal["hyc.stage-artifact.v1"]
    artifact_ref: Identifier
    stage_name: StageName
    stage_version: SemanticVersion
    stage_order: Annotated[int, Field(ge=1, le=8)]
    ordering_marker: Identifier
    stable_clock_marker: Identifier
    input_refs: tuple[Identifier, ...]
    input_digests: tuple[Annotated[str, Field(pattern=SHA256_PATTERN)], ...]
    output_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    upstream_artifact_refs: tuple[Identifier, ...]
    status: StageStatus
    warning_codes: tuple[StageWarningCode, ...]
    error_codes: tuple[StageErrorCode, ...]

    @field_validator(
        "input_refs",
        "input_digests",
        "upstream_artifact_refs",
        mode="before",
    )
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("warning_codes", "error_codes", mode="before")
    @classmethod
    def canonicalize_codes(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            return tuple(sorted(value)) if value else ()
        return value

    @model_validator(mode="after")
    def enforce_stage_contract(self) -> StageArtifact:
        if STAGE_ORDER[self.stage_order - 1] != self.stage_name:
            raise ValueError("stage name and order must match the versioned sequence")
        if len(self.input_refs) != len(self.input_digests) or not self.input_refs:
            raise ValueError("stage input refs and digests must have equal non-zero cardinality")
        if len(self.input_refs) != len(set(self.input_refs)):
            raise ValueError("stage input refs must be unique")
        if len(self.warning_codes) != len(set(self.warning_codes)):
            raise ValueError("stage warning codes must be unique")
        if len(self.error_codes) != len(set(self.error_codes)):
            raise ValueError("stage error codes must be unique")
        if self.status == "SUCCESS" and self.error_codes:
            raise ValueError("successful stage cannot contain errors")
        if self.status == "FAILED" and not self.error_codes:
            raise ValueError("failed stage requires a structured error")
        skipped = self.status == "SKIPPED_UPSTREAM_FAILURE"
        if skipped != (self.error_codes == ("SKIPPED_UPSTREAM_FAILURE",)):
            raise ValueError("skipped stages must use SKIPPED_UPSTREAM_FAILURE exactly")
        if skipped and self.warning_codes:
            raise ValueError("skipped stages cannot claim unobserved warnings")
        if self.warning_codes and (
            self.stage_name != "SYNTHETIC_FIXTURE_EXTRACTION" or self.status != "SUCCESS"
        ):
            raise ValueError("warnings are only observable at successful fixture extraction")
        if self.status == "FAILED":
            allowed = STAGE_ERROR_COMPATIBILITY[self.stage_name]
            if any(code not in allowed for code in self.error_codes):
                raise ValueError("stage error code is incompatible with the failed stage")
            if "SKIPPED_UPSTREAM_FAILURE" in self.error_codes:
                raise ValueError("failed stages cannot mix skipped-upstream status")
        return self


class StageArtifactManifest(ArtifactModel):
    manifest_schema_version: Literal["hyc.stage-manifest.v1"]
    case_id: Identifier
    input_ref: Identifier
    input_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    stages: tuple[StageArtifact, ...]

    @field_validator("stages", mode="before")
    @classmethod
    def freeze_stages(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def enforce_exact_lineage_and_failure_propagation(self) -> StageArtifactManifest:
        if len(self.stages) != len(STAGE_ORDER):
            raise ValueError("stage manifest must contain exactly eight stages")
        if tuple(stage.stage_name for stage in self.stages) != STAGE_ORDER:
            raise ValueError("stage manifest order must match the versioned sequence")
        if tuple(stage.stage_order for stage in self.stages) != tuple(range(1, 9)):
            raise ValueError("stage order must be contiguous")
        refs = tuple(stage.artifact_ref for stage in self.stages)
        if len(refs) != len(set(refs)):
            raise ValueError("stage artifact refs must be unique")
        first = self.stages[0]
        if first.input_refs != (self.input_ref,) or first.input_digests != (self.input_sha256,):
            raise ValueError("first stage must bind the declared source input")
        if first.upstream_artifact_refs:
            raise ValueError("first stage cannot have an upstream artifact")
        failed = first.status != "SUCCESS"
        for previous, current in zip(self.stages, self.stages[1:], strict=False):
            if current.upstream_artifact_refs != (previous.artifact_ref,):
                raise ValueError("each stage must reference exactly its immediate upstream")
            if current.input_refs != (previous.artifact_ref,) or current.input_digests != (
                previous.output_sha256,
            ):
                raise ValueError("stage input must bind the exact upstream artifact digest")
            if failed and current.status != "SKIPPED_UPSTREAM_FAILURE":
                raise ValueError("downstream stages must skip after upstream failure")
            if not failed and current.status == "SKIPPED_UPSTREAM_FAILURE":
                raise ValueError("stage cannot skip before an upstream failure")
            failed = failed or current.status != "SUCCESS"
        return self


class CandidateValue(ArtifactModel):
    candidate_order: Annotated[int, Field(ge=1)]
    identity: GoldenIdentity
    field_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    value: GoldenValue
    geometry: GoldenGeometry
    applied_normalizations: tuple[NormalizationBinding, ...]
    confidence: Annotated[CanonicalDecimal, Field(ge=0, le=1)]
    reason_codes: tuple[EvaluationReason, ...]
    handwriting_reference_only: bool
    review_required: bool

    @field_validator("applied_normalizations", mode="before")
    @classmethod
    def freeze_normalizations(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> tuple[EvaluationReason, ...]:
        return _ordered_reasons(value)

    @model_validator(mode="after")
    def enforce_fail_closed_signals(self) -> CandidateValue:
        if (self.confidence < Decimal("1")) != ("LOW_CONFIDENCE" in self.reason_codes):
            raise ValueError("confidence below one must use LOW_CONFIDENCE exactly")
        if (self.value.raw is None) != ("MISSING_REQUIRED" in self.reason_codes):
            raise ValueError("missing candidate values must use MISSING_REQUIRED exactly")
        handwriting_reason = "HANDWRITING_REFERENCE_ONLY" in self.reason_codes
        if handwriting_reason != self.handwriting_reference_only:
            raise ValueError("handwriting marker must use HANDWRITING_REFERENCE_ONLY")
        if bool(self.reason_codes) != self.review_required:
            raise ValueError("candidate review state must reflect its reason codes")
        identities = [
            (binding.normalization_id, binding.normalization_version)
            for binding in self.applied_normalizations
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("applied normalization identities must be unique")
        return self


class CandidateRunArtifact(ArtifactModel):
    artifact_schema_version: Literal["hyc.candidate-run.v1"]
    golden_schema_version: Literal["hyc.golden.v1"]
    dataset_id: Identifier
    dataset_version: SemanticVersion
    dataset_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    case_id: Identifier
    input_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    provider_name: Literal["synthetic-fixture"]
    document_kind: Literal["supplier-coa", "supplier-inspection-report"]
    bindings: VersionBindings
    stage_manifest: StageArtifactManifest
    stage_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    final_stage_artifact_ref: Identifier
    values: tuple[CandidateValue, ...]
    reason_codes: tuple[EvaluationReason, ...]
    review_required: bool
    escalation_required: bool

    @field_validator("values", mode="before")
    @classmethod
    def freeze_values(cls, value: object) -> object:
        if isinstance(value, list):
            return tuple(value)
        return value

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> tuple[EvaluationReason, ...]:
        return _ordered_reasons(value)

    @model_validator(mode="after")
    def validate_order_and_review_propagation(self) -> CandidateRunArtifact:
        orders = tuple(value.candidate_order for value in self.values)
        if orders != tuple(range(1, len(self.values) + 1)):
            raise ValueError("candidate values must retain contiguous source order")
        child_reasons = {reason for value in self.values for reason in value.reason_codes}
        identities = [
            (
                value.identity.document_id,
                value.identity.section_id,
                value.identity.row_id,
                value.identity.sample_id,
                value.field_key,
            )
            for value in self.values
        ]
        duplicate_identities = {
            identity for identity in identities if identities.count(identity) > 1
        }
        if duplicate_identities and any(
            "DUPLICATE_FIELD" not in value.reason_codes
            for value, identity in zip(self.values, identities, strict=True)
            if identity in duplicate_identities
        ):
            raise ValueError("duplicate candidate fields must fail closed")
        if not child_reasons.issubset(self.reason_codes):
            raise ValueError("run reason codes must include all candidate value reasons")
        needs_review = bool(self.reason_codes) or any(
            value.review_required for value in self.values
        )
        if needs_review != self.review_required:
            raise ValueError("run review state must propagate candidate reasons")
        if self.review_required != self.escalation_required:
            raise ValueError("review-required runs must remain escalated")
        if self.stage_manifest.case_id != self.case_id:
            raise ValueError("candidate case must match its stage manifest")
        if self.stage_manifest.input_sha256 != self.input_sha256:
            raise ValueError("candidate input must match its stage manifest")
        if self.stage_manifest_sha256 != canonical_sha256(self.stage_manifest):
            raise ValueError("candidate must bind the exact stage manifest digest")
        if self.final_stage_artifact_ref != self.stage_manifest.stages[-1].artifact_ref:
            raise ValueError("candidate must bind the final stage artifact ref")
        stage_failed = any(stage.status != "SUCCESS" for stage in self.stage_manifest.stages)
        if stage_failed != ("UPSTREAM_FAILURE" in self.reason_codes):
            raise ValueError("stage failure must propagate UPSTREAM_FAILURE exactly")
        return self


class MetricCount(ArtifactModel):
    numerator: Annotated[int, Field(ge=0)]
    denominator: Annotated[int, Field(ge=0)]
    value: CanonicalDecimal | None
    excluded_reference_count: Annotated[int, Field(ge=0)]
    excluded_ignored_count: Annotated[int, Field(ge=0)]
    error_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_ratio(self) -> MetricCount:
        if self.numerator > self.denominator:
            raise ValueError("metric numerator cannot exceed denominator")
        if self.denominator == 0:
            if self.value is not None:
                raise ValueError("zero-denominator metrics are not applicable")
        else:
            with localcontext(ARTIFACT_DECIMAL_CONTEXT):
                expected = Decimal(self.numerator) / Decimal(self.denominator)
            if self.value is None or self.value != expected:
                raise ValueError("metric value must exactly reflect numerator and denominator")
        return self


class KindMetrics(ArtifactModel):
    kind: ValueKind
    exact: MetricCount
    normalized: MetricCount


class PolygonIoUEvidence(ArtifactModel):
    case_id: Identifier
    identity: GoldenIdentity
    field_key: str
    iou: CanonicalDecimal | None
    error_code: Literal["PAGE_MISMATCH"] | None

    @model_validator(mode="after")
    def require_value_or_error(self) -> PolygonIoUEvidence:
        if (self.iou is None) == (self.error_code is None):
            raise ValueError("polygon IoU must have exactly one value or error")
        if self.iou is not None and not Decimal("0") <= self.iou <= Decimal("1"):
            raise ValueError("polygon IoU must be within zero and one")
        return self


class MissingDetectionCounts(ArtifactModel):
    true_positive: Annotated[int, Field(ge=0)]
    false_positive: Annotated[int, Field(ge=0)]
    false_negative: Annotated[int, Field(ge=0)]
    true_negative: Annotated[int, Field(ge=0)]
    precision: MetricCount
    recall: MetricCount

    @model_validator(mode="after")
    def bind_metrics_to_confusion_counts(self) -> MissingDetectionCounts:
        expected_precision = (
            self.true_positive,
            self.true_positive + self.false_positive,
        )
        expected_recall = (
            self.true_positive,
            self.true_positive + self.false_negative,
        )
        if (self.precision.numerator, self.precision.denominator) != expected_precision:
            raise ValueError("missing precision must bind TP / (TP + FP)")
        if (self.recall.numerator, self.recall.denominator) != expected_recall:
            raise ValueError("missing recall must bind TP / (TP + FN)")
        return self


class CohortMetrics(ArtifactModel):
    document_classification_exact: MetricCount
    exact_field_match: MetricCount
    normalized_field_match: MetricCount
    missing_required: MetricCount
    missing_detection: MissingDetectionCounts
    row_precision: MetricCount
    row_recall: MetricCount
    page_number_exact: MetricCount
    polygon_iou: tuple[PolygonIoUEvidence, ...]
    by_kind: tuple[KindMetrics, ...]
    excluded_reference_count: Annotated[int, Field(ge=0)]
    excluded_ignored_count: Annotated[int, Field(ge=0)]
    duplicate_field_count: Annotated[int, Field(ge=0)]
    unmapped_field_count: Annotated[int, Field(ge=0)]
    logic_conflict_count: Annotated[int, Field(ge=0)]
    low_confidence_count: Annotated[int, Field(ge=0)]
    page_mismatch_count: Annotated[int, Field(ge=0)]
    missing_polygon_count: Literal[0]
    invalid_polygon_count: Literal[0]

    @model_validator(mode="after")
    def bind_geometry_counters_to_evidence(self) -> CohortMetrics:
        page_mismatches = sum(
            evidence.error_code == "PAGE_MISMATCH" for evidence in self.polygon_iou
        )
        if self.page_mismatch_count != page_mismatches:
            raise ValueError("page mismatch count must bind polygon evidence")
        if self.page_number_exact.denominator != len(self.polygon_iou):
            raise ValueError("page metric denominator must bind polygon evidence cardinality")
        if self.page_number_exact.numerator != len(self.polygon_iou) - page_mismatches:
            raise ValueError("page metric numerator must bind same-page geometry evidence")
        return self


class FieldOutcome(ArtifactModel):
    identity: GoldenIdentity
    field_key: str
    kind: ValueKind
    expected_order: Annotated[int, Field(ge=1)] | None
    expected_required: bool | None
    expected_value_missing: bool | None
    candidate_value_missing: bool | None
    candidate_orders: tuple[Annotated[int, Field(ge=1)], ...]
    exact_match: bool | None
    normalized_match: bool | None
    page_number_match: bool | None
    polygon_iou: CanonicalDecimal | None
    outcome: FieldOutcomeName
    reason_codes: tuple[EvaluationReason, ...]
    review_required: bool
    escalation_required: bool
    excluded_reference_only: bool
    excluded_ignored: bool

    @field_validator("candidate_orders", mode="before")
    @classmethod
    def freeze_candidate_orders(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> tuple[EvaluationReason, ...]:
        return _ordered_reasons(value)

    @model_validator(mode="after")
    def bind_outcome_to_fail_closed_state(self) -> FieldOutcome:
        reasons = set(self.reason_codes)
        requires_review = bool(reasons)
        if self.review_required != requires_review:
            raise ValueError("field review state must exactly reflect reason codes")
        if self.escalation_required != requires_review:
            raise ValueError("field escalation state must exactly reflect reason codes")
        expected_outcome: FieldOutcomeName = (
            "UNMAPPED"
            if self.expected_order is None
            else (
                "EXCLUDED_IGNORED"
                if self.excluded_ignored
                else (
                    "NORMALIZED_MATCH"
                    if not reasons
                    and self.exact_match is False
                    and self.normalized_match is True
                    else _outcome_for_reasons(reasons)
                )
            )
        )
        if self.outcome != expected_outcome:
            raise ValueError("field outcome must exactly reflect reasons and exclusions")
        handwriting_reference = "HANDWRITING_REFERENCE_ONLY" in reasons
        if self.excluded_reference_only != handwriting_reference:
            raise ValueError("reference exclusion must exactly reflect handwriting reason")
        if self.excluded_reference_only and self.excluded_ignored:
            raise ValueError("a field cannot be both ignored and reference-only")
        if self.expected_order is None:
            if (
                self.expected_required is not None
                or self.expected_value_missing is not None
                or self.excluded_ignored
            ):
                raise ValueError("unmapped candidates cannot claim expected-field metadata")
            if not self.candidate_orders or "UNMAPPED" not in reasons:
                raise ValueError("unmapped outcomes require candidate evidence and UNMAPPED")
            if any(
                value is not None
                for value in (
                    self.exact_match,
                    self.normalized_match,
                    self.page_number_match,
                    self.polygon_iou,
                )
            ):
                raise ValueError("unmapped outcomes must use a consistent None evidence tuple")
        elif self.expected_required is None:
            raise ValueError("expected outcomes must bind required-field metadata")
        elif self.expected_value_missing is None:
            raise ValueError("expected outcomes must bind expected missing-value state")
        if self.candidate_orders and self.candidate_value_missing is None:
            raise ValueError("candidate evidence must bind candidate missing-value state")
        if not self.candidate_orders and self.candidate_value_missing is not True:
            raise ValueError("absent candidate evidence must bind candidate missing true")

        if self.exact_match is True and self.normalized_match is not True:
            raise ValueError("exact match requires normalized match")
        if "VALUE_MISMATCH" in reasons and self.normalized_match is not False:
            raise ValueError("value mismatch requires normalized_match false")
        if "PAGE_MISMATCH" in reasons:
            if self.page_number_match is not False or self.polygon_iou is not None:
                raise ValueError("page mismatch cannot carry a valid IoU")
        elif self.page_number_match is False:
            raise ValueError("page_number_match false requires PAGE_MISMATCH")
        if self.page_number_match is True and self.polygon_iou is None:
            raise ValueError("same-page geometry evidence requires an IoU")

        excluded = self.excluded_reference_only or self.excluded_ignored
        if excluded or len(self.candidate_orders) != 1:
            if any(
                value is not None
                for value in (
                    self.exact_match,
                    self.normalized_match,
                    self.page_number_match,
                    self.polygon_iou,
                )
            ):
                raise ValueError("excluded, missing, or duplicate outcomes require None evidence")
        elif self.expected_order is not None and any(
            value is None
            for value in (self.exact_match, self.normalized_match, self.page_number_match)
        ):
            raise ValueError("one-to-one eligible outcomes require complete match evidence")

        if self.outcome == "MATCH":
            if (
                self.expected_order is None
                or not self.candidate_orders
                or self.exact_match is not True
                or self.normalized_match is not True
                or self.page_number_match is not True
                or self.polygon_iou is None
            ):
                raise ValueError(
                    "MATCH requires complete exact, normalized, page, and IoU evidence"
                )
        return self


def _metric_signature(metric: MetricCount) -> tuple[int, int, int, int, int]:
    return (
        metric.numerator,
        metric.denominator,
        metric.excluded_reference_count,
        metric.excluded_ignored_count,
        metric.error_count,
    )


def _expected_metric_signature(
    numerator: int,
    denominator: int,
    *,
    excluded_reference: int = 0,
    excluded_ignored: int = 0,
    errors: int = 0,
) -> tuple[int, int, int, int, int]:
    return numerator, denominator, excluded_reference, excluded_ignored, errors


def _validate_metrics_against_fields(
    case_id: str,
    fields: tuple[FieldOutcome, ...],
    metrics: CohortMetrics,
) -> None:
    expected_fields = tuple(field for field in fields if field.expected_order is not None)
    eligible = tuple(
        field
        for field in expected_fields
        if not field.excluded_reference_only and not field.excluded_ignored
    )
    excluded_reference = sum(field.excluded_reference_only for field in expected_fields)
    excluded_ignored = sum(field.excluded_ignored for field in expected_fields)
    duplicates = sum("DUPLICATE_FIELD" in field.reason_codes for field in fields)
    unmapped = sum(field.expected_order is None for field in fields)
    normalization_errors = sum(
        "UNAPPROVED_NORMALIZATION" in field.reason_codes for field in fields
    )

    exact_signature = _expected_metric_signature(
        sum(field.exact_match is True for field in eligible),
        len(eligible),
        excluded_reference=excluded_reference,
        excluded_ignored=excluded_ignored,
        errors=duplicates,
    )
    normalized_signature = _expected_metric_signature(
        sum(field.normalized_match is True for field in eligible),
        len(eligible),
        excluded_reference=excluded_reference,
        excluded_ignored=excluded_ignored,
        errors=duplicates + normalization_errors,
    )
    if _metric_signature(metrics.exact_field_match) != exact_signature:
        raise ValueError("exact metric must be derivable from field outcomes")
    if _metric_signature(metrics.normalized_field_match) != normalized_signature:
        raise ValueError("normalized metric must be derivable from field outcomes")

    page_fields = tuple(field for field in eligible if field.page_number_match is not None)
    page_signature = _expected_metric_signature(
        sum(field.page_number_match is True for field in page_fields),
        len(page_fields),
        excluded_reference=excluded_reference,
        excluded_ignored=excluded_ignored,
        errors=duplicates,
    )
    if _metric_signature(metrics.page_number_exact) != page_signature:
        raise ValueError("page metric must be derivable from field outcomes")

    expected_evidence = []
    for field in page_fields:
        expected_evidence.append(
            PolygonIoUEvidence(
                case_id=case_id,
                identity=field.identity,
                field_key=field.field_key,
                iou=field.polygon_iou,
                error_code=("PAGE_MISMATCH" if field.page_number_match is False else None),
            )
        )
    if metrics.polygon_iou != tuple(expected_evidence):
        raise ValueError("polygon evidence must exactly bind field outcomes")

    if metrics.excluded_reference_count != excluded_reference:
        raise ValueError("excluded reference count must bind field outcomes")
    if metrics.excluded_ignored_count != excluded_ignored:
        raise ValueError("excluded ignored count must bind field outcomes")
    if metrics.duplicate_field_count != duplicates:
        raise ValueError("duplicate count must bind field outcomes")
    if metrics.unmapped_field_count != unmapped:
        raise ValueError("unmapped count must bind candidate-only field outcomes")
    if metrics.logic_conflict_count != sum(
        "LOGIC_CONFLICT" in field.reason_codes for field in fields
    ):
        raise ValueError("logic conflict count must bind field outcomes")
    if metrics.low_confidence_count != sum(
        "LOW_CONFIDENCE" in field.reason_codes for field in fields
    ):
        raise ValueError("low-confidence count must bind field outcomes")
    if metrics.page_mismatch_count != sum(
        field.page_number_match is False for field in page_fields
    ):
        raise ValueError("page mismatch count must bind field outcomes")

    required = tuple(field for field in eligible if field.expected_required)
    missing_signature = _expected_metric_signature(
        sum("MISSING_REQUIRED" in field.reason_codes for field in required),
        len(required),
        excluded_reference=excluded_reference,
        excluded_ignored=excluded_ignored,
    )
    if _metric_signature(metrics.missing_required) != missing_signature:
        raise ValueError("required-missing metric must bind field outcomes")
    true_positive = sum(
        field.expected_value_missing is True and field.candidate_value_missing is True
        for field in required
    )
    false_positive = sum(
        field.expected_value_missing is False and field.candidate_value_missing is True
        for field in required
    )
    false_negative = sum(
        field.expected_value_missing is True and field.candidate_value_missing is False
        for field in required
    )
    true_negative = sum(
        field.expected_value_missing is False and field.candidate_value_missing is False
        for field in required
    )
    if (
        metrics.missing_detection.true_positive,
        metrics.missing_detection.false_positive,
        metrics.missing_detection.false_negative,
        metrics.missing_detection.true_negative,
    ) != (true_positive, false_positive, false_negative, true_negative):
        raise ValueError("missing-detection counts must bind field outcomes")

    expected_rows = {
        (field.identity.document_id, field.identity.section_id, field.identity.row_id)
        for field in eligible
    }
    predicted_rows = {
        (field.identity.document_id, field.identity.section_id, field.identity.row_id)
        for field in fields
        if field.candidate_orders and not field.excluded_reference_only
    }
    row_true_positive = len(expected_rows & predicted_rows)
    row_precision = _expected_metric_signature(
        row_true_positive,
        len(predicted_rows),
    )
    row_recall = _expected_metric_signature(row_true_positive, len(expected_rows))
    if _metric_signature(metrics.row_precision) != row_precision:
        raise ValueError("row precision must bind field identities")
    if _metric_signature(metrics.row_recall) != row_recall:
        raise ValueError("row recall must bind field identities")

    by_kind = {item.kind: item for item in metrics.by_kind}
    if len(by_kind) != len(metrics.by_kind):
        raise ValueError("kind metrics must be unique")
    for kind, item in by_kind.items():
        kind_expected = tuple(field for field in expected_fields if field.kind == kind)
        kind_eligible = tuple(
            field
            for field in kind_expected
            if not field.excluded_reference_only and not field.excluded_ignored
        )
        kind_reference = sum(field.excluded_reference_only for field in kind_expected)
        kind_ignored = sum(field.excluded_ignored for field in kind_expected)
        kind_duplicates = sum(
            "DUPLICATE_FIELD" in field.reason_codes for field in fields if field.kind == kind
        )
        kind_normalization_errors = sum(
            "UNAPPROVED_NORMALIZATION" in field.reason_codes
            for field in fields
            if field.kind == kind
        )
        if _metric_signature(item.exact) != _expected_metric_signature(
            sum(field.exact_match is True for field in kind_eligible),
            len(kind_eligible),
            excluded_reference=kind_reference,
            excluded_ignored=kind_ignored,
            errors=kind_duplicates,
        ):
            raise ValueError("per-kind exact metric must bind field outcomes")
        if _metric_signature(item.normalized) != _expected_metric_signature(
            sum(field.normalized_match is True for field in kind_eligible),
            len(kind_eligible),
            excluded_reference=kind_reference,
            excluded_ignored=kind_ignored,
            errors=kind_duplicates + kind_normalization_errors,
        ):
            raise ValueError("per-kind normalized metric must bind field outcomes")


class CaseOutcome(ArtifactModel):
    case_id: Identifier
    ordering_key: Identifier
    input_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    candidate_artifact_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    stage_manifest_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    fields: tuple[FieldOutcome, ...]
    metrics: CohortMetrics
    reason_codes: tuple[EvaluationReason, ...]
    review_required: bool
    escalation_required: bool
    acceptance_eligible: bool

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> tuple[EvaluationReason, ...]:
        return _ordered_reasons(value)

    @model_validator(mode="after")
    def propagate_field_fail_closed_state(self) -> CaseOutcome:
        reasons = set(self.reason_codes)
        child_reasons = {reason for field in self.fields for reason in field.reason_codes}
        if not child_reasons.issubset(reasons):
            raise ValueError("case reason codes must include all field reasons")
        requires_review = bool(reasons) or any(field.review_required for field in self.fields)
        if self.review_required != requires_review:
            raise ValueError("case review state must propagate reasons and field review")
        if self.escalation_required != requires_review:
            raise ValueError("case escalation state must propagate review state")
        if self.acceptance_eligible == requires_review:
            raise ValueError("case acceptance must be the inverse of fail-closed review")
        _validate_metrics_against_fields(self.case_id, self.fields, self.metrics)
        return self


class NotApplicableMetric(ArtifactModel):
    status: Literal["NOT_APPLICABLE"]
    reason: Literal["P4A_SYNTHETIC_NO_MEASUREMENT"]


class OperationalMetrics(ArtifactModel):
    latency: NotApplicableMetric
    provider_cost: NotApplicableMetric
    human_correction_time: NotApplicableMetric


def _sum_metric_signatures(metrics: tuple[MetricCount, ...]) -> tuple[int, int, int, int, int]:
    return (
        sum(metric.numerator for metric in metrics),
        sum(metric.denominator for metric in metrics),
        sum(metric.excluded_reference_count for metric in metrics),
        sum(metric.excluded_ignored_count for metric in metrics),
        sum(metric.error_count for metric in metrics),
    )


def _validate_report_metrics(
    cases: tuple[CaseOutcome, ...], metrics: CohortMetrics
) -> None:
    for attribute in (
        "document_classification_exact",
        "exact_field_match",
        "normalized_field_match",
        "missing_required",
        "row_precision",
        "row_recall",
        "page_number_exact",
    ):
        case_metrics = tuple(getattr(case.metrics, attribute) for case in cases)
        if _metric_signature(getattr(metrics, attribute)) != _sum_metric_signatures(
            case_metrics
        ):
            raise ValueError(f"report {attribute} must aggregate case metrics")

    for attribute in ("precision", "recall"):
        case_metrics = tuple(
            getattr(case.metrics.missing_detection, attribute) for case in cases
        )
        if _metric_signature(getattr(metrics.missing_detection, attribute)) != (
            _sum_metric_signatures(case_metrics)
        ):
            raise ValueError(f"report missing {attribute} must aggregate case metrics")
    for attribute in ("true_positive", "false_positive", "false_negative", "true_negative"):
        if getattr(metrics.missing_detection, attribute) != sum(
            getattr(case.metrics.missing_detection, attribute) for case in cases
        ):
            raise ValueError("report missing-detection counts must aggregate cases")

    if metrics.polygon_iou != tuple(
        evidence for case in cases for evidence in case.metrics.polygon_iou
    ):
        raise ValueError("report polygon evidence must preserve exact case order")
    for attribute in (
        "excluded_reference_count",
        "excluded_ignored_count",
        "duplicate_field_count",
        "unmapped_field_count",
        "logic_conflict_count",
        "low_confidence_count",
        "page_mismatch_count",
        "missing_polygon_count",
        "invalid_polygon_count",
    ):
        if getattr(metrics, attribute) != sum(
            getattr(case.metrics, attribute) for case in cases
        ):
            raise ValueError(f"report {attribute} must aggregate case metrics")

    case_kind_maps = tuple({item.kind: item for item in case.metrics.by_kind} for case in cases)
    report_kind_map = {item.kind: item for item in metrics.by_kind}
    if len(report_kind_map) != len(metrics.by_kind):
        raise ValueError("report kind metrics must be unique")
    for kind, item in report_kind_map.items():
        for attribute in ("exact", "normalized"):
            case_metrics = tuple(
                getattr(case_map[kind], attribute)
                for case_map in case_kind_maps
                if kind in case_map
            )
            if _metric_signature(getattr(item, attribute)) != _sum_metric_signatures(
                case_metrics
            ):
                raise ValueError("report per-kind metrics must aggregate cases")


class GoldenEvaluationReport(ArtifactModel):
    report_schema_version: Literal["hyc.evaluation-report.v1"]
    golden_schema_version: Literal["hyc.golden.v1"]
    candidate_artifact_schema_version: Literal["hyc.candidate-run.v1"]
    dataset_id: Identifier
    dataset_version: SemanticVersion
    dataset_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    provider_name: Literal["synthetic-fixture"]
    bindings: VersionBindings
    candidate_artifact_sha256: tuple[Annotated[str, Field(pattern=SHA256_PATTERN)], ...]
    stage_manifest_sha256: tuple[Annotated[str, Field(pattern=SHA256_PATTERN)], ...]
    cases: tuple[CaseOutcome, ...]
    metrics: CohortMetrics
    operational_metrics: OperationalMetrics
    reason_codes: tuple[EvaluationReason, ...]
    review_required: bool
    escalation_required: bool
    acceptance_eligible: bool

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> tuple[EvaluationReason, ...]:
        return _ordered_reasons(value)

    @model_validator(mode="after")
    def propagate_case_state_and_bind_digests(self) -> GoldenEvaluationReport:
        ordered_case_digests = tuple(case.candidate_artifact_sha256 for case in self.cases)
        if self.candidate_artifact_sha256 != ordered_case_digests:
            raise ValueError("candidate artifact digests must match case cardinality and order")
        ordered_stage_digests = tuple(case.stage_manifest_sha256 for case in self.cases)
        if self.stage_manifest_sha256 != ordered_stage_digests:
            raise ValueError("stage manifest digests must match case cardinality and order")
        reasons = set(self.reason_codes)
        child_reasons = {reason for case in self.cases for reason in case.reason_codes}
        if reasons != child_reasons:
            raise ValueError("report reason codes must exactly aggregate all case reasons")
        requires_review = bool(reasons) or any(case.review_required for case in self.cases)
        if self.review_required != requires_review:
            raise ValueError("report review state must propagate reasons and case review")
        if self.escalation_required != requires_review:
            raise ValueError("report escalation state must propagate review state")
        if self.acceptance_eligible == requires_review:
            raise ValueError("report acceptance must be the inverse of fail-closed review")
        _validate_report_metrics(self.cases, self.metrics)
        return self


def _json_compatible(value: object) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("canonical JSON cannot encode non-finite decimals")
        return format(value, "f")
    if isinstance(value, dict):
        return {key: _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_compatible(item) for item in value]
    if isinstance(value, (set, frozenset)):
        converted = [_json_compatible(item) for item in value]
        return sorted(
            converted,
            key=lambda item: json.dumps(
                item, ensure_ascii=False, separators=(",", ":"), sort_keys=True
            ),
        )
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize path-independently while retaining every identity-bearing list order."""

    compatible = _json_compatible(value)
    return json.dumps(
        compatible,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()
