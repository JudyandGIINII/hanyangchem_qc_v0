from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from hyc_evaluation.artifacts import (
    CandidateRunArtifact,
    CaseOutcome,
    FieldOutcome,
    GoldenEvaluationReport,
    MissingDetectionCounts,
    StageArtifactManifest,
    canonical_json_bytes,
    canonical_sha256,
)
from hyc_evaluation.runner import build_success_stage_manifest
from hyc_evaluation.schema import GoldenDataset
from hyc_evaluation.scoring import score_candidate_runs


def golden_payload() -> dict[str, Any]:
    return {
        "golden_schema_version": "hyc.golden.v1",
        "dataset_id": "p4a-scoring",
        "dataset_version": "1.0.0",
        "normalization_vocabulary_version": "hyc.normalization.v1",
        "bindings": {
            "fixture_name": "generated-scoring-fixture",
            "fixture_version": "1.0.0",
            "provider_name": "synthetic-fixture",
            "provider_version": "1.0.0",
            "model_version": "not-applicable",
            "parser_version": "1.0.0",
            "prompt_schema_version": "not-applicable",
            "pipeline_version": "1.0.0",
            "stage_contract_version": "1.0.0",
            "runner_version": "1.0.0",
            "scorer_version": "1.0.0",
            "report_version": "1.0.0",
        },
        "cases": [
            {
                "case_id": "case-1",
                "ordering_key": "0001",
                "input": {
                    "source_sha256": "a" * 64,
                    "mime_type": "application/pdf",
                    "document_kind": "supplier-coa",
                    "synthetic": True,
                    "generator": {
                        "name": "hyc-p4a-generator",
                        "version": "1.0.0",
                        "seed": 20260802,
                    },
                    "provenance_marker": "generated-non-sensitive-synthetic",
                },
                "pages": [
                    {
                        "page_id": "page-1",
                        "page_number": 1,
                        "rendered_dpi": 300,
                        "declared_rotation": 0,
                        "detected_rotation": 0,
                        "width": "1000",
                        "height": "1400",
                        "coordinate_system": "pixels",
                        "coordinate_system_version": "1.0",
                    }
                ],
                "expected_fields": [
                    {
                        "identity": {
                            "document_id": "document-1",
                            "section_id": "section-1",
                            "row_id": "row-1",
                            "row_order": 1,
                            "sample_id": None,
                            "sample_order": None,
                        },
                        "field_key": "LOT_NUMBER",
                        "required": True,
                        "ignored": False,
                        "value": {
                            "kind": "lot",
                            "raw": " LOT-01 ",
                            "normalized": "LOT-01",
                            "unit": None,
                        },
                        "geometry": {
                            "page_number": 1,
                            "polygon": [
                                {"x": "100", "y": "200"},
                                {"x": "300", "y": "200"},
                                {"x": "300", "y": "250"},
                                {"x": "100", "y": "250"},
                            ],
                        },
                        "review": {
                            "review_required": False,
                            "reason_codes": [],
                            "handwriting_reference_only": False,
                        },
                        "allowed_normalizations": [
                            {
                                "normalization_id": "lot.trim-upper",
                                "normalization_version": "1.0",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def candidate_payload(dataset: GoldenDataset, case_index: int = 0) -> dict[str, Any]:
    case = dataset.cases[case_index]
    expected = case.expected_fields[0]
    manifest = build_success_stage_manifest(case)
    return {
        "artifact_schema_version": "hyc.candidate-run.v1",
        "golden_schema_version": dataset.golden_schema_version,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.dataset_version,
        "dataset_sha256": canonical_sha256(dataset),
        "case_id": case.case_id,
        "input_sha256": case.input.source_sha256,
        "provider_name": "synthetic-fixture",
        "document_kind": case.input.document_kind,
        "bindings": dataset.bindings.model_dump(mode="json"),
        "stage_manifest": manifest.model_dump(mode="json"),
        "stage_manifest_sha256": canonical_sha256(manifest),
        "final_stage_artifact_ref": manifest.stages[-1].artifact_ref,
        "values": [
            {
                "candidate_order": 1,
                "identity": expected.identity.model_dump(mode="json"),
                "field_key": expected.field_key,
                "value": expected.value.model_dump(mode="json"),
                "geometry": expected.geometry.model_dump(mode="json"),
                "applied_normalizations": [
                    binding.model_dump(mode="json") for binding in expected.allowed_normalizations
                ],
                "confidence": "1",
                "reason_codes": [],
                "handwriting_reference_only": False,
                "review_required": False,
            }
        ],
        "reason_codes": [],
        "review_required": False,
        "escalation_required": False,
    }


def artifact_for(dataset_payload: dict[str, Any]) -> tuple[GoldenDataset, dict[str, Any]]:
    dataset = GoldenDataset.model_validate(dataset_payload)
    return dataset, candidate_payload(dataset)


def set_review_reasons(payload: dict[str, Any], *reasons: str) -> None:
    ordered = list(reasons)
    payload["reason_codes"] = ordered
    payload["review_required"] = bool(ordered)
    payload["escalation_required"] = bool(ordered)


def set_value_review_reasons(value: dict[str, Any], *reasons: str) -> None:
    value["reason_codes"] = list(reasons)
    value["review_required"] = bool(reasons)
    value["handwriting_reference_only"] = "HANDWRITING_REFERENCE_ONLY" in reasons


def test_golden_schema_to_candidate_pass_records_exact_counts() -> None:
    dataset, payload = artifact_for(golden_payload())
    artifact = CandidateRunArtifact.model_validate(payload)

    report = score_candidate_runs(dataset, [artifact])

    assert isinstance(report, GoldenEvaluationReport)
    assert report.provider_name == "synthetic-fixture"
    assert report.acceptance_eligible is True
    assert report.review_required is False
    assert report.escalation_required is False
    assert report.metrics.exact_field_match.numerator == 1
    assert report.metrics.exact_field_match.denominator == 1
    assert report.metrics.exact_field_match.value == Decimal("1")
    assert report.metrics.normalized_field_match.numerator == 1
    assert report.metrics.normalized_field_match.denominator == 1
    assert report.metrics.excluded_reference_count == 0
    assert report.metrics.row_precision.numerator == 1
    assert report.metrics.row_precision.denominator == 1
    assert report.metrics.row_recall.numerator == 1
    assert report.metrics.missing_detection.true_negative == 1
    assert report.cases[0].fields[0].outcome == "MATCH"
    assert canonical_json_bytes(report) == canonical_json_bytes(report)
    assert canonical_sha256(report) == canonical_sha256(report)


def test_canonical_bytes_and_digest_repeat_across_cwd_env_and_object_key_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    dataset, payload = artifact_for(golden_payload())
    payload["reason_codes"] = ["UNMAPPED", "LOW_CONFIDENCE"]
    payload["review_required"] = True
    payload["escalation_required"] = True
    payload["values"][0]["reason_codes"] = ["UNMAPPED", "LOW_CONFIDENCE"]
    payload["values"][0]["review_required"] = True
    payload["values"][0]["confidence"] = "0.75"
    artifact = CandidateRunArtifact.model_validate(payload)
    reversed_payload = dict(reversed(list(payload.items())))
    reversed_artifact = CandidateRunArtifact.model_validate(reversed_payload)

    first_bytes = canonical_json_bytes(artifact)
    first_digest = canonical_sha256(artifact)
    first_report = score_candidate_runs(dataset, [artifact])
    first_report_bytes = canonical_json_bytes(first_report)
    first_report_digest = canonical_sha256(first_report)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    monkeypatch.setenv("LC_ALL", "C")

    assert artifact.reason_codes == ("LOW_CONFIDENCE", "UNMAPPED")
    assert artifact.values[0].reason_codes == ("LOW_CONFIDENCE", "UNMAPPED")
    assert canonical_json_bytes(artifact) == first_bytes
    assert canonical_json_bytes(reversed_artifact) == first_bytes
    assert canonical_sha256(artifact) == first_digest
    assert canonical_sha256(reversed_artifact) == first_digest
    assert canonical_sha256(dataset) == payload["dataset_sha256"]
    second_report = score_candidate_runs(dataset, [reversed_artifact])
    assert canonical_json_bytes(second_report) == first_report_bytes
    assert canonical_sha256(second_report) == first_report_digest


def test_semantically_unordered_golden_reasons_have_one_dataset_digest() -> None:
    first = golden_payload()
    first_review = first["cases"][0]["expected_fields"][0]["review"]
    first_review.update(
        review_required=True,
        reason_codes=["LOW_CONFIDENCE", "LOGIC_CONFLICT"],
    )
    second = deepcopy(first)
    second["cases"][0]["expected_fields"][0]["review"]["reason_codes"].reverse()

    first_dataset = GoldenDataset.model_validate(first)
    second_dataset = GoldenDataset.model_validate(second)

    assert first_dataset.cases[0].expected_fields[0].review.reason_codes == [
        "LOGIC_CONFLICT",
        "LOW_CONFIDENCE",
    ]
    assert canonical_json_bytes(first_dataset) == canonical_json_bytes(second_dataset)
    assert canonical_sha256(first_dataset) == canonical_sha256(second_dataset)


@pytest.mark.parametrize(
    ("kind", "golden_raw", "candidate_raw", "normalized", "normalization_id"),
    [
        ("header", " Test Header ", "test header", "TEST HEADER", "text.upper"),
        ("date", "02/08/2026", "2026-08-02", "2026-08-02", "date.iso8601"),
        ("lot", " lot-01 ", "LOT-01", "LOT-01", "lot.trim-upper"),
        ("unit", "㎎/L", "mg/L", "mg/L", "unit.alias"),
        ("text", "ＡＢＣ ", "ABC", "ABC", "text.nfkc"),
        ("decimal", "75.500", "75.50", "75.500", "decimal.canonical"),
    ],
)
def test_each_value_kind_uses_separate_raw_and_normalized_exact_comparison(
    kind: str,
    golden_raw: str,
    candidate_raw: str,
    normalized: str,
    normalization_id: str,
) -> None:
    golden = golden_payload()
    expected = golden["cases"][0]["expected_fields"][0]
    expected["value"] = {
        "kind": kind,
        "raw": golden_raw,
        "normalized": normalized,
        "unit": None,
    }
    expected["allowed_normalizations"] = [
        {"normalization_id": normalization_id, "normalization_version": "1.0"}
    ]
    dataset, payload = artifact_for(golden)
    payload["values"][0]["value"]["raw"] = candidate_raw
    artifact = CandidateRunArtifact.model_validate(payload)

    report = score_candidate_runs(dataset, [artifact])
    kind_metric = next(metric for metric in report.metrics.by_kind if metric.kind == kind)

    assert report.metrics.exact_field_match.numerator == 0
    assert report.metrics.normalized_field_match.numerator == 1
    assert kind_metric.exact.numerator == 0
    assert kind_metric.normalized.numerator == 1


def test_low_confidence_fails_closed_and_propagates_review() -> None:
    dataset, payload = artifact_for(golden_payload())
    value = payload["values"][0]
    value["confidence"] = "0.75"
    set_value_review_reasons(value, "LOW_CONFIDENCE")
    set_review_reasons(payload, "LOW_CONFIDENCE")

    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])

    assert report.acceptance_eligible is False
    assert report.review_required is True
    assert report.escalation_required is True
    assert report.reason_codes == ("LOW_CONFIDENCE",)
    assert report.cases[0].fields[0].reason_codes == ("LOW_CONFIDENCE",)


def test_missing_required_field_fails_closed_with_exact_denominator() -> None:
    dataset, payload = artifact_for(golden_payload())
    payload["values"] = []
    artifact = CandidateRunArtifact.model_validate(payload)

    report = score_candidate_runs(dataset, [artifact])

    assert report.acceptance_eligible is False
    assert report.reason_codes == ("MISSING_REQUIRED",)
    assert report.metrics.exact_field_match.numerator == 0
    assert report.metrics.exact_field_match.denominator == 1
    assert report.metrics.missing_required.numerator == 1
    assert report.metrics.missing_required.denominator == 1
    assert report.cases[0].fields[0].outcome == "MISSING_REQUIRED"


def test_duplicate_and_unmapped_fields_are_not_greedily_matched() -> None:
    dataset, duplicate_payload = artifact_for(golden_payload())
    duplicate = deepcopy(duplicate_payload["values"][0])
    duplicate["candidate_order"] = 2
    set_value_review_reasons(duplicate_payload["values"][0], "DUPLICATE_FIELD")
    set_value_review_reasons(duplicate, "DUPLICATE_FIELD")
    duplicate_payload["values"].append(duplicate)
    set_review_reasons(duplicate_payload, "DUPLICATE_FIELD")
    duplicate_report = score_candidate_runs(
        dataset, [CandidateRunArtifact.model_validate(duplicate_payload)]
    )

    assert duplicate_report.acceptance_eligible is False
    assert duplicate_report.reason_codes == ("DUPLICATE_FIELD",)
    assert duplicate_report.metrics.exact_field_match.numerator == 0
    assert duplicate_report.cases[0].fields[0].outcome == "DUPLICATE_FIELD"
    assert duplicate_report.cases[0].fields[0].candidate_orders == (1, 2)

    _, unmapped_payload = artifact_for(golden_payload())
    unmapped_payload["values"][0]["field_key"] = "UNMAPPED_VALUE"
    unmapped_report = score_candidate_runs(
        dataset, [CandidateRunArtifact.model_validate(unmapped_payload)]
    )

    assert unmapped_report.acceptance_eligible is False
    assert unmapped_report.reason_codes == ("MISSING_REQUIRED", "UNMAPPED")
    assert [field.outcome for field in unmapped_report.cases[0].fields] == [
        "MISSING_REQUIRED",
        "UNMAPPED",
    ]


def test_logic_conflict_is_a_candidate_only_signal_that_forces_escalation() -> None:
    dataset, payload = artifact_for(golden_payload())
    set_value_review_reasons(payload["values"][0], "LOGIC_CONFLICT")
    set_review_reasons(payload, "LOGIC_CONFLICT")

    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])

    assert report.metrics.normalized_field_match.numerator == 1
    assert report.acceptance_eligible is False
    assert report.escalation_required is True
    assert report.cases[0].fields[0].outcome == "LOGIC_CONFLICT"
    assert report.metrics.unmapped_field_count == 0


def test_handwriting_is_reference_only_excluded_and_never_acceptance_eligible() -> None:
    golden = golden_payload()
    expected = golden["cases"][0]["expected_fields"][0]
    expected["review"] = {
        "review_required": True,
        "reason_codes": ["HANDWRITING_REFERENCE_ONLY"],
        "handwriting_reference_only": True,
    }
    dataset, payload = artifact_for(golden)
    set_value_review_reasons(payload["values"][0], "HANDWRITING_REFERENCE_ONLY")
    set_review_reasons(payload, "HANDWRITING_REFERENCE_ONLY")

    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])

    assert report.acceptance_eligible is False
    assert report.metrics.exact_field_match.denominator == 0
    assert report.metrics.exact_field_match.value is None
    assert report.metrics.excluded_reference_count == 1
    assert report.cases[0].fields[0].outcome == "HANDWRITING_REFERENCE_ONLY"


def test_unapproved_normalization_fails_closed_even_when_values_match() -> None:
    dataset, payload = artifact_for(golden_payload())
    payload["values"][0]["applied_normalizations"] = [
        {"normalization_id": "text.upper", "normalization_version": "1.0"}
    ]

    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])

    assert report.acceptance_eligible is False
    assert report.metrics.normalized_field_match.numerator == 0
    assert report.reason_codes == ("UNAPPROVED_NORMALIZATION",)
    assert report.metrics.exact_field_match.error_count == 0
    assert report.metrics.normalized_field_match.error_count == 1


