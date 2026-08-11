from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC
from typing import Any

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_api.reports.sources import FrozenDecisionSource, LookedUpReferenceSource

_FIXED_HEADERS = [
    "Model명",
    "품    명",
    "Lot Size",
    "검사구분",
    "입고일자",
    "검사일자",
    "검 사 자",
    "불량수량",
    "불 량 율",
    "제조업체",
    "Sample Size",
    "판   정",
    "처리방안",
]


def _as_text(value: object | None) -> str:
    return "" if value is None else str(value)


def _frozen_label(frozen: FrozenDecisionSource) -> str:
    return f"승인 시점 고정 (snapshot {frozen.content_hash[:12]})"


def _lookup_label(reference: LookedUpReferenceSource) -> str:
    stamp = reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"조회 시점 {stamp}"


def _dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _first_value(item: dict[str, Any], keys: Iterable[str]) -> str:
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return _as_text(value)
    return ""


def _criterion(spec_item: dict[str, Any]) -> str:
    direct = _first_value(spec_item, ("criterion", "spec", "standard", "specification"))
    if direct:
        return direct

    unit = _as_text(spec_item.get("unit"))
    lower = _as_text(spec_item.get("lower"))
    upper = _as_text(spec_item.get("upper"))
    target = _as_text(spec_item.get("target"))
    operator = _as_text(spec_item.get("operator"))
    allowed = _as_text(spec_item.get("allowed"))
    if lower or upper:
        return f"{lower} ~ {upper}".strip() + (f" {unit}" if unit else "")
    if target:
        return f"{operator} {target}".strip() + (f" {unit}" if unit else "")
    return allowed + (f" {unit}" if allowed and unit else "")


def _sample_rows(result: dict[str, Any]) -> list[tuple[str, str, str]]:
    raw_samples = result.get("samples", result.get("sample_measurements", []))
    samples: list[tuple[str, str, str]] = []
    if isinstance(raw_samples, list):
        for position, sample in enumerate(raw_samples, start=1):
            if isinstance(sample, dict):
                sample_index = _first_value(
                    sample, ("sample_index", "index", "sample_no", "number")
                )
                value = _first_value(
                    sample, ("value", "evaluated_value", "normalized_value", "text")
                )
                decision = _first_value(sample, ("decision", "status"))
                samples.append((sample_index or str(position), value, decision))
            else:
                samples.append((str(position), _as_text(sample), ""))
    if samples:
        return sorted(
            samples,
            key=lambda row: (0, int(row[0]), row[0]) if row[0].isdigit() else (1, 0, row[0]),
        )

    value = _first_value(result, ("value", "evaluated_value", "normalized_value", "text"))
    if value:
        return [("1", value, _first_value(result, ("decision", "status")))]
    return []


def _inspection_items(payload: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    spec_items = _dicts(payload.get("spec_items", []))
    internal_results = _dicts(payload.get("internal_results", []))
    results_by_spec_id = {
        _as_text(result.get("spec_item_id")): result
        for result in internal_results
        if _as_text(result.get("spec_item_id"))
    }
    items: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_result_ids: set[str] = set()
    for spec_item in spec_items:
        spec_id = _as_text(spec_item.get("id"))
        result = results_by_spec_id.get(spec_id, {})
        if spec_id:
            seen_result_ids.add(spec_id)
        items.append((spec_item, result))
    for result in internal_results:
        spec_id = _as_text(result.get("spec_item_id"))
        if spec_id and spec_id in seen_result_ids:
            continue
        items.append(({"id": spec_id, "item_name": spec_id}, result))
    return items


def _item_name(spec_item: dict[str, Any]) -> str:
    return _first_value(spec_item, ("item_name", "name", "code", "standard_test_item_id", "id"))


def render_raw_data_report(
    frozen: FrozenDecisionSource,
    reference: LookedUpReferenceSource,
    include_audit: bool = False,
) -> bytes:
    """Render the legacy-compatible, lossless Raw Data workbook.

    The flattened sheet carries the two legacy result cells for each item;
    Measurements_Long remains the authoritative export for every sample.
    """

    payload = frozen.payload
    frozen_lbl = _frozen_label(frozen)
    lookup_lbl = _lookup_label(reference)
    mixed_lbl = f"혼합 (snapshot {frozen.content_hash[:12]} / {lookup_lbl})"
    items = _inspection_items(payload)

    raw_headers = list(_FIXED_HEADERS)
    raw_values = [
        _as_text(reference.model_name),
        _as_text(reference.material_name),
        _first_value(payload, ("lot_size",)),
        _first_value(payload, ("inspection_type", "inspection_category")),
        _first_value(payload, ("received_at", "receipt_date", "inbound_date")),
        _first_value(payload, ("inspected_at", "inspection_date")),
        _first_value(payload, ("inspector", "inspector_name")),
        _first_value(payload, ("defect_quantity", "defective_quantity")),
        _first_value(payload, ("defect_rate",)),
        _as_text(reference.supplier_name),
        _first_value(payload, ("sample_size",)),
        _first_value(payload, ("overall_decision",)),
        _first_value(payload, ("treatment", "treatment_action", "disposition")),
    ]
    if not raw_values[10]:
        raw_values[10] = str(max((len(_sample_rows(result)) for _, result in items), default=0))

    measurement_rows: list[list[str]] = [
        ["출처", frozen_lbl],
        ["검사항목", "기준", "Sample #", "결과", "판정"],
    ]
    for group_index, (spec_item, result) in enumerate(items):
        start_number = group_index * 2 + 1
        raw_headers.extend(
            [
                "검사항목",
                "기준",
                f"결과#{start_number}",
                f"결과#{start_number + 1}",
                "판정",
            ]
        )
        name = _item_name(spec_item)
        criterion = _criterion(spec_item)
        samples = _sample_rows(result)
        raw_values.extend(
            [
                name,
                criterion,
                samples[0][1] if samples else "",
                samples[1][1] if len(samples) > 1 else "",
                _first_value(result, ("decision", "status"))
                or (samples[0][2] if samples else ""),
            ]
        )
        for sample_index, value, decision in samples:
            measurement_rows.append([name, criterion, sample_index, value, decision])

    raw_rows: list[list[str]] = [
        ["출처", mixed_lbl],
        raw_headers,
        raw_values,
    ]
    document_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["문서명", "SHA-256"],
        *[[_as_text(filename), _as_text(digest)] for filename, digest in reference.documents],
    ]
    sheets = [
        SheetSpec(title="Raw_Data", rows=raw_rows),
        SheetSpec(title="Measurements_Long", rows=measurement_rows),
        SheetSpec(title="Documents", rows=document_rows),
    ]
    if include_audit:
        approver = payload.get("approver", {})
        audit_rows: list[list[str]] = [
            ["출처", lookup_lbl],
            ["감사 항목", "내용"],
            ["조회 시점", reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")],
            [
                "승인자 역할",
                _as_text(approver.get("role")) if isinstance(approver, dict) else "",
            ],
            [
                "승인자 ID",
                _as_text(approver.get("actor_id")) if isinstance(approver, dict) else "",
            ],
        ]
        sheets.append(SheetSpec(title="Audit", rows=audit_rows))

    return render_workbook(sheets)
