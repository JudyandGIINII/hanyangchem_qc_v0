from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from hyc_api.contracts import (
    CANONICAL_DECIMAL_STRING_PATTERN,
    ExtractionCandidate,
    ReviewRequest,
    to_seoul_display,
)


def candidate_payload() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "candidate_id": "123e4567-e89b-12d3-a456-426614174000",
        "created_at": "2026-07-31T00:00:00Z",
        "document": {
            "document_id": "123e4567-e89b-12d3-a456-426614174001",
            "source_reference": "synthetic://fixture/document",
            "page_number": 1,
            "bbox": {"left": 0.0, "top": 0.0, "right": 10.0, "bottom": 10.0},
        },
        "provider_name": "synthetic-fixture",
        "values": [
            {
                "item_key": "SYNTHETIC_VALUE",
                "raw_text": "TEST_FIXTURE_VALUE",
                "normalized_value": "12.30",
                "unit": "mg/L",
                "provenance": {
                    "document_id": "123e4567-e89b-12d3-a456-426614174001",
                    "source_reference": "synthetic://fixture/document",
                    "page_number": 1,
                    "bbox": {"left": 0.0, "top": 0.0, "right": 10.0, "bottom": 10.0},
                },
                "confidence": 1.0,
                "review_required": False,
            }
        ],
        "review_required": False,
    }


def test_json_round_trip_and_canonical_serialization() -> None:
    candidate = ExtractionCandidate.model_validate_json(json.dumps(candidate_payload()))
    encoded = candidate.model_dump_json()
    restored = ExtractionCandidate.model_validate_json(encoded)
    assert restored == candidate
    assert '"normalized_value":"12.30"' in encoded
    assert '"created_at":"2026-07-31T00:00:00Z"' in encoded
    assert isinstance(restored.candidate_id, UUID)
    assert restored.values[0].normalized_value == Decimal("12.30")


def test_child_review_requirement_propagates_to_candidate() -> None:
    payload = candidate_payload()
    payload["values"][0]["review_required"] = True

    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate_json(json.dumps(payload))

    payload["review_required"] = True
    candidate = ExtractionCandidate.model_validate_json(json.dumps(payload))
    assert candidate.review_required is True


def test_unknown_provider_is_rejected() -> None:
    payload = candidate_payload()
    payload["provider_name"] = "unapproved-provider"

    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate_json(json.dumps(payload))


def test_candidate_and_review_contracts_reject_more_than_500_rows() -> None:
    candidate = candidate_payload()
    candidate["values"] = [candidate["values"][0]] * 501
    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate(candidate)

    field = {
        "field_key": "SYNTHETIC_VALUE",
        "final_text": "12.30",
        "source": "OCR",
        "reason": "generated review",
    }
    with pytest.raises(ValidationError):
        ReviewRequest.model_validate(
            {
                "allocation_id": "123e4567-e89b-12d3-a456-426614174002",
                "fields": [field] * 501,
            }
        )


def test_local_provider_is_candidate_only_and_requires_review_metadata() -> None:
    payload = candidate_payload()
    payload["provider_name"] = "local-paddleocr"
    payload["review_required"] = True
    payload["values"][0].update(
        review_required=True,
        reading_order=1,
        recipe_id="native-text",
        variant_id="native-text",
        rotation_degrees=0,
        deskew_millidegrees=0,
        deskew_status="NOT_NEEDED",
        perspective_corrected=False,
        reason_codes=["HUMAN_REVIEW_REQUIRED"],
    )

    candidate = ExtractionCandidate.model_validate_json(json.dumps(payload))

    assert candidate.provider_name == "local-paddleocr"
    assert candidate.review_required is True
    assert candidate.values[0].reason_codes == ["HUMAN_REVIEW_REQUIRED"]


def test_local_provider_can_never_bypass_human_review() -> None:
    payload = candidate_payload()
    payload["provider_name"] = "local-paddleocr"

    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate_json(json.dumps(payload))


def test_reason_codes_preserve_pipeline_severity_order() -> None:
    payload = candidate_payload()
    payload["provider_name"] = "local-paddleocr"
    payload["review_required"] = True
    payload["values"][0].update(
        review_required=True,
        reading_order=1,
        recipe_id="original",
        variant_id="original-r0",
        rotation_degrees=0,
        deskew_millidegrees=0,
        deskew_status="NOT_NEEDED",
        perspective_corrected=False,
        reason_codes=["TABLE_LAYOUT_REVIEW_REQUIRED", "LOW_CONFIDENCE", "HUMAN_REVIEW_REQUIRED"],
    )

    candidate = ExtractionCandidate.model_validate_json(json.dumps(payload))

    assert candidate.values[0].reason_codes == [
        "HUMAN_REVIEW_REQUIRED",
        "LOW_CONFIDENCE",
        "TABLE_LAYOUT_REVIEW_REQUIRED",
    ]


def test_generated_schema_accepts_canonical_decimal_strings() -> None:
    schema_path = (
        Path(__file__).resolve().parents[3] / "contracts/schemas/extraction-candidate.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    assert (
        schema["$defs"]["ExtractionValue"]["properties"]["normalized_value"]["anyOf"][0]["pattern"]
        == CANONICAL_DECIMAL_STRING_PATTERN
    )
    Draft202012Validator.check_schema(schema)
    assert not list(Draft202012Validator(schema).iter_errors(candidate_payload()))


@pytest.mark.parametrize(
    "value",
    ["12.30", "1.00", "-0.5", "0", "42"],
)
def test_canonical_decimal_strings_validate(value: str) -> None:
    payload = candidate_payload()
    payload["values"][0]["normalized_value"] = value
    candidate = ExtractionCandidate.model_validate_json(json.dumps(payload))
    assert candidate.values[0].normalized_value == Decimal(value)


@pytest.mark.parametrize(
    "value",
    [1.0, "NaN", "Infinity", "-Infinity", "1e3", "+1", " 1", "1 ", "01", ".5", "1."],
)
def test_noncanonical_decimal_values_fail_closed(value: object) -> None:
    payload = candidate_payload()
    payload["values"][0]["normalized_value"] = value
    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate_json(json.dumps(payload))


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload.update(unexpected="no"),
        lambda payload: payload.pop("candidate_id"),
        lambda payload: payload["document"].update(unexpected="no"),
        lambda payload: payload["values"][0].pop("review_required"),
        lambda payload: payload["values"][0]["provenance"]["bbox"].update(unexpected="no"),
        lambda payload: payload["values"][0].update(confidence=1.1),
        lambda payload: payload["values"][0]["provenance"]["bbox"].update(right=0.0),
        lambda payload: payload["values"][0].update(normalized_value=1.2),
        lambda payload: payload.update(candidate_id="not-a-uuid"),
        lambda payload: payload.update(created_at="2026-07-31T00:00:00+09:00"),
    ],
)
def test_invalid_contract_inputs_fail_closed(
    mutator: Callable[[dict[str, Any]], object],
) -> None:
    payload = candidate_payload()
    mutator(payload)
    with pytest.raises(ValidationError):
        ExtractionCandidate.model_validate_json(json.dumps(payload))


def test_utc_storage_and_seoul_display() -> None:
    stored = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    displayed = to_seoul_display(stored)
    assert displayed.tzinfo is not None
    assert displayed.isoformat() == "2026-07-31T09:00:00+09:00"
    with pytest.raises(ValueError):
        to_seoul_display(datetime(2026, 7, 31, 0, 0))
