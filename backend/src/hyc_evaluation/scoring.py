from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

from hyc_evaluation.artifacts import (
    CandidateRunArtifact,
    CandidateValue,
    CaseOutcome,
    CohortMetrics,
    EvaluationReason,
    FieldOutcome,
    FieldOutcomeName,
    GoldenEvaluationReport,
    KindMetrics,
    MetricCount,
    MissingDetectionCounts,
    NotApplicableMetric,
    OperationalMetrics,
    PolygonIoUEvidence,
    canonical_sha256,
)
from hyc_evaluation.schema import (
    GoldenCase,
    GoldenDataset,
    GoldenExpectedField,
    GoldenGeometry,
    ValueKind,
)

FieldKey = tuple[str, str, str, str | None, str]
KIND_ORDER: tuple[ValueKind, ...] = ("header", "date", "lot", "unit", "text", "decimal")
SCORING_DECIMAL_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


@dataclass
class _Counts:
    document_classification_numerator: int = 0
    document_classification_denominator: int = 0
    exact_numerator: int = 0
    normalized_numerator: int = 0
    denominator: int = 0
    required_missing: int = 0
    required_denominator: int = 0
    excluded_reference: int = 0
    excluded_ignored: int = 0
    duplicates: int = 0
    unmapped: int = 0
    logic_conflicts: int = 0
    low_confidence: int = 0
    errors: int = 0
    exact_errors: int = 0
    normalized_errors: int = 0
    missing_true_positive: int = 0
    missing_false_positive: int = 0
    missing_false_negative: int = 0
    missing_true_negative: int = 0
    row_true_positive: int = 0
    row_false_positive: int = 0
    row_false_negative: int = 0
    page_number_numerator: int = 0
    page_number_denominator: int = 0
    page_mismatches: int = 0
    missing_polygons: int = 0
    invalid_polygons: int = 0
    polygon_iou: list[PolygonIoUEvidence] = field(default_factory=list)

    def add(self, other: _Counts) -> None:
        for name in self.__dataclass_fields__:
            if name == "polygon_iou":
                self.polygon_iou.extend(other.polygon_iou)
            else:
                setattr(self, name, getattr(self, name) + getattr(other, name))


def _polygon_area(vertices: list[tuple[Decimal, Decimal]]) -> Decimal:
    with localcontext(SCORING_DECIMAL_CONTEXT):
        return abs(
            sum(
                (
                    x1 * y2 - x2 * y1
                    for (x1, y1), (x2, y2) in zip(
                        vertices,
                        vertices[1:] + vertices[:1],
                        strict=True,
                    )
                ),
                Decimal("0"),
            )
        ) / Decimal("2")


def _line_intersection(
    first: tuple[Decimal, Decimal],
    second: tuple[Decimal, Decimal],
    clip_first: tuple[Decimal, Decimal],
    clip_second: tuple[Decimal, Decimal],
) -> tuple[Decimal, Decimal]:
    with localcontext(SCORING_DECIMAL_CONTEXT):
        x1, y1 = first
        x2, y2 = second
        x3, y3 = clip_first
        x4, y4 = clip_second
        denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
        if denominator == 0:
            return second
        first_cross = x1 * y2 - y1 * x2
        clip_cross = x3 * y4 - y3 * x4
        return (
            (first_cross * (x3 - x4) - (x1 - x2) * clip_cross) / denominator,
            (first_cross * (y3 - y4) - (y1 - y2) * clip_cross) / denominator,
        )