def test_artifact_schema_is_strict_synthetic_only_version_bound_and_frozen() -> None:
    dataset, payload = artifact_for(golden_payload())

    for field, invalid in (
        ("provider_name", "external-provider"),
        ("artifact_schema_version", "hyc.candidate-run.v2"),
        ("dataset_sha256", "not-a-digest"),
    ):
        invalid_payload = deepcopy(payload)
        invalid_payload[field] = invalid
        with pytest.raises(ValidationError):
            CandidateRunArtifact.model_validate(invalid_payload)

    invalid_payload = deepcopy(payload)
    invalid_payload["unexpected"] = "forbidden"
    with pytest.raises(ValidationError):
        CandidateRunArtifact.model_validate(invalid_payload)

    artifact = CandidateRunArtifact.model_validate(payload)
    with pytest.raises(ValidationError):
        artifact.dataset_sha256 = "b" * 64

    report = score_candidate_runs(dataset, [artifact])
    with pytest.raises(ValidationError):
        report.review_required = True


def test_generated_artifact_and_report_json_schemas_are_strict_and_valid() -> None:
    dataset, payload = artifact_for(golden_payload())
    artifact = CandidateRunArtifact.model_validate(payload)
    report = score_candidate_runs(dataset, [artifact])

    for model, instance in (
        (CandidateRunArtifact, artifact),
        (GoldenEvaluationReport, report),
    ):
        schema = model.model_json_schema()
        Draft202012Validator.check_schema(schema)
        assert not list(Draft202012Validator(schema).iter_errors(instance.model_dump(mode="json")))
        assert schema["additionalProperties"] is False
        for definition in schema["$defs"].values():
            if "properties" in definition:
                assert definition["additionalProperties"] is False


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(review_required=True),
        lambda payload: payload.update(escalation_required=True),
        lambda payload: payload.update(outcome="LOW_CONFIDENCE"),
        lambda payload: payload.update(
            reason_codes=["LOW_CONFIDENCE"],
            review_required=True,
            escalation_required=True,
            outcome="MATCH",
        ),
        lambda payload: payload.update(
            reason_codes=["HANDWRITING_REFERENCE_ONLY"],
            review_required=True,
            escalation_required=True,
            outcome="HANDWRITING_REFERENCE_ONLY",
            excluded_reference_only=False,
        ),
    ],
)
def test_field_outcome_rejects_contradictory_fail_closed_state(
    mutator: Any,
) -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    field_payload = report.cases[0].fields[0].model_dump(mode="json")
    mutator(field_payload)

    with pytest.raises(ValidationError):
        FieldOutcome.model_validate_json(json.dumps(field_payload))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(exact_match=True, normalized_match=False),
        lambda payload: payload.update(
            exact_match=False,
            normalized_match=True,
            outcome="MISMATCH",
            reason_codes=["VALUE_MISMATCH"],
            review_required=True,
            escalation_required=True,
        ),
        lambda payload: payload.update(
            page_number_match=False,
            outcome="MISMATCH",
            reason_codes=["PAGE_MISMATCH"],
            review_required=True,
            escalation_required=True,
        ),
        lambda payload: payload.update(candidate_orders=[], candidate_value_missing=True),
        lambda payload: payload.update(exact_match=None),
    ],
)
def test_field_outcome_rejects_tampered_match_and_evidence_invariants(
    mutator: Any,
) -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    field_payload = report.cases[0].fields[0].model_dump(mode="json")
    mutator(field_payload)
    with pytest.raises(ValidationError):
        FieldOutcome.model_validate(field_payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(review_required=True),
        lambda payload: payload.update(escalation_required=True),
        lambda payload: payload.update(acceptance_eligible=False),
    ],
)
def test_case_outcome_rejects_contradictory_terminal_state(mutator: Any) -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    case_payload = report.cases[0].model_dump(mode="json")
    mutator(case_payload)

    with pytest.raises(ValidationError):
        CaseOutcome.model_validate_json(json.dumps(case_payload))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["metrics"]["exact_field_match"].update(
            numerator=999, denominator=1000, value="0.999"
        ),
        lambda payload: payload["metrics"].update(duplicate_field_count=77),
        lambda payload: payload["metrics"]["polygon_iou"].clear(),
    ],
)
def test_case_outcome_rejects_tampered_derivable_metrics(mutator: Any) -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    case_payload = report.cases[0].model_dump(mode="json")
    mutator(case_payload)
    with pytest.raises(ValidationError):
        CaseOutcome.model_validate(case_payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(review_required=True),
        lambda payload: payload.update(escalation_required=True),
        lambda payload: payload.update(acceptance_eligible=False),
        lambda payload: payload.update(
            reason_codes=["LOW_CONFIDENCE"],
            review_required=True,
            escalation_required=True,
            acceptance_eligible=False,
        ),
    ],
)
def test_report_rejects_contradictory_terminal_state(mutator: Any) -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    report_payload = report.model_dump(mode="json")
    mutator(report_payload)

    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate_json(json.dumps(report_payload))


