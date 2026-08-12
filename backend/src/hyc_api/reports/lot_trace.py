from __future__ import annotations

from datetime import UTC

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_api.reports.sources import FrozenDecisionSource, LotTraceSources


def _frozen_label(frozen: FrozenDecisionSource) -> str:
    return f"승인 시점 고정 (snapshot {frozen.content_hash[:12]})"


def render_lot_trace_report(
    sources: LotTraceSources,
    include_audit: bool = False,
) -> bytes:
    stamp = sources.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    lookup_lbl = f"조회 시점 {stamp}"
    if sources.case_pairs:
        hashes = ", ".join(c.frozen.content_hash[:12] for c in sources.case_pairs)
        mixed_lbl = f"혼합 (snapshots {hashes} / {lookup_lbl})"
        first_frozen_lbl = _frozen_label(sources.case_pairs[0].frozen)
    else:
        mixed_lbl = lookup_lbl
        first_frozen_lbl = lookup_lbl

    # 1. LOT기본정보 (LOT Basic Info - Mixed)
    info_rows: list[list[str]] = [
        ["출처", mixed_lbl],
        ["항목", "내용", "출처"],
        ["LOT ID", str(sources.material_lot_id), lookup_lbl],
        ["공급사 LOT 번호", str(sources.supplier_lot_no_raw), lookup_lbl],
        ["Canonical Key", str(sources.identity_key), lookup_lbl],
        ["공급사명", str(sources.supplier_name), lookup_lbl],
        ["품목명", str(sources.material_name), lookup_lbl],
        ["모델명", str(sources.model_name), lookup_lbl],
        ["생산일자 증빙", str(sources.production_date_evidence), lookup_lbl],
        ["식별 상태", str(sources.identity_status), lookup_lbl],
        ["병합 대상 LOT ID", str(sources.merged_into_id), lookup_lbl],
    ]

    # 2. 입고이력 (Inbound & Allocation History - split receipts of one LOT)
    alloc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["Allocation ID", "입고번호", "입고일자", "모델명", "수량", "단위", "입고 상태"],
    ]
    for item in sources.allocations:
        alloc_rows.append(
            [
                str(item.allocation_id),
                str(item.inbound_no),
                str(item.receipt_date),
                str(item.model_name or sources.model_name),
                str(item.quantity),
                str(item.quantity_unit),
                str(item.status),
            ]
        )

    # 3. 검사이력 (Inspection History - Snapshot-backed)
    case_rows: list[list[str]] = [
        ["출처", first_frozen_lbl],
        ["검사 건 ID", "Allocation ID", "최종 판정", "후보 판정", "기준 버전", "승인 스냅샷 해시"],
    ]
    for case_pair in sources.case_pairs:
        frozen = case_pair.frozen
        case_rows.append(
            [
                str(frozen.payload.get("inspection_case_id", "")),
                str(frozen.payload.get("allocation_reference", {}).get("allocation_id", "")),
                str(frozen.payload.get("overall_decision", "")),
                str(frozen.payload.get("candidate_decision", "")),
                str(frozen.payload.get("spec_version", {}).get("semantic_version", "")),
                str(frozen.content_hash[:12]),
            ]
        )

    # 4. 부적합 (Nonconformances - Lookup-backed)
    nc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["NCR 번호", "중요도", "제목/내용", "상태"],
    ]
    seen_ncs: set[str] = set()
    for case_pair in sources.case_pairs:
        for nc in case_pair.reference.nonconformances:
            if isinstance(nc, dict):
                nc_id = str(nc.get("id", nc.get("ncr_number", "")))
                if nc_id not in seen_ncs:
                    seen_ncs.add(nc_id)
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
    seen_docs: set[tuple[str, str]] = set()
    seen_atts: set[str] = set()
    for case_pair in sources.case_pairs:
        for filename, digest in case_pair.reference.documents:
            if (filename, digest) not in seen_docs:
                seen_docs.add((filename, digest))
                doc_rows.append(["첨부 문서", f"{filename} (해시: {digest})"])
        for att in case_pair.reference.attachments:
            if att not in seen_atts:
                seen_atts.add(att)
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
        audit_rows: list[list[str]] = [
            ["출처", lookup_lbl],
            ["감사 항목", "내용"],
            ["조회 시점", sources.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")],
        ]
        for case_pair in sources.case_pairs:
            approver = case_pair.frozen.payload.get("approver", {})
            if isinstance(approver, dict):
                actor_role = str(approver.get("role", ""))
                actor_id = str(approver.get("actor_id", ""))
                audit_rows.append(["승인자 역할", actor_role])
                audit_rows.append(["승인자 ID", actor_id])
        sheets.append(SheetSpec(title="감사", rows=audit_rows))

    return render_workbook(sheets)