def _polygon_intersection(
    subject: list[tuple[Decimal, Decimal]],
    clip: list[tuple[Decimal, Decimal]],
) -> list[tuple[Decimal, Decimal]]:
    with localcontext(SCORING_DECIMAL_CONTEXT):
        output = subject
        signed_area = sum(
            (
                x1 * y2 - x2 * y1
                for (x1, y1), (x2, y2) in zip(
                    clip,
                    clip[1:] + clip[:1],
                    strict=True,
                )
            ),
            Decimal("0"),
        )
        orientation = Decimal("1") if signed_area > 0 else Decimal("-1")
        for clip_first, clip_second in zip(clip, clip[1:] + clip[:1], strict=True):
            incoming = output
            output = []
            if not incoming:
                break

            def inside(
                point: tuple[Decimal, Decimal],
                edge_start: tuple[Decimal, Decimal] = clip_first,
                edge_end: tuple[Decimal, Decimal] = clip_second,
            ) -> bool:
                return (
                    orientation
                    * (
                        (edge_end[0] - edge_start[0]) * (point[1] - edge_start[1])
                        - (edge_end[1] - edge_start[1]) * (point[0] - edge_start[0])
                    )
                    >= 0
                )

            previous = incoming[-1]
            previous_inside = inside(previous)
            for current in incoming:
                current_inside = inside(current)
                if current_inside:
                    if not previous_inside:
                        output.append(
                            _line_intersection(
                                previous,
                                current,
                                clip_first,
                                clip_second,
                            )
                        )
                    output.append(current)
                elif previous_inside:
                    output.append(
                        _line_intersection(
                            previous,
                            current,
                            clip_first,
                            clip_second,
                        )
                    )
                previous = current
                previous_inside = current_inside
        return output


def _polygon_iou(expected: GoldenGeometry, predicted: GoldenGeometry) -> Decimal:
    with localcontext(SCORING_DECIMAL_CONTEXT):
        expected_vertices = [(point.x, point.y) for point in expected.polygon]
        predicted_vertices = [(point.x, point.y) for point in predicted.polygon]
        expected_area = _polygon_area(expected_vertices)
        predicted_area = _polygon_area(predicted_vertices)
        intersection_area = _polygon_area(
            _polygon_intersection(expected_vertices, predicted_vertices)
        )
        union_area = expected_area + predicted_area - intersection_area
        if union_area <= 0:
            raise ValueError("polygon union must have positive area")
        return intersection_area / union_area


def _field_key(field: GoldenExpectedField | CandidateValue) -> FieldKey:
    identity = field.identity
    return (
        identity.document_id,
        identity.section_id,
        identity.row_id,
        identity.sample_id,
        field.field_key,
    )


def _metric(
    numerator: int,
    denominator: int,
    *,
    excluded_reference: int = 0,
    excluded_ignored: int = 0,
    errors: int = 0,
) -> MetricCount:
    value: Decimal | None = None
    if denominator:
        with localcontext(SCORING_DECIMAL_CONTEXT):
            value = Decimal(numerator) / Decimal(denominator)
    return MetricCount(
        numerator=numerator,
        denominator=denominator,
        value=value,
        excluded_reference_count=excluded_reference,
        excluded_ignored_count=excluded_ignored,
        error_count=errors,
    )


