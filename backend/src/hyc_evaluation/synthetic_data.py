from __future__ import annotations

import hashlib
from copy import deepcopy
from decimal import Decimal
from typing import Any


def _digest(index: int) -> str:
    marker = f"generated-non-sensitive-synthetic-edge-{index:03d}".encode()
    return hashlib.sha256(marker).hexdigest()


def _geometry(order: int) -> dict[str, Any]:
    top = 40 + order * 20
    return {
        "page_number": 1,
        "polygon": [
            {"x": "40", "y": str(top)},
            {"x": "300", "y": str(top)},
            {"x": "300", "y": str(top + 16)},
            {"x": "40", "y": str(top + 16)},
        ],
    }


def _field(
    document_id: str,
    field_key: str,
    raw: str | None,
    normalized: str | None,
    *,
    kind: str = "text",
    unit: str | None = None,
    row_id: str = "row-1",
    row_order: int = 1,
    sample_id: str | None = None,
    sample_order: int | None = None,
    reason_codes: list[str] | None = None,
    handwriting: bool = False,
    required: bool = True,
    geometry_order: int = 1,
) -> dict[str, Any]:
    reasons = reason_codes or []
    normalization = {
        "decimal": "decimal.canonical",
        "date": "date.iso8601",
        "lot": "lot.trim-upper",
        "unit": "unit.alias",
    }.get(kind, "identity")
    return {
        "identity": {
            "document_id": document_id,
            "section_id": "main",
            "row_id": row_id,
            "row_order": row_order,
            "sample_id": sample_id,
            "sample_order": sample_order,
        },
        "field_key": field_key,
        "required": required,
        "ignored": False,
        "value": {"kind": kind, "raw": raw, "normalized": normalized, "unit": unit},
        "geometry": _geometry(geometry_order),
        "review": {
            "review_required": bool(reasons),
            "reason_codes": reasons,
            "handwriting_reference_only": handwriting,
        },
        "allowed_normalizations": [
            {"normalization_id": normalization, "normalization_version": "1.0"}
        ],
    }


