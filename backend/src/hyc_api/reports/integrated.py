from __future__ import annotations

from datetime import UTC

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_api.reports.sources import FrozenDecisionSource, LookedUpReferenceSource


def _frozen_label(frozen: FrozenDecisionSource) -> str:
    return f"승인 시점 고정 (snapshot {frozen.content_hash[:12]})"


def _lookup_label(reference: LookedUpReferenceSource) -> str:
    stamp = reference.observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    return f"조회 시점 {stamp}"


def render_integrated_inspection_report(
    frozen: FrozenDecisionSource,
    reference: LookedUpReferenceSource,
    include_audit: bool = False,
) -> bytes:
    frozen_lbl = _frozen_label(frozen)
    lookup_lbl = _lookup_label(reference)
    mixed_lbl = f"혼합 (snapshot {frozen.content_hash[:12]} / {lookup_lbl})"

    # 1. 요약 (Summary - Mixed)
    summary_rows: list[list[str]] = [
        ["출처", mixed_lbl],
        ["항목", "내용", "출처"],
        ["품목명", str(reference.material_name), lookup_lbl],
        ["공급사명", str(reference.supplier_name), lookup_lbl],
        ["모델명", str(reference.model_name), lookup_lbl],
        ["최종 판정", str(frozen.payload.get("overall_decision", "")), frozen_lbl],
        [
            "기준 버전",
            str(frozen.payload.get("spec_version", {}).get("semantic_version", "")),
            frozen_lbl,
        ],
        ["승인자 역할", str(frozen.payload.get("approver", {}).get("role", "")), frozen_lbl],
        ["LOT ID", str(frozen.payload.get("lot_reference", {}).get("lot_id", "")), frozen_lbl],
        [
            "Allocation ID",
            str(frozen.payload.get("allocation_reference", {}).get("allocation_id", "")),
            frozen_lbl,
        ],
    ]

    # 2. 공급사결과 (Supplier Results - Snapshot-backed)
    supplier_rows: list[list[str]] = [
        ["출처", frozen_lbl],
        ["공급사 항목", "상세 규격 및 결과"],
    ]
    raw_supplier_results = frozen.payload.get("supplier_results", [])
    if isinstance(raw_supplier_results, list):
        for item in raw_supplier_results:
            if isinstance(item, dict):
                item_name = str(item.get("supplier_item_name", item.get("name", "")))
                spec_text = str(item.get("supplier_spec_text", item.get("spec", "")))
                norm_val = str(item.get("normalized_value", item.get("value", "")))
                decision = str(item.get("supplier_decision", item.get("status", "")))
                supplier_rows.append(
                    [item_name, f"규격: {spec_text} / 수치: {norm_val} / 판정: {decision}"]
                )

    # 3. 자체검사 (Internal Results - Snapshot-backed)
    internal_rows: list[list[str]] = [
        ["출처", frozen_lbl],
        ["검사항목", "상세 측정 및 판정"],
    ]
    raw_internal_results = frozen.payload.get("internal_results", [])
    if isinstance(raw_internal_results, list):
        for item in raw_internal_results:
            if isinstance(item, dict):
                item_name = str(item.get("item_name", item.get("code", "")))
                spec_text = str(item.get("spec", ""))
                eval_val = str(item.get("evaluated_value", item.get("value", "")))
                decision = str(item.get("decision", ""))
                internal_rows.append(
                    [item_name, f"기준: {spec_text} / 측정: {eval_val} / 판정: {decision}"]
                )

    # 4. 판정근거 (Decision Rationale - Snapshot-backed)
    reasons = frozen.payload.get("decision_reasons", {})
    reason_str = str(reasons.get("reason", "")) if isinstance(reasons, dict) else ""
    final_str = str(reasons.get("final", "")) if isinstance(reasons, dict) else ""
    rationale_rows: list[list[str]] = [
        ["출처", frozen_lbl],
        ["항목", "내용"],
        ["최종 판정", str(frozen.payload.get("overall_decision", ""))],
        ["판정 이유", reason_str],
        ["결정 사유 상세", final_str],
    ]

    # 5. 부적합 (Nonconformances - Lookup-backed)
    nc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["NCR 번호", "상세 내용"],
    ]
    for nc in reference.nonconformances:
        if isinstance(nc, dict):
            ncr_no = str(nc.get("ncr_number", nc.get("title", "")))
            title = str(nc.get("title", nc.get("description", "")))
            qty = str(nc.get("quantity", ""))
            status = str(nc.get("status", ""))
            nc_rows.append([ncr_no, f"제목: {title} / 수량: {qty} / 상태: {status}"])

    # 6. 문서 (Documents - Lookup & Snapshot)
    doc_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["문서 구분", "상세 참조 및 해시"],
    ]
    for filename, digest in reference.documents:
        doc_rows.append(["첨부 문서", f"{filename} (해시: {digest})"])
    for att in reference.attachments:
        doc_rows.append(["추가 첨부", str(att)])
    raw_doc_hashes = frozen.payload.get("document_hashes", [])
    if isinstance(raw_doc_hashes, list):
        for h in raw_doc_hashes:
            doc_rows.append(["승인 문서 해시", str(h)])

    sheets = [
        SheetSpec(title="요약", rows=summary_rows),
        SheetSpec(title="공급사결과", rows=supplier_rows),
        SheetSpec(title="자체검사", rows=internal_rows),
        SheetSpec(title="판정근거", rows=rationale_rows),
        SheetSpec(title="부적합", rows=nc_rows),
        SheetSpec(title="문서", rows=doc_rows),
    ]

    # 7. 감사 (Audit - Lookup-backed, optional)
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