def _cohort_metrics(counts: _Counts, kinds: dict[ValueKind, _Counts]) -> CohortMetrics:
    return CohortMetrics(
        document_classification_exact=_metric(
            counts.document_classification_numerator,
            counts.document_classification_denominator,
        ),
        exact_field_match=_metric(
            counts.exact_numerator,
            counts.denominator,
            excluded_reference=counts.excluded_reference,
            excluded_ignored=counts.excluded_ignored,
            errors=counts.exact_errors,
        ),
        normalized_field_match=_metric(
            counts.normalized_numerator,
            counts.denominator,
            excluded_reference=counts.excluded_reference,
            excluded_ignored=counts.excluded_ignored,
            errors=counts.normalized_errors,
        ),
        missing_required=_metric(
            counts.required_missing,
            counts.required_denominator,
            excluded_reference=counts.excluded_reference,
            excluded_ignored=counts.excluded_ignored,
        ),
        missing_detection=MissingDetectionCounts(
            true_positive=counts.missing_true_positive,
            false_positive=counts.missing_false_positive,
            false_negative=counts.missing_false_negative,
            true_negative=counts.missing_true_negative,
            precision=_metric(
                counts.missing_true_positive,
                counts.missing_true_positive + counts.missing_false_positive,
            ),
            recall=_metric(
                counts.missing_true_positive,
                counts.missing_true_positive + counts.missing_false_negative,
            ),
        ),
        row_precision=_metric(
            counts.row_true_positive,
            counts.row_true_positive + counts.row_false_positive,
        ),
        row_recall=_metric(
            counts.row_true_positive,
            counts.row_true_positive + counts.row_false_negative,
        ),
        page_number_exact=_metric(
            counts.page_number_numerator,
            counts.page_number_denominator,
            excluded_reference=counts.excluded_reference,
            excluded_ignored=counts.excluded_ignored,
            errors=counts.duplicates,
        ),
        polygon_iou=tuple(counts.polygon_iou),
        by_kind=tuple(
            KindMetrics(
                kind=kind,
                exact=_metric(
                    kinds.get(kind, _Counts()).exact_numerator,
                    kinds.get(kind, _Counts()).denominator,
                    excluded_reference=kinds.get(kind, _Counts()).excluded_reference,
                    excluded_ignored=kinds.get(kind, _Counts()).excluded_ignored,
                    errors=kinds.get(kind, _Counts()).exact_errors,
                ),
                normalized=_metric(
                    kinds.get(kind, _Counts()).normalized_numerator,
                    kinds.get(kind, _Counts()).denominator,
                    excluded_reference=kinds.get(kind, _Counts()).excluded_reference,
                    excluded_ignored=kinds.get(kind, _Counts()).excluded_ignored,
                    errors=kinds.get(kind, _Counts()).normalized_errors,
                ),
            )
            for kind in KIND_ORDER
        ),
        excluded_reference_count=counts.excluded_reference,
        excluded_ignored_count=counts.excluded_ignored,
        duplicate_field_count=counts.duplicates,
        unmapped_field_count=counts.unmapped,
        logic_conflict_count=counts.logic_conflicts,
        low_confidence_count=counts.low_confidence,
        page_mismatch_count=counts.page_mismatches,
        missing_polygon_count=0,
        invalid_polygon_count=0,
    )


def _outcome_name(reasons: set[EvaluationReason]) -> FieldOutcomeName:
    for reason, outcome in (
        ("HANDWRITING_REFERENCE_ONLY", "HANDWRITING_REFERENCE_ONLY"),
        ("DUPLICATE_FIELD", "DUPLICATE_FIELD"),
        ("MISSING_REQUIRED", "MISSING_REQUIRED"),
        ("UNMAPPED", "UNMAPPED"),
        ("LOGIC_CONFLICT", "LOGIC_CONFLICT"),
        ("LOW_CONFIDENCE", "LOW_CONFIDENCE"),
    ):
        if reason in reasons:
            return outcome  # type: ignore[return-value]
    return "MISMATCH" if reasons else "MATCH"


def _case_binding_reasons(
    dataset: GoldenDataset,
    case: GoldenCase,
    artifact: CandidateRunArtifact,
) -> set[EvaluationReason]:
    if (
        artifact.golden_schema_version != dataset.golden_schema_version
        or artifact.dataset_id != dataset.dataset_id
        or artifact.dataset_version != dataset.dataset_version
        or artifact.dataset_sha256 != canonical_sha256(dataset)
        or artifact.case_id != case.case_id
        or artifact.input_sha256 != case.input.source_sha256
        or artifact.bindings != dataset.bindings
        or artifact.provider_name != "synthetic-fixture"
    ):
        return {"BINDING_MISMATCH"}
    return set()