def _case(index: int, fields: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "case_id": f"edge-{index:03d}",
        "ordering_key": f"{index:04d}",
        "input": {
            "source_sha256": _digest(index),
            "mime_type": "application/pdf",
            "document_kind": ("supplier-inspection-report" if index == 13 else "supplier-coa"),
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
                "page_id": f"edge-{index:03d}-page-1",
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
        "expected_fields": fields,
    }


def _candidate_value(order: int, expected: dict[str, Any]) -> dict[str, Any]:
    """Materialize a versioned candidate payload distinct from the golden answer key."""

    reasons = list(expected["review"]["reason_codes"])
    return {
        "candidate_order": order,
        "identity": deepcopy(expected["identity"]),
        "field_key": expected["field_key"],
        "value": deepcopy(expected["value"]),
        "geometry": deepcopy(expected["geometry"]),
        "applied_normalizations": deepcopy(expected["allowed_normalizations"]),
        "confidence": "0.55" if "LOW_CONFIDENCE" in reasons else "1",
        "reason_codes": reasons,
        "handwriting_reference_only": expected["review"]["handwriting_reference_only"],
        "review_required": bool(reasons),
    }


def _set_candidate_reasons(candidate: dict[str, Any], *reasons: str) -> None:
    candidate["reason_codes"] = list(reasons)
    candidate["handwriting_reference_only"] = "HANDWRITING_REFERENCE_ONLY" in reasons
    candidate["review_required"] = bool(reasons)
    candidate["confidence"] = "0.55" if "LOW_CONFIDENCE" in reasons else "1"


def _generated_candidate_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidate_cases: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        values = [
            _candidate_value(order, expected)
            for order, expected in enumerate(case["expected_fields"], start=1)
        ]

        if index == 1:
            offset = next(value for value in values if value["field_key"] == "SUPPLIER_NAME")
            offset["geometry"]["polygon"] = [
                {"x": "60", "y": "60"},
                {"x": "320", "y": "60"},
                {"x": "320", "y": "76"},
                {"x": "60", "y": "76"},
            ]
        elif index == 2:
            values[0]["value"].update(raw="75.4", normalized="75.4")
        elif index == 3:
            values[0]["value"]["unit"] = "%"
        elif index == 4:
            zero = next(value for value in values if value["field_key"] == "O_ZERO_AMBIGUITY")
            zero["value"].update(raw="LOT-01", normalized="LOT-01")
            eye = next(value for value in values if value["field_key"] == "I_L_AMBIGUITY")
            eye["value"].update(raw="llI", normalized="llI")
        elif index == 6:
            values[0]["applied_normalizations"] = [
                {"normalization_id": "text.upper", "normalization_version": "1.0"}
            ]
        elif index == 7:
            hyc_spec = next(value for value in values if value["field_key"] == "HYC_SPECIFICATION")
            _set_candidate_reasons(hyc_spec, "LOGIC_CONFLICT")
        elif index == 9:
            product = next(
                value
                for value in values
                if value["field_key"] == "PRODUCT_NAME"
                and value["identity"]["row_id"] == "product-a"
            )
            _set_candidate_reasons(product, "DUPLICATE_FIELD")
            duplicate = deepcopy(product)
            duplicate["candidate_order"] = len(values) + 1
            values.append(duplicate)
        elif index == 11:
            unmapped = deepcopy(values[-1])
            unmapped["candidate_order"] = len(values) + 1
            unmapped["identity"]["row_id"] = "unmapped-note"
            unmapped["identity"]["row_order"] = 4
            unmapped["field_key"] = "UNMAPPED_ALLOCATION_NOTE"
            unmapped["value"] = {
                "kind": "text",
                "raw": "synthetic candidate-only note",
                "normalized": "synthetic candidate-only note",
                "unit": None,
            }
            unmapped["applied_normalizations"] = [
                {"normalization_id": "identity", "normalization_version": "1.0"}
            ]
            _set_candidate_reasons(unmapped)
            values.append(unmapped)
        elif index == 18:
            page_mismatch = next(
                value for value in values if value["field_key"] == "EFFECTIVE_SPEC_VERSION"
            )
            page_mismatch["geometry"]["page_number"] = 2

        observed_stage_warning_codes: set[str] = set()
        if any(Decimal(value["confidence"]) < Decimal("1") for value in values):
            observed_stage_warning_codes.add("LOW_CONFIDENCE")
        if any(value["handwriting_reference_only"] for value in values):
            observed_stage_warning_codes.add("HANDWRITING_REFERENCE_ONLY")
        if index == 1:
            # Stamp overlap is image-level observed evidence, not a value/golden label.
            observed_stage_warning_codes.add("STAMP_OVERLAP")

        candidate_cases.append(
            {
                "case_id": case["case_id"],
                "values": values,
                "observed_stage_warning_codes": sorted(observed_stage_warning_codes),
            }
        )
    return candidate_cases


EDGE_TITLES = (
    "stamp overlap obscures result",
    "missing decimal point",
    "missing percent sign",
    "O/0 and I/l ambiguity",
    "CaCl2 formula recognition",
    "multilingual alias",
    "supplier versus HYC specification separation",
    "missing HYC required field",
    "multiple products and LOTs",
    "duplicate document identity",
    "split receipt identity",
    "large supplier/internal deviation signal",
    "variable 5 and 3 samples",
    "sentence qualitative result",
    "handwriting date reference only",
    "encrypted or corrupt synthetic input",
    "upload/read race",
    "effective-date boundary binding",
    "spec revision before approval",
    "post-approval wrong-link discovery",
)


def generated_fixture_payload() -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for index in range(1, 21):
        document_id = f"synthetic-document-{index:03d}"
        fields = [
            _field(
                document_id,
                "SYNTHETIC_SIGNAL",
                f"EDGE-{index:03d}",
                f"EDGE-{index:03d}",
            )
        ]
        if index == 1:
            fields = [
                _field(
                    document_id,
                    "SUPPLIER_NAME",
                    "Synthetic Supplier",
                    "Synthetic Supplier",
                    kind="header",
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "PRODUCT_NAME",
                    "Calcium Chloride",
                    "Calcium Chloride",
                    kind="header",
                    geometry_order=2,
                ),
                _field(
                    document_id,
                    "LOT_NUMBER",
                    "SYN-LOT-001",
                    "SYN-LOT-001",
                    kind="lot",
                    geometry_order=3,
                ),
                _field(
                    document_id,
                    "CALCIUM_CHLORIDE_CONTENT",
                    "75.50",
                    "75.50",
                    kind="decimal",
                    unit="%",
                    row_id="content-row",
                    row_order=4,
                    geometry_order=4,
                ),
                _field(
                    document_id,
                    "SUPPLIER_SPECIFICATION",
                    ">= 74.0%",
                    ">= 74.0%",
                    row_id="content-row",
                    row_order=4,
                    geometry_order=5,
                ),
                _field(
                    document_id,
                    "SUPPLIER_RESULT",
                    "75.50%",
                    "75.50%",
                    row_id="content-row",
                    row_order=4,
                    geometry_order=6,
                ),
                _field(
                    document_id,
                    "STAMP_OVERLAP_VALUE",
                    "0.001",
                    "0.001",
                    kind="decimal",
                    unit="%",
                    row_id="stamp-row",
                    row_order=5,
                    reason_codes=["LOW_CONFIDENCE"],
                    geometry_order=7,
                ),
                _field(
                    document_id,
                    "HANDWRITING_DATE_REFERENCE",
                    "2026-08-02",
                    "2026-08-02",
                    kind="date",
                    row_id="handwriting-row",
                    row_order=6,
                    reason_codes=["HANDWRITING_REFERENCE_ONLY"],
                    handwriting=True,
                    geometry_order=8,
                ),
            ]
        elif index == 2:
            fields = [
                _field(
                    document_id,
                    "DECIMAL_AMBIGUITY_VALUE",
                    "7550",
                    "75.50",
                    kind="decimal",
                    unit="%",
                    reason_codes=["LOGIC_CONFLICT"],
                )
            ]
        elif index == 3:
            fields = [
                _field(
                    document_id,
                    "PERCENT_UNIT_MISSING_VALUE",
                    "0.5",
                    "0.5",
                    kind="decimal",
                    reason_codes=["LOGIC_CONFLICT"],
                )
            ]
        elif index == 4:
            fields = [
                _field(
                    document_id,
                    "O_ZERO_AMBIGUITY",
                    "L0T-O1",
                    "L0T-O1",
                    kind="lot",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "I_L_AMBIGUITY",
                    "Il1",
                    "Il1",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=2,
                ),
            ]
        elif index == 5:
            fields = [_field(document_id, "CHEMICAL_FORMULA", "CaCl2", "CaCl2")]
        elif index == 6:
            fields = [
                _field(
                    document_id,
                    "ALIASED_ITEM_NAME",
                    "불용분",
                    "WATER_INSOLUBLE",
                )
            ]
        elif index == 7:
            fields = [
                _field(
                    document_id,
                    "SUPPLIER_SPECIFICATION",
                    "<= 0.5%",
                    "<= 0.5%",
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "HYC_SPECIFICATION",
                    "<= 0.15%",
                    "<= 0.15%",
                    geometry_order=2,
                ),
            ]
        elif index == 8:
            fields = [
                _field(
                    document_id, "HYC_REQUIRED_FIELD", None, None, reason_codes=["MISSING_REQUIRED"]
                )
            ]
        elif index == 9:
            fields = [
                _field(
                    document_id,
                    "PRODUCT_NAME",
                    "Synthetic Product A",
                    "Synthetic Product A",
                    kind="header",
                    row_id="product-a",
                    row_order=1,
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "LOT_NUMBER",
                    "SYN-A-001",
                    "SYN-A-001",
                    kind="lot",
                    row_id="product-a",
                    row_order=1,
                    geometry_order=2,
                ),
                _field(
                    document_id,
                    "PRODUCT_NAME",
                    "Synthetic Product B",
                    "Synthetic Product B",
                    kind="header",
                    row_id="product-b",
                    row_order=2,
                    geometry_order=3,
                ),
                _field(
                    document_id,
                    "LOT_NUMBER",
                    "SYN-B-001",
                    "SYN-B-001",
                    kind="lot",
                    row_id="product-b",
                    row_order=2,
                    geometry_order=4,
                ),
            ]
        elif index == 10:
            fields = [
                _field(
                    document_id,
                    "DUPLICATE_DOCUMENT_IDENTITY",
                    "synthetic-duplicate-group-001",
                    "synthetic-duplicate-group-001",
                    reason_codes=["LOGIC_CONFLICT"],
                )
            ]
        elif index == 11:
            fields = [
                _field(
                    document_id,
                    "CANONICAL_LOT_ID",
                    "synthetic-lot-011",
                    "synthetic-lot-011",
                    row_id="lot",
                    row_order=1,
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "INBOUND_ALLOCATION_ID",
                    "synthetic-allocation-011-a",
                    "synthetic-allocation-011-a",
                    row_id="allocation-a",
                    row_order=2,
                    geometry_order=2,
                ),
                _field(
                    document_id,
                    "INBOUND_ALLOCATION_ID",
                    "synthetic-allocation-011-b",
                    "synthetic-allocation-011-b",
                    row_id="allocation-b",
                    row_order=3,
                    geometry_order=3,
                ),
            ]
        elif index == 12:
            fields = [
                _field(
                    document_id,
                    "SUPPLIER_RESULT",
                    "0.01",
                    "0.01",
                    kind="decimal",
                    unit="%",
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "HYC_INTERNAL_RESULT",
                    "0.14",
                    "0.14",
                    kind="decimal",
                    unit="%",
                    geometry_order=2,
                ),
                _field(
                    document_id,
                    "DEVIATION_SIGNAL",
                    "0.13",
                    "0.13",
                    kind="decimal",
                    unit="%",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=3,
                ),
            ]
        elif index == 13:
            fields = []
            for sample in range(1, 6):
                fields.append(
                    _field(
                        document_id,
                        "DIMENSION_VALUE",
                        f"10.{sample}",
                        f"10.{sample}",
                        kind="decimal",
                        unit="mm",
                        row_id="dimension-row",
                        row_order=1,
                        sample_id=f"dimension-{sample}",
                        sample_order=sample,
                        geometry_order=sample,
                    )
                )
            for sample in range(1, 4):
                fields.append(
                    _field(
                        document_id,
                        "MATERIAL_RESULT",
                        "PASS",
                        "PASS",
                        row_id="material-row",
                        row_order=2,
                        sample_id=f"material-{sample}",
                        sample_order=sample,
                        geometry_order=sample + 5,
                    )
                )
        elif index == 14:
            fields = [
                _field(
                    document_id,
                    "QUALITATIVE_SENTENCE_RESULT",
                    "No foreign material was observed.",
                    "No foreign material was observed.",
                )
            ]
        elif index == 15:
            fields = [
                _field(
                    document_id,
                    "HANDWRITING_DATE_REFERENCE",
                    "2026-08-02",
                    "2026-08-02",
                    kind="date",
                    reason_codes=["HANDWRITING_REFERENCE_ONLY"],
                    handwriting=True,
                )
            ]
        elif index == 18:
            fields = [
                _field(
                    document_id,
                    "RECEIPT_DATE",
                    "2026-08-01",
                    "2026-08-01",
                    kind="date",
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "EFFECTIVE_SPEC_VERSION",
                    "synthetic-spec-v2",
                    "synthetic-spec-v2",
                    geometry_order=2,
                ),
            ]
        elif index == 19:
            fields = [
                _field(
                    document_id,
                    "FROZEN_SPEC_VERSION",
                    "synthetic-spec-v2",
                    "synthetic-spec-v2",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "CURRENT_SPEC_VERSION",
                    "synthetic-spec-v3",
                    "synthetic-spec-v3",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=2,
                ),
            ]
        elif index == 20:
            fields = [
                _field(
                    document_id,
                    "ORIGINAL_DOCUMENT_LINK",
                    "synthetic-document-link-020-a",
                    "synthetic-document-link-020-a",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=1,
                ),
                _field(
                    document_id,
                    "CORRECTED_DOCUMENT_LINK",
                    "synthetic-document-link-020-b",
                    "synthetic-document-link-020-b",
                    reason_codes=["LOGIC_CONFLICT"],
                    geometry_order=2,
                ),
            ]
        cases.append(_case(index, fields))

    owner_phases = (
        "P4-A",
        "P4-A",
        "P4-A",
        "P4-A",
        "P4-A",
        "P4-A",
        "P2",
        "P2",
        "P4-A",
        "P3",
        "P2",
        "P2",
        "P4-A",
        "P4-A",
        "P4-A",
        "P4-A",
        "P4-A",
        "P2",
        "P2",
        "P5",
    )
    dispositions = (
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "CANDIDATE_ONLY",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "MANUAL_FALLBACK",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "CANDIDATE_ONLY",
        "CANDIDATE_ONLY",
        "REVIEW_REQUIRED",
        "STABLE_FAILURE",
        "STABLE_FAILURE",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
        "REVIEW_REQUIRED",
    )
    reasons = (
        ("HANDWRITING_REFERENCE_ONLY", "LOW_CONFIDENCE"),
        ("LOGIC_CONFLICT", "VALUE_MISMATCH"),
        ("LOGIC_CONFLICT", "VALUE_MISMATCH"),
        ("LOGIC_CONFLICT", "VALUE_MISMATCH"),
        (),
        ("UNAPPROVED_NORMALIZATION",),
        ("LOGIC_CONFLICT",),
        ("MISSING_REQUIRED",),
        ("DUPLICATE_FIELD",),
        ("LOGIC_CONFLICT",),
        ("UNMAPPED",),
        ("LOGIC_CONFLICT",),
        (),
        (),
        ("HANDWRITING_REFERENCE_ONLY",),
        ("MISSING_REQUIRED", "UPSTREAM_FAILURE"),
        ("MISSING_REQUIRED", "UPSTREAM_FAILURE"),
        ("PAGE_MISMATCH",),
        ("LOGIC_CONFLICT",),
        ("LOGIC_CONFLICT",),
    )
    edges = []
    for index, title in enumerate(EDGE_TITLES, start=1):
        cross_phase = owner_phases[index - 1] != "P4-A"
        edges.append(
            {
                "edge_id": f"P4-EDGE-{index:03d}",
                "prd_edge_number": index,
                "title": title,
                "synthetic_fixture_ref": "p4a_edge_dataset.v1.json",
                "case_id": f"edge-{index:03d}",
                "expected_value_or_failure": (
                    "STABLE_UPSTREAM_FAILURE"
                    if index in {16, 17}
                    else f"SYNTHETIC_EDGE_{index:03d}_CANDIDATE"
                ),
                "expected_confidence": "0.55"
                if index == 1
                else ("NOT_APPLICABLE" if index in {16, 17} else "1"),
                "expected_reason_codes": list(reasons[index - 1]),
                "expected_stage_warning_codes": (
                    ["HANDWRITING_REFERENCE_ONLY", "LOW_CONFIDENCE", "STAMP_OVERLAP"]
                    if index == 1
                    else (["HANDWRITING_REFERENCE_ONLY"] if index == 15 else [])
                ),
                "expected_disposition": dispositions[index - 1],
                "owner_phase": owner_phases[index - 1],
                "executable_test_path": "backend/tests/golden/test_runner_stages_metrics_edges.py",
                "p4a_signal": "Deterministic synthetic evaluator evidence only",
                "p4a_limit": (
                    "SIGNAL_ONLY_EXISTING_OR_FUTURE_OWNER_REMAINS_AUTHORITATIVE"
                    if cross_phase
                    else "OFFLINE_SYNTHETIC_ONLY_NO_REAL_CORPUS_OR_PROVIDER"
                ),
                "failure_stage": "TEXT_LAYER_DETECTION"
                if index == 16
                else ("PAGE_RENDER" if index == 17 else None),
                "failure_code": "ENCRYPTED_SYNTHETIC_INPUT"
                if index == 16
                else ("UPLOAD_READ_RACE" if index == 17 else None),
            }
        )

    return {
        "fixture_schema_version": "hyc.synthetic-fixture-bundle.v1",
        "dataset": {
            "golden_schema_version": "hyc.golden.v1",
            "dataset_id": "p4a-prd-edge-matrix",
            "dataset_version": "1.0.0",
            "normalization_vocabulary_version": "hyc.normalization.v1",
            "bindings": {
                "fixture_name": "p4a-edge-dataset",
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
            "cases": cases,
        },
        "edge_matrix": edges,
        "candidate_cases": _generated_candidate_cases(cases),
    }
