from __future__ import annotations

from datetime import UTC

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_api.reports.sources import FrozenDecisionSource, LookedUpReferenceSource


def _frozen_label(frozen: FrozenDecisionSource) -> str:
    return f"승인 시점 고정 (snapshot {frozen.content_hash[:12]})"


def _lookup_label(reference: LookedUpReferenceSource) -> str:
    stamp = reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"조회 시점 {stamp}"


def render_lot_trace_report(
    frozen: FrozenDecisionSource,
    reference: LookedUpReferenceSource,
    include_audit: bool = False,
) -> bytes:
    """Render REP-003 LOT trace report as deterministic Excel workbook."""
    frozen_lbl = _frozen_label(frozen)
    lookup_lbl = _lookup_label(reference)
    mixed_lbl = f"혼합 (snapshot {frozen.content_hash[:12]} / {lookup_lbl})"

    lot_ref = frozen.payload.get("lot_reference", {})
    if not isinstance(lot_ref, dict):
        lot_ref = {}

    # 1. LOT기본정보 (LOT Basic Info - Mixed)
    info_rows: list[list[str]] = [
        ["출처", mixed_lbl],
        ["항목", "내용", "출처"],
        ["LOT ID", str(lot_ref.get("lot_id", "")), frozen_lbl],
        ["공급사 LOT 번호", str(lot_ref.get("supplier_lot_no_raw", "")), frozen_lbl],
        ["Canonical Key", str(lot_ref.get("identity_key", "")), frozen_lbl],
        ["공급사명", str(reference.supplier_name), lookup_lbl],
        ["품목명", str(reference.material_name), lookup_lbl],
        ["모델명", str(reference.model_name), lookup_lbl],
        ["생산일자 증빙", str(lot_ref.get("production_date_evidence", "")), frozen_lbl],
        ["식별 상태", str(lot_ref.get("identity_status", "")), frozen_lbl],
        ["병합 대상 LOT ID", str(lot_ref.get("merged_into_id", "")), frozen_lbl],
    ]

    # 2. 입고이력 (Inbound & Allocation History - includes split receipts of one LOT)
    alloc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["Allocation ID", "입고번호", "입고일자", "모델명", "수량", "단위", "입고 상태"],
    ]
    raw_allocs = frozen.payload.get("allocations", [])
    if isinstance(raw_allocs, list):
        for item in raw_allocs:
            if isinstance(item, dict):
                alloc_rows.append(
                    [
                        str(item.get("allocation_id", "")),
                        str(item.get("inbound_no", "")),
                        str(item.get("receipt_date", "")),
                        str(item.get("model_name", reference.model_name)),
                        str(item.get("quantity", "")),
                        str(item.get("quantity_unit", "")),
                        str(item.get("status", "")),
                    ]
                )

    # 3. 검사이력 (Inspection History - Snapshot-backed)
    case_rows: list[list[str]] = [
        ["출처", frozen_lbl],
        ["검사 건 ID", "Allocation ID", "최종 판정", "후보 판정", "기준 버전", "승인 스냅샷 해시"],
        [
            str(frozen.payload.get("inspection_case_id", "")),
            str(frozen.payload.get("allocation_reference", {}).get("allocation_id", "")),
            str(frozen.payload.get("overall_decision", "")),
            str(frozen.payload.get("candidate_decision", "")),
            str(frozen.payload.get("spec_version", {}).get("semantic_version", "")),
            str(frozen.content_hash[:12]),
        ],
    ]

    # 4. 부적합 (Nonconformances - Lookup-backed)
    nc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["NCR 번호", "중요도", "제목/내용", "상태"],
    ]
    for nc in reference.nonconformances:
        if isinstance(nc, dict):
            ncr_no = str(nc.get("ncr_number", nc.get("title", "")))
            sev = str(nc.get("severity", ""))
            desc = str(nc.get("description", nc.get("title", "")))
            status = str(nc.get("status", ""))
            nc_rows.append([ncr_no, sev, desc, status])

    # 5. 문서 (Documents - Lookup & Snapshot)
    doc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["문서 구분", "상세 참조 및 해시"],
    ]
    for filename, digest in reference.documents:
        doc_rows.append(["첨부 문서", f"{filename} (해시: {digest})"])
    for att in reference.attachments:
        doc_rows.append(["추가 첨부", str(att)])

    # 6. 생산 및 출하 추적 (ERP Linkage Seam)
    # PRD 16.3 / Prompt: leave downstream production-LOT and customer-shipment columns
    # as an explicitly empty seam because automatic ERP linkage is out of scope.
    erp_rows: list[list[str]] = [
        ["출처", "미연계 (ERP 연계 비대상 - empty seam)"],
        [
            "투입 생산 LOT",
            "완제품 품목",
            "완제품 LOT",
            "투입 수량",
            "생산일자",
            "출하 LOT",
            "고객사",
        ],
    ]

    sheets = [
        SheetSpec(title="LOT기본정보", rows=info_rows),
        SheetSpec(title="입고이력", rows=alloc_rows),
        SheetSpec(title="검사이력", rows=case_rows),
        SheetSpec(title="부적합", rows=nc_rows),
        SheetSpec(title="문서", rows=doc_rows),
        SheetSpec(title="생산및출하추적", rows=erp_rows),
    ]

    if include_audit:
        approver = frozen.payload.get("approver", {})
        actor_role = str(approver.get("role", "")) if isinstance(approver, dict) else ""
        actor_id = str(approver.get("actor_id", "")) if isinstance(approver, dict) else ""
        audit_rows: list[list[str]] = [
            ["출처", lookup_lbl],
            ["감사 항목", "내용"],
            ["조회 시점", reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")],
            ["승인자 역할", actor_role],
            ["승인자 ID", actor_id],
        ]
        sheets.append(SheetSpec(title="감사", rows=audit_rows))

    return render_workbook(sheets)