def _score_case(
    dataset: GoldenDataset,
    case: GoldenCase,
    artifact: CandidateRunArtifact,
) -> tuple[CaseOutcome, _Counts, dict[ValueKind, _Counts]]:
    counts = _Counts()
    kinds: dict[ValueKind, _Counts] = defaultdict(_Counts)
    fields: list[FieldOutcome] = []
    case_reasons = set(artifact.reason_codes) | _case_binding_reasons(dataset, case, artifact)
    binding_failed = "BINDING_MISMATCH" in case_reasons
    counts.document_classification_denominator = 1
    if artifact.document_kind == case.input.document_kind:
        counts.document_classification_numerator = 1
    else:
        case_reasons.add("DOCUMENT_CLASSIFICATION_MISMATCH")
    predictions: dict[FieldKey, list[CandidateValue]] = defaultdict(list)
    if not binding_failed:
        for candidate in artifact.values:
            predictions[_field_key(candidate)].append(candidate)

    expected_rows = {
        (
            field.identity.document_id,
            field.identity.section_id,
            field.identity.row_id,
        )
        for field in case.expected_fields
        if not field.ignored and not field.review.handwriting_reference_only
    }
    predicted_rows = (
        {
            (
                value.identity.document_id,
                value.identity.section_id,
                value.identity.row_id,
            )
            for value in artifact.values
            if not value.handwriting_reference_only
        }
        if not binding_failed
        else set()
    )
    counts.row_true_positive = len(expected_rows & predicted_rows)
    counts.row_false_positive = len(predicted_rows - expected_rows)
    counts.row_false_negative = len(expected_rows - predicted_rows)

    expected_keys = {_field_key(expected) for expected in case.expected_fields}
    for expected_order, expected in enumerate(case.expected_fields, start=1):
        kind_counts = kinds[expected.value.kind]
        key = _field_key(expected)
        candidates = predictions.get(key, [])
        reasons: set[EvaluationReason] = set(expected.review.reason_codes)
        exact_match: bool | None = None
        normalized_match: bool | None = None
        page_number_match: bool | None = None
        polygon_iou: Decimal | None = None
        excluded_reference = expected.review.handwriting_reference_only
        expected_value_missing = expected.value.raw is None
        candidate_value_missing = not candidates or (
            len(candidates) == 1
            and (
                candidates[0].value.raw is None
                or "MISSING_REQUIRED" in candidates[0].reason_codes
            )
        )

        if expected.ignored:
            counts.excluded_ignored += 1
            kind_counts.excluded_ignored += 1
        elif excluded_reference:
            counts.excluded_reference += 1
            kind_counts.excluded_reference += 1
            reasons.add("HANDWRITING_REFERENCE_ONLY")
        else:
            counts.denominator += 1
            kind_counts.denominator += 1
            if expected.required:
                counts.required_denominator += 1
                kind_counts.required_denominator += 1
                expected_missing = expected_value_missing
                predicted_missing = candidate_value_missing
                if expected_missing and predicted_missing:
                    counts.missing_true_positive += 1
                    kind_counts.missing_true_positive += 1
                elif not expected_missing and predicted_missing:
                    counts.missing_false_positive += 1
                    kind_counts.missing_false_positive += 1
                elif expected_missing and not predicted_missing:
                    counts.missing_false_negative += 1
                    kind_counts.missing_false_negative += 1
                else:
                    counts.missing_true_negative += 1
                    kind_counts.missing_true_negative += 1
                if predicted_missing:
                    counts.required_missing += 1
                    kind_counts.required_missing += 1

            if len(candidates) > 1:
                reasons.add("DUPLICATE_FIELD")
                counts.duplicates += 1
                kind_counts.duplicates += 1
                counts.errors += 1
                kind_counts.errors += 1
                counts.exact_errors += 1
                kind_counts.exact_errors += 1
                counts.normalized_errors += 1
                kind_counts.normalized_errors += 1
            elif not candidates:
                reasons.add("MISSING_REQUIRED" if expected.required else "VALUE_MISMATCH")
            else:
                candidate = candidates[0]
                reasons.update(candidate.reason_codes)
                expected_normalizations = {
                    (binding.normalization_id, binding.normalization_version)
                    for binding in expected.allowed_normalizations
                }
                applied_normalizations = {
                    (binding.normalization_id, binding.normalization_version)
                    for binding in candidate.applied_normalizations
                }
                if not applied_normalizations.issubset(expected_normalizations):
                    reasons.add("UNAPPROVED_NORMALIZATION")
                    counts.errors += 1
                    kind_counts.errors += 1
                    counts.normalized_errors += 1
                    kind_counts.normalized_errors += 1
                same_kind = candidate.value.kind == expected.value.kind
                raw_exact_match = (
                    same_kind
                    and candidate.value.raw == expected.value.raw
                    and candidate.value.unit == expected.value.unit
                )
                normalized_value_equal = (
                    same_kind
                    and candidate.value.normalized == expected.value.normalized
                    and candidate.value.unit == expected.value.unit
                    and "MISSING_REQUIRED" not in reasons
                )
                normalized_match = (
                    normalized_value_equal and "UNAPPROVED_NORMALIZATION" not in reasons
                )
                exact_match = raw_exact_match and normalized_match
                if exact_match:
                    counts.exact_numerator += 1
                    kind_counts.exact_numerator += 1
                if normalized_match:
                    counts.normalized_numerator += 1
                    kind_counts.normalized_numerator += 1
                if not normalized_value_equal and "MISSING_REQUIRED" not in reasons:
                    reasons.add("VALUE_MISMATCH")
                page_number_match = candidate.geometry.page_number == expected.geometry.page_number
                counts.page_number_denominator += 1
                kind_counts.page_number_denominator += 1
                if page_number_match:
                    counts.page_number_numerator += 1
                    kind_counts.page_number_numerator += 1
                else:
                    reasons.add("PAGE_MISMATCH")
                    counts.page_mismatches += 1
                    kind_counts.page_mismatches += 1
                polygon_iou = (
                    _polygon_iou(expected.geometry, candidate.geometry)
                    if page_number_match
                    else None
                )
                evidence = PolygonIoUEvidence(
                    case_id=case.case_id,
                    identity=expected.identity,
                    field_key=expected.field_key,
                    iou=polygon_iou,
                    error_code=(None if page_number_match else "PAGE_MISMATCH"),
                )
                counts.polygon_iou.append(evidence)
                kind_counts.polygon_iou.append(evidence)

        if "LOGIC_CONFLICT" in reasons:
            counts.logic_conflicts += 1
            kind_counts.logic_conflicts += 1
        if "LOW_CONFIDENCE" in reasons:
            counts.low_confidence += 1
            kind_counts.low_confidence += 1
        case_reasons.update(reasons)
        fields.append(
            FieldOutcome(
                identity=expected.identity,
                field_key=expected.field_key,
                kind=expected.value.kind,
                expected_order=expected_order,
                expected_required=expected.required,
                expected_value_missing=expected_value_missing,
                candidate_value_missing=candidate_value_missing,
                candidate_orders=tuple(candidate.candidate_order for candidate in candidates),
                exact_match=exact_match,
                normalized_match=normalized_match,
                page_number_match=page_number_match,
                polygon_iou=polygon_iou,
                outcome=(
                    "EXCLUDED_IGNORED"
                    if expected.ignored
                    else (
                        "NORMALIZED_MATCH"
                        if not reasons and exact_match is False and normalized_match is True
                        else _outcome_name(reasons)
                    )
                ),
                reason_codes=tuple(reasons),
                review_required=bool(reasons),
                escalation_required=bool(reasons),
                excluded_reference_only=excluded_reference,
                excluded_ignored=expected.ignored,
            )
        )

    for candidate in artifact.values:
        if _field_key(candidate) in expected_keys:
            continue
        unmapped_reasons: set[EvaluationReason] = set(candidate.reason_codes) | {"UNMAPPED"}
        counts.unmapped += 1
        counts.errors += 1
        kinds[candidate.value.kind].unmapped += 1
        kinds[candidate.value.kind].errors += 1
        case_reasons.update(unmapped_reasons)
        fields.append(
            FieldOutcome(
                identity=candidate.identity,
                field_key=candidate.field_key,
                kind=candidate.value.kind,
                expected_order=None,
                expected_required=None,
                expected_value_missing=None,
                candidate_value_missing=candidate.value.raw is None,
                candidate_orders=(candidate.candidate_order,),
                exact_match=None,
                normalized_match=None,
                page_number_match=None,
                polygon_iou=None,
                outcome="UNMAPPED",
                reason_codes=tuple(unmapped_reasons),
                review_required=True,
                escalation_required=True,
                excluded_reference_only=candidate.handwriting_reference_only,
                excluded_ignored=False,
            )
        )

    if binding_failed:
        counts.errors += 1
    case_digest = canonical_sha256(artifact)
    review_required = bool(case_reasons)
    outcome = CaseOutcome(
        case_id=case.case_id,
        ordering_key=case.ordering_key,
        input_sha256=case.input.source_sha256,
        candidate_artifact_sha256=case_digest,
        stage_manifest_sha256=artifact.stage_manifest_sha256,
        fields=tuple(fields),
        metrics=_cohort_metrics(counts, kinds),
        reason_codes=tuple(case_reasons),
        review_required=review_required,
        escalation_required=review_required,
        acceptance_eligible=not review_required,
    )
    return outcome, counts, kinds