def test_report_rejects_metrics_that_do_not_aggregate_valid_cases() -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    report_payload = report.model_dump(mode="json")
    report_payload["metrics"]["exact_field_match"].update(
        numerator=1,
        denominator=2,
        value="0.5",
    )
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate(report_payload)


def test_case_and_report_reason_codes_must_propagate_child_reasons() -> None:
    dataset, payload = artifact_for(golden_payload())
    set_value_review_reasons(payload["values"][0], "LOW_CONFIDENCE")
    payload["values"][0]["confidence"] = "0.75"
    set_review_reasons(payload, "LOW_CONFIDENCE")
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])

    case_payload = report.cases[0].model_dump(mode="json")
    case_payload["reason_codes"] = []
    case_payload["review_required"] = False
    case_payload["escalation_required"] = False
    case_payload["acceptance_eligible"] = True
    with pytest.raises(ValidationError):
        CaseOutcome.model_validate_json(json.dumps(case_payload))

    report_payload = report.model_dump(mode="json")
    report_payload["reason_codes"] = []
    report_payload["review_required"] = False
    report_payload["escalation_required"] = False
    report_payload["acceptance_eligible"] = True
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate_json(json.dumps(report_payload))


def test_missing_detection_precision_and_recall_must_match_confusion_counts() -> None:
    dataset, payload = artifact_for(golden_payload())
    report = score_candidate_runs(dataset, [CandidateRunArtifact.model_validate(payload)])
    missing_payload = report.metrics.missing_detection.model_dump(mode="json")
    missing_payload["precision"] = {
        "numerator": 1,
        "denominator": 1,
        "value": "1",
        "excluded_reference_count": 0,
        "excluded_ignored_count": 0,
        "error_count": 0,
    }

    with pytest.raises(ValidationError):
        MissingDetectionCounts.model_validate_json(json.dumps(missing_payload))

    missing_payload = report.metrics.missing_detection.model_dump(mode="json")
    missing_payload["false_positive"] = 1
    with pytest.raises(ValidationError):
        MissingDetectionCounts.model_validate_json(json.dumps(missing_payload))

    missing_payload = report.metrics.missing_detection.model_dump(mode="json")
    missing_payload["recall"] = {
        "numerator": 1,
        "denominator": 1,
        "value": "1",
        "excluded_reference_count": 0,
        "excluded_ignored_count": 0,
        "error_count": 0,
    }
    with pytest.raises(ValidationError):
        MissingDetectionCounts.model_validate_json(json.dumps(missing_payload))


