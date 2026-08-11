from __future__ import annotations

import io
from datetime import UTC, datetime

from openpyxl import load_workbook

from hyc_api.reports.deterministic import workbook_digest
from hyc_api.reports.lot_trace import render_lot_trace_report
from hyc_api.reports.sources import FrozenDecisionSource, LookedUpReferenceSource

_FROZEN = FrozenDecisionSource(
    payload={
        "inspection_case_id": "case-uuid-1",
        "overall_decision": "ACCEPTED",
        "candidate_decision": "ACCEPTED",
        "spec_version": {"semantic_version": "1.0.0", "status": "ACTIVE"},
        "approver": {"actor_id": "lead-1", "role": "LEAD"},
        "lot_reference": {
            "lot_id": "lot-uuid-1",
            "supplier_lot_no_raw": "RAW-LOT-100",
            "identity_key": "LOT-CANONICAL-100",
            "identity_status": "CANONICAL",
            "production_date_evidence": "2026-04-15",
            "merged_into_id": "",
        },
        "allocation_reference": {"allocation_id": "alloc-uuid-1"},
        "allocations": [
            {
                "allocation_id": "alloc-uuid-1",
                "inbound_no": "INB-2026-001",
                "receipt_date": "2026-05-01",
                "model_name": "비드 25kg",
                "quantity": "50.00",
                "quantity_unit": "kg",
                "status": "CLOSED",
            },
            {
                "allocation_id": "alloc-uuid-2",
                "inbound_no": "INB-2026-002",
                "receipt_date": "2026-05-15",
                "model_name": "비드 25kg",
                "quantity": "50.00",
                "quantity_unit": "kg",
                "status": "CLOSED",
            },
        ],
    },
    content_hash="a" * 64,
)


def _reference() -> LookedUpReferenceSource:
    return LookedUpReferenceSource(
        material_name="염화칼슘",
        supplier_name="세계로비드",
        model_name="비드 25kg",
        documents=[("coa.pdf", "b" * 64)],
        nonconformances=[
            {
                "ncr_number": "NCR-2026-001",
                "severity": "MAJOR",
                "description": "수분함량 초과",
                "status": "APPROVED",
            }
        ],
        attachments=["photo.jpg"],
        observed_at=datetime(2026, 8, 12, 0, 0, tzinfo=UTC),
    )


def test_lot_trace_sheet_layout_and_audit() -> None:
    report_bytes = render_lot_trace_report(_FROZEN, _reference(), include_audit=False)
    assert len(report_bytes) > 0
    assert workbook_digest(report_bytes) == workbook_digest(report_bytes)

    wb = load_workbook(io.BytesIO(report_bytes))
    assert list(wb.sheetnames) == [
        "LOT기본정보",
        "입고이력",
        "검사이력",
        "부적합",
        "문서",
        "생산및출하추적",
    ]

    report_with_audit = render_lot_trace_report(_FROZEN, _reference(), include_audit=True)
    wb_audit = load_workbook(io.BytesIO(report_with_audit))
    assert "감사" in wb_audit.sheetnames


def test_lot_trace_split_receipts_rows() -> None:
    report_bytes = render_lot_trace_report(_FROZEN, _reference(), include_audit=False)
    wb = load_workbook(io.BytesIO(report_bytes))
    alloc_sheet = wb["입고이력"]
    rows = list(alloc_sheet.iter_rows(values_only=True))

    inbound_nos = [str(r[1]) for r in rows[2:]]
    assert "INB-2026-001" in inbound_nos
    assert "INB-2026-002" in inbound_nos


def test_lot_trace_downstream_erp_seam_is_empty() -> None:
    report_bytes = render_lot_trace_report(_FROZEN, _reference(), include_audit=False)
    wb = load_workbook(io.BytesIO(report_bytes))
    erp_sheet = wb["생산및출하추적"]
    rows = list(erp_sheet.iter_rows(values_only=True))

    assert rows[0][0] == "출처"
    assert "미연계" in str(rows[0][1])
    expected_header = (
        "투입 생산 LOT",
        "완제품 품목",
        "완제품 LOT",
        "투입 수량",
        "생산일자",
        "출하 LOT",
        "고객사",
    )
    assert rows[1] == expected_header
    assert len(rows) == 2


def test_lot_trace_all_cell_values_are_strings() -> None:
    report_bytes = render_lot_trace_report(_FROZEN, _reference(), include_audit=True)
    wb = load_workbook(io.BytesIO(report_bytes))
    for name in wb.sheetnames:
        sheet = wb[name]
        for row in sheet.iter_rows(values_only=True):
            for val in row:
                if val is not None:
                    err_msg = f"Cell in {name} is not str: {type(val)}"
                    assert isinstance(val, str), err_msg
