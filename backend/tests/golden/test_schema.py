from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from decimal import Decimal
from typing import Any

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from hyc_evaluation.normalization import VersionedNormalizationVocabulary
from hyc_evaluation.schema import GoldenDataset


def golden_payload() -> dict[str, Any]:
    return {
        "golden_schema_version": "hyc.golden.v1",
        "dataset_id": "p4a-synthetic-contract",
        "dataset_version": "1.0.0",
        "normalization_vocabulary_version": "hyc.normalization.v1",
        "bindings": {
            "fixture_name": "generated-contract-fixture",
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
                "case_id": "synthetic-decimal",
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
                            "sample_id": "sample-1",
                            "sample_order": 1,
                        },
                        "field_key": "CALCIUM_CHLORIDE_CONTENT",
                        "required": True,
                        "ignored": False,
                        "value": {
                            "kind": "decimal",
                            "raw": "75.50",
                            "normalized": "75.50",
                            "unit": "%",
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
                                "normalization_id": "decimal.canonical",
                                "normalization_version": "1.0",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def normalization_vocabulary_payload() -> dict[str, Any]:
    return {
        "vocabulary_version": "hyc.normalization.v1",
        "normalizations": [
            {"normalization_id": "identity", "normalization_version": "1.0"},
            {
                "normalization_id": "decimal.canonical",
                "normalization_version": "1.0",
            },
            {"normalization_id": "date.iso8601", "normalization_version": "1.0"},
            {"normalization_id": "lot.trim-upper", "normalization_version": "1.0"},
            {"normalization_id": "text.nfkc", "normalization_version": "1.0"},
            {"normalization_id": "text.trim", "normalization_version": "1.0"},
            {"normalization_id": "text.upper", "normalization_version": "1.0"},
            {"normalization_id": "unit.alias", "normalization_version": "1.0"},
        ],
    }


def test_versioned_golden_schema_round_trip_is_strict_and_canonical() -> None:
    dataset = GoldenDataset.model_validate(golden_payload())
    encoded = dataset.model_dump_json()
    restored = GoldenDataset.model_validate_json(encoded)

    assert restored == dataset
    assert restored.cases[0].pages[0].width == Decimal("1000")
    assert restored.cases[0].expected_fields[0].value.normalized == Decimal("75.50")
    assert '"normalized":"75.50"' in encoded


def test_generated_golden_json_schema_is_valid_and_extra_forbid() -> None:
    schema = GoldenDataset.model_json_schema()
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(golden_payload()))
    assert schema["additionalProperties"] is False
    for definition in schema["$defs"].values():
        if "properties" in definition:
            assert definition["additionalProperties"] is False


def test_normalization_vocabulary_is_versioned_strict_and_unique() -> None:
    payload = normalization_vocabulary_payload()
    vocabulary = VersionedNormalizationVocabulary.model_validate(payload)
    assert vocabulary.model_dump(mode="json") == payload

    payload["normalizations"].append(deepcopy(payload["normalizations"][0]))
    with pytest.raises(ValidationError):
        VersionedNormalizationVocabulary.model_validate(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(unexpected="forbidden"),
        lambda payload: payload.pop("vocabulary_version"),
        lambda payload: payload["normalizations"].pop(),
        lambda payload: payload["normalizations"].reverse(),
        lambda payload: payload["normalizations"][0].update(normalization_id="unapproved.magic"),
        lambda payload: payload["normalizations"][0].update(normalization_version="2.0"),
    ],
)
def test_normalization_vocabulary_drift_fails_closed(
    mutator: Callable[[dict[str, Any]], object],
) -> None:
    payload = normalization_vocabulary_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        VersionedNormalizationVocabulary.model_validate(payload)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(unexpected="forbidden"),
        lambda payload: payload["bindings"].pop("runner_version"),
        lambda payload: payload["cases"][0]["input"].update(synthetic=False),
        lambda payload: payload["cases"][0]["input"].pop("generator"),
        lambda payload: payload["cases"][0]["pages"][0].pop("coordinate_system_version"),
        lambda payload: payload["cases"][0]["expected_fields"][0].pop("review"),
    ],
)
def test_missing_bindings_and_extra_or_invalid_fields_fail_closed(
    mutator: Callable[[dict[str, Any]], object],
) -> None:
    payload = golden_payload()
    mutator(payload)

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