def test_report_candidate_digest_cardinality_and_case_order_are_bound() -> None:
    golden = golden_payload()
    second_case = deepcopy(golden["cases"][0])
    second_case["case_id"] = "case-2"
    second_case["ordering_key"] = "0002"
    second_case["input"]["source_sha256"] = "b" * 64
    second_case["expected_fields"][0]["identity"]["document_id"] = "document-2"
    golden["cases"].append(second_case)
    dataset = GoldenDataset.model_validate(golden)
    artifacts = [
        CandidateRunArtifact.model_validate(candidate_payload(dataset, 0)),
        CandidateRunArtifact.model_validate(candidate_payload(dataset, 1)),
    ]
    report = score_candidate_runs(dataset, artifacts)
    report_payload = report.model_dump(mode="json")

    missing_digest = deepcopy(report_payload)
    missing_digest["candidate_artifact_sha256"].pop()
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate_json(json.dumps(missing_digest))

    reversed_digests = deepcopy(report_payload)
    reversed_digests["candidate_artifact_sha256"].reverse()
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate_json(json.dumps(reversed_digests))


def test_missing_duplicate_and_unknown_candidate_artifacts_fail_stably() -> None:
    dataset, payload = artifact_for(golden_payload())
    artifact = CandidateRunArtifact.model_validate(payload)

    with pytest.raises(ValueError, match="missing candidate artifact"):
        score_candidate_runs(dataset, [])
    with pytest.raises(ValueError, match="unique per case"):
        score_candidate_runs(dataset, [artifact, artifact])

    unknown_payload = deepcopy(payload)
    unknown_payload["case_id"] = "unknown-case"
    unknown_payload["stage_manifest"]["case_id"] = "unknown-case"
    unknown_manifest = StageArtifactManifest.model_validate(unknown_payload["stage_manifest"])
    unknown_payload["stage_manifest_sha256"] = canonical_sha256(unknown_manifest)
    unknown = CandidateRunArtifact.model_validate(unknown_payload)
    with pytest.raises(ValueError, match="unknown cases"):
        score_candidate_runs(dataset, [artifact, unknown])