def score_candidate_runs(
    dataset: GoldenDataset,
    artifacts: Iterable[CandidateRunArtifact],
) -> GoldenEvaluationReport:
    """Score synthetic artifacts in golden case order; field source order is never sorted."""

    artifacts_by_case: dict[str, CandidateRunArtifact] = {}
    duplicate_case_ids: set[str] = set()
    for artifact_item in artifacts:
        if artifact_item.case_id in artifacts_by_case:
            duplicate_case_ids.add(artifact_item.case_id)
        else:
            artifacts_by_case[artifact_item.case_id] = artifact_item
    if duplicate_case_ids:
        raise ValueError("candidate run artifacts must be unique per case")

    case_outcomes: list[CaseOutcome] = []
    artifact_digests: list[str] = []
    stage_manifest_digests: list[str] = []
    total_counts = _Counts()
    total_kinds: dict[ValueKind, _Counts] = defaultdict(_Counts)
    report_reasons: set[EvaluationReason] = set()
    for case in dataset.cases:
        candidate_artifact = artifacts_by_case.get(case.case_id)
        if candidate_artifact is None:
            raise ValueError(f"missing candidate artifact for case {case.case_id}")
        case_outcome, counts, kinds = _score_case(dataset, case, candidate_artifact)
        case_outcomes.append(case_outcome)
        artifact_digests.append(case_outcome.candidate_artifact_sha256)
        stage_manifest_digests.append(case_outcome.stage_manifest_sha256)
        total_counts.add(counts)
        for kind, kind_counts in kinds.items():
            total_kinds[kind].add(kind_counts)
        report_reasons.update(case_outcome.reason_codes)

    unknown_cases = set(artifacts_by_case) - {case.case_id for case in dataset.cases}
    if unknown_cases:
        raise ValueError("candidate artifacts reference unknown cases")

    review_required = bool(report_reasons)
    return GoldenEvaluationReport(
        report_schema_version="hyc.evaluation-report.v1",
        golden_schema_version=dataset.golden_schema_version,
        candidate_artifact_schema_version="hyc.candidate-run.v1",
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        dataset_sha256=canonical_sha256(dataset),
        provider_name="synthetic-fixture",
        bindings=dataset.bindings,
        candidate_artifact_sha256=tuple(artifact_digests),
        stage_manifest_sha256=tuple(stage_manifest_digests),
        cases=tuple(case_outcomes),
        metrics=_cohort_metrics(total_counts, total_kinds),
        operational_metrics=OperationalMetrics(
            latency=NotApplicableMetric(
                status="NOT_APPLICABLE", reason="P4A_SYNTHETIC_NO_MEASUREMENT"
            ),
            provider_cost=NotApplicableMetric(
                status="NOT_APPLICABLE", reason="P4A_SYNTHETIC_NO_MEASUREMENT"
            ),
            human_correction_time=NotApplicableMetric(
                status="NOT_APPLICABLE", reason="P4A_SYNTHETIC_NO_MEASUREMENT"
            ),
        ),
        reason_codes=tuple(report_reasons),
        review_required=review_required,
        escalation_required=review_required,
        acceptance_eligible=not review_required,
    )