@pytest.mark.parametrize(
    "binding_name",
    [
        "fixture_version",
        "provider_version",
        "parser_version",
        "pipeline_version",
        "stage_contract_version",
        "runner_version",
        "scorer_version",
        "report_version",
    ],
)
def test_required_version_bindings_cannot_be_not_applicable(binding_name: str) -> None:
    payload = golden_payload()
    payload["bindings"][binding_name] = "not-applicable"

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_dataset_and_generator_versions_cannot_be_not_applicable() -> None:
    payload = golden_payload()
    payload["dataset_version"] = "not-applicable"
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    payload["cases"][0]["input"]["generator"]["version"] = "not-applicable"
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_duplicate_case_document_field_and_ordering_identities_fail_closed() -> None:
    payload = golden_payload()
    duplicate_case = deepcopy(payload["cases"][0])
    payload["cases"].append(duplicate_case)
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    duplicate_case = deepcopy(payload["cases"][0])
    duplicate_case["case_id"] = "synthetic-second-case"
    duplicate_case["ordering_key"] = "0002"
    payload["cases"].append(duplicate_case)
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    duplicate_field = deepcopy(payload["cases"][0]["expected_fields"][0])
    payload["cases"][0]["expected_fields"].append(duplicate_field)
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    second_field = deepcopy(payload["cases"][0]["expected_fields"][0])
    second_field["identity"]["row_id"] = "row-2"
    second_field["identity"]["sample_id"] = "sample-2"
    second_field["field_key"] = "WATER_INSOLUBLE"
    payload["cases"][0]["expected_fields"].append(second_field)
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


@pytest.mark.parametrize(
    "value",
    [75.5, "NaN", "Infinity", "1e3", "+1", "01", ".5", "1."],
)
def test_binary_float_and_noncanonical_decimal_values_fail_closed(value: object) -> None:
    payload = golden_payload()
    payload["cases"][0]["expected_fields"][0]["value"]["normalized"] = value

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_unknown_or_duplicate_normalization_fails_closed() -> None:
    payload = golden_payload()
    binding = payload["cases"][0]["expected_fields"][0]["allowed_normalizations"][0]
    binding["normalization_id"] = "unapproved.magic"
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    normalizations = payload["cases"][0]["expected_fields"][0]["allowed_normalizations"]
    normalizations.append(deepcopy(normalizations[0]))
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


@pytest.mark.parametrize(
    "polygon",
    [
        [
            {"x": "100", "y": "200"},
            {"x": "200", "y": "200"},
            {"x": "300", "y": "200"},
        ],
        [
            {"x": "100", "y": "200"},
            {"x": "1001", "y": "200"},
            {"x": "1001", "y": "250"},
            {"x": "100", "y": "250"},
        ],
        [
            {"x": "100", "y": "200"},
            {"x": "300", "y": "200"},
            {"x": "300", "y": "1401"},
            {"x": "100", "y": "1401"},
        ],
    ],
)
def test_degenerate_and_out_of_page_polygons_fail_closed(
    polygon: list[dict[str, str]],
) -> None:
    payload = golden_payload()
    payload["cases"][0]["expected_fields"][0]["geometry"]["polygon"] = polygon

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_self_intersecting_polygon_fails_closed() -> None:
    payload = golden_payload()
    payload["cases"][0]["expected_fields"][0]["geometry"]["polygon"] = [
        {"x": "100", "y": "200"},
        {"x": "400", "y": "500"},
        {"x": "100", "y": "450"},
        {"x": "400", "y": "200"},
    ]

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_concave_polygon_is_rejected_for_deterministic_decimal_iou_contract() -> None:
    payload = golden_payload()
    payload["cases"][0]["expected_fields"][0]["geometry"]["polygon"] = [
        {"x": "100", "y": "200"},
        {"x": "300", "y": "200"},
        {"x": "200", "y": "225"},
        {"x": "300", "y": "250"},
        {"x": "100", "y": "250"},
    ]

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


@pytest.mark.parametrize(
    ("kind", "normalized"),
    [
        ("date", "2026-8-2"),
        ("date", "not-a-date"),
        ("lot", ""),
        ("text", ""),
        ("unit", ""),
    ],
)
def test_noncanonical_normalized_strings_fail_closed(kind: str, normalized: str) -> None:
    payload = golden_payload()
    value = payload["cases"][0]["expected_fields"][0]["value"]
    value["kind"] = kind
    value["normalized"] = normalized

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_present_expected_value_requires_raw_and_normalized_pair() -> None:
    payload = golden_payload()
    payload["cases"][0]["expected_fields"][0]["value"]["normalized"] = None

    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)


def test_sample_identity_requires_parent_ordering_and_review_reasons_propagate() -> None:
    payload = golden_payload()
    identity = payload["cases"][0]["expected_fields"][0]["identity"]
    identity.pop("sample_order")
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)

    payload = golden_payload()
    review = payload["cases"][0]["expected_fields"][0]["review"]
    review["reason_codes"] = ["LOW_CONFIDENCE"]
    with pytest.raises(ValidationError):
        GoldenDataset.model_validate(payload)
