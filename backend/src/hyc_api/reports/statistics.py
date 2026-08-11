from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_data.models import (
    DecisionSnapshotRow,
    Document,
    DocumentAllocationLink,
    DocumentSection,
    InspectionCase,
    InternalResult,
    Material,
    MaterialLot,
    Nonconformance,
    NonconformanceDisposition,
    ReceiptLotAllocation,
    Supplier,
)

SEOUL_TZ = ZoneInfo("Asia/Seoul")

#: Sentinel for a metric the schema cannot support yet.  Kept as a string so the
#: frontend renders it verbatim alongside real rates without special-casing.
OCR_REVIEW_RATE_UNMEASURED = "미측정"


@dataclass(frozen=True, slots=True)
class StatisticsRow:
    """Input row representing an approved inspection case for statistics."""

    inspection_case_id: str
    snapshot_created_at: datetime
    status: str
    final_decision: str | None
    material_code: str
    material_name: str
    supplier_code: str = ""
    supplier_name: str = ""
    created_at: datetime | None = None
    has_coa_document: bool = True
    ocr_review_required: bool = False
    internal_test_required: bool = False
    internal_test_completed: bool = False
    failed_test_items: tuple[tuple[str, str], ...] = ()
    nonconformance_dispositions: tuple[tuple[str, str], ...] = ()
    open_nonconformance_count: int = 0


def query_approved_inspection_cases(
    session: Session,
    start_dt_utc: datetime | None = None,
    end_dt_utc: datetime | None = None,
) -> list[tuple[InspectionCase, DecisionSnapshotRow]]:
    """Fetch approved inspection cases for reporting per PRD 12.5.

    Rule 1: Approved inspection cases only (joined with DecisionSnapshotRow).
    Rule 2: Exclude CANCELLED status.

    # GAP (PRD 12.5): Test-data exclusion is unimplementable because the current
    # schema has no marker (e.g. is_test flag or test environment tag) to identify
    # test records. When a marker is introduced, add it to this shared query helper.
    """
    stmt = (
        select(InspectionCase, DecisionSnapshotRow)
        .join(
            DecisionSnapshotRow,
            DecisionSnapshotRow.inspection_case_id == InspectionCase.id,
        )
        .where(InspectionCase.status != "CANCELLED")
    )
    if start_dt_utc is not None:
        stmt = stmt.where(DecisionSnapshotRow.created_at >= start_dt_utc)
    if end_dt_utc is not None:
        stmt = stmt.where(DecisionSnapshotRow.created_at <= end_dt_utc)

    stmt = stmt.order_by(DecisionSnapshotRow.created_at, InspectionCase.id)
    return list(session.execute(stmt).tuples())


def period_bounds_utc(period_start: str, period_end: str) -> tuple[datetime, datetime]:
    """Convert an inclusive Asia/Seoul date window into UTC instants.

    The KST calendar is the one users read, so the window is defined there and
    translated at the database boundary rather than the other way round.
    """

    start_kst = datetime.combine(date.fromisoformat(period_start), time.min, tzinfo=SEOUL_TZ)
    end_kst = datetime.combine(date.fromisoformat(period_end), time.max, tzinfo=SEOUL_TZ)
    return start_kst.astimezone(UTC), end_kst.astimezone(UTC)


def build_statistics_rows(
    session: Session,
    start_dt_utc: datetime | None = None,
    end_dt_utc: datetime | None = None,
) -> list[StatisticsRow]:
    """Bridge the approved-case query onto the statistics row dataclasses.

    The bounds are pushed into SQL rather than filtered afterwards.  Each case costs
    several follow-up queries, so materialising the whole approved history for a
    one-month report degrades quadratically as the history grows.
    """

    rows: list[StatisticsRow] = []
    for case, snapshot in query_approved_inspection_cases(session, start_dt_utc, end_dt_utc):
        supplier_name = ""
        supplier_code = ""
        material_name = ""
        material_code = ""

        if case.receipt_lot_allocation_id:
            alloc = session.scalar(
                select(ReceiptLotAllocation).where(
                    ReceiptLotAllocation.id == case.receipt_lot_allocation_id
                )
            )
            if alloc and alloc.material_lot_id:
                lot = session.scalar(
                    select(MaterialLot).where(MaterialLot.id == alloc.material_lot_id)
                )
                if lot:
                    if lot.supplier_id:
                        sup = session.scalar(select(Supplier).where(Supplier.id == lot.supplier_id))
                        if sup:
                            supplier_name = str(sup.name or "")
                            supplier_code = str(sup.supplier_code or "")
                    if lot.material_id:
                        mat = session.scalar(select(Material).where(Material.id == lot.material_id))
                        if mat:
                            material_name = str(mat.name or "")
                            material_code = str(mat.material_code or "")

        has_coa = True
        if case.receipt_lot_allocation_id:
            coa_doc = session.scalar(
                select(Document)
                .join(DocumentSection, DocumentSection.document_id == Document.id)
                .join(
                    DocumentAllocationLink,
                    DocumentAllocationLink.document_section_id == DocumentSection.id,
                )
                .where(
                    DocumentAllocationLink.receipt_lot_allocation_id
                    == case.receipt_lot_allocation_id,
                    Document.document_type == "COA",
                    Document.deleted_at.is_(None),
                )
            )
            has_coa = coa_doc is not None

        ncs = list(
            session.scalars(
                select(Nonconformance).where(
                    Nonconformance.inspection_case_id == case.id,
                    Nonconformance.deleted_at.is_(None),
                )
            )
        )
        nonconformance_dispositions: list[tuple[str, str]] = []
        open_ncr_count = 0
        for nc in ncs:
            if nc.status != "CLOSED":
                open_ncr_count += 1
            if nc.disposition_id:
                disp = session.scalar(
                    select(NonconformanceDisposition).where(
                        NonconformanceDisposition.id == nc.disposition_id
                    )
                )
                if disp:
                    nonconformance_dispositions.append((str(disp.code), str(disp.name)))

        payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}

        # These were previously derived from the *current* case status being
        # SUPPLIER_REVIEW or INTERNAL_TEST_PENDING.  Every case in this population is
        # already approved and has therefore left both states, so both flags were
        # structurally always False and the derived rates always read 0.0.  A metric
        # that silently reads zero is worse than an absent one: "OCR 수동 검토율 0%"
        # asserts the exact opposite of this system's core invariant, which is that
        # every extraction is a candidate needing human review.
        #
        # internal_test_required is recovered from the frozen source policies, which
        # are the values that actually decided whether internal testing was owed.
        source_policies = payload.get("source_policy", [])
        internal_required = isinstance(source_policies, list) and any(
            str(policy)
            in {
                "INTERNAL_ONLY",
                "BOTH_INTERNAL_PRIORITY",
                "BOTH_ALL_MUST_PASS",
                "SUPPLIER_REFERENCE_INTERNAL_FINAL",
            }
            for policy in source_policies
        )
        # internal_test_completed is recovered from the rows that record the work.
        internal_completed = (
            session.scalar(
                select(InternalResult.id)
                .where(InternalResult.inspection_case_id == case.id)
                .limit(1)
            )
            is not None
        )
        # ocr_review_required has no persisted counterpart: review_required lives on a
        # runtime extraction candidate and is never stored per case.  It is left False
        # here and the aggregate reports it as unmeasured rather than as a rate.
        ocr_required = False

        reasons = payload.get("decision_reasons", {})
        final_decision_val = (
            str(case.final_decision)
            if case.final_decision
            else (str(reasons.get("final", "")) or None)
        )

        rows.append(
            StatisticsRow(
                inspection_case_id=str(case.id),
                snapshot_created_at=snapshot.created_at,
                status=str(case.status),
                final_decision=final_decision_val,
                material_code=material_code,
                material_name=material_name,
                supplier_code=supplier_code,
                supplier_name=supplier_name,
                created_at=case.created_at,
                has_coa_document=has_coa,
                ocr_review_required=ocr_required,
                internal_test_required=internal_required,
                internal_test_completed=internal_completed,
                nonconformance_dispositions=tuple(nonconformance_dispositions),
                open_nonconformance_count=open_ncr_count,
            )
        )
    return rows


def calculate_quality_statistics_data(
    rows: Sequence[StatisticsRow | dict[str, Any]],
    period_start: str,
    period_end: str,
    observed_at: datetime,
    excluded_cancelled_count: int = 0,
) -> dict[str, Any]:
    """Shared calculation engine that powers both the JSON endpoint and Excel report."""
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    start_dt_kst = datetime.combine(start_date, time.min, tzinfo=SEOUL_TZ)
    end_dt_kst = datetime.combine(end_date, time.max, tzinfo=SEOUL_TZ)

    stamp = observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")

    filtered_rows: list[dict[str, Any]] = []
    for r in rows:
        r_dict = (
            {
                "inspection_case_id": r.inspection_case_id,
                "snapshot_created_at": r.snapshot_created_at,
                "status": r.status,
                "final_decision": r.final_decision,
                "material_code": r.material_code,
                "material_name": r.material_name,
                "supplier_code": r.supplier_code,
                "supplier_name": r.supplier_name,
                "created_at": r.created_at,
                "has_coa_document": r.has_coa_document,
                "ocr_review_required": r.ocr_review_required,
                "internal_test_required": r.internal_test_required,
                "internal_test_completed": r.internal_test_completed,
                "failed_test_items": r.failed_test_items,
                "nonconformance_dispositions": r.nonconformance_dispositions,
                "open_nonconformance_count": r.open_nonconformance_count,
            }
            if isinstance(r, StatisticsRow)
            else dict(r)
        )
        snap_dt_val = r_dict.get("snapshot_created_at")
        if not isinstance(snap_dt_val, datetime):
            continue
        snap_dt = (
            snap_dt_val if snap_dt_val.tzinfo is not None else snap_dt_val.replace(tzinfo=UTC)
        )
        snap_dt_kst = snap_dt.astimezone(SEOUL_TZ)

        if start_dt_kst <= snap_dt_kst <= end_dt_kst:
            r_dict["_snap_dt_kst"] = snap_dt_kst
            filtered_rows.append(r_dict)

    total_count = len(filtered_rows)

    # Monthly breakdown
    monthly_counts: dict[str, int] = defaultdict(int)
    for r in filtered_rows:
        m_str = r["_snap_dt_kst"].strftime("%Y-%m")
        monthly_counts[m_str] += 1

    monthly_list: list[dict[str, Any]] = []
    for m in sorted(monthly_counts):
        monthly_list.append(
            {
                "month": m,
                "receipt_count": monthly_counts[m],
                "inspection_count": monthly_counts[m],
            }
        )

    # Decision counts
    decision_counts: dict[str, int] = defaultdict(int)
    handling_seconds_total = 0.0
    defect_case_count = 0
    coa_missing_count = 0
    ocr_review_count = 0
    internal_pending_count = 0
    total_open_ncr_count = 0

    supplier_total: dict[str, int] = defaultdict(int)
    supplier_defects: dict[str, int] = defaultdict(int)

    material_total: dict[str, int] = defaultdict(int)
    material_defects: dict[str, int] = defaultdict(int)

    item_defects: dict[tuple[str, str], int] = defaultdict(int)
    disposition_counts: dict[tuple[str, str], int] = defaultdict(int)

    for r in filtered_rows:
        decision = str(r.get("final_decision") or "UNKNOWN")
        decision_counts[decision] += 1

        sup_name = str(r.get("supplier_name") or "미지정")
        supplier_total[sup_name] += 1

        mat_name = str(r.get("material_name") or "미지정")
        material_total[mat_name] += 1

        is_defect = decision in ("REJECTED", "SPECIAL_ACCEPTED") or bool(
            r.get("nonconformance_dispositions")
        )
        if is_defect:
            defect_case_count += 1
            supplier_defects[sup_name] += 1
            material_defects[mat_name] += 1

        s_val = r.get("snapshot_created_at")
        c_val = r.get("created_at")
        if isinstance(s_val, datetime) and isinstance(c_val, datetime):
            s_dt = s_val if s_val.tzinfo is not None else s_val.replace(tzinfo=UTC)
            c_dt = c_val if c_val.tzinfo is not None else c_val.replace(tzinfo=UTC)
            delta = (s_dt - c_dt).total_seconds()
            if delta > 0:
                handling_seconds_total += delta

        if not r.get("has_coa_document", True) or r.get("status") == "DOCUMENT_PENDING":
            coa_missing_count += 1

        if r.get("ocr_review_required", False) or r.get("status") == "SUPPLIER_REVIEW":
            ocr_review_count += 1

        internal_pending = (
            r.get("internal_test_required", False)
            and not r.get("internal_test_completed", False)
        ) or r.get("status") == "INTERNAL_TEST_PENDING"
        if internal_pending:
            internal_pending_count += 1

        total_open_ncr_count += int(r.get("open_nonconformance_count", 0))

        failed_items = r.get("failed_test_items", ())
        if isinstance(failed_items, (list, tuple)):
            for item in failed_items:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    item_defects[(str(item[0]), str(item[1]))] += 1

        disps = r.get("nonconformance_dispositions", ())
        if isinstance(disps, (list, tuple)):
            for item in disps:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    disposition_counts[(str(item[0]), str(item[1]))] += 1

    by_decision: list[dict[str, Any]] = [
        {"decision": k, "count": v}
        for k, v in sorted(decision_counts.items(), key=lambda x: (-x[1], x[0]))
    ]

    by_supplier: list[dict[str, Any]] = []
    for sup_name in sorted(supplier_total):
        inspected = supplier_total[sup_name]
        defective = supplier_defects[sup_name]
        rate_val = (
            (Decimal(defective) / Decimal(inspected) * Decimal(100))
            if inspected > 0
            else Decimal(0)
        )
        by_supplier.append(
            {
                "supplier_name": sup_name,
                "inspected": inspected,
                "defective": defective,
                "defect_rate": f"{rate_val:.2f}%",
            }
        )

    by_material: list[dict[str, Any]] = []
    for mat_name in sorted(material_total):
        inspected = material_total[mat_name]
        defective = material_defects[mat_name]
        rate_val = (
            (Decimal(defective) / Decimal(inspected) * Decimal(100))
            if inspected > 0
            else Decimal(0)
        )
        by_material.append(
            {
                "material_name": mat_name,
                "inspected": inspected,
                "defective": defective,
                "defect_rate": f"{rate_val:.2f}%",
            }
        )

    # No OCR review rate is computed on purpose; see OCR_REVIEW_RATE_UNMEASURED.
    avg_days_val = (
        (Decimal(str(handling_seconds_total)) / Decimal(total_count) / Decimal(86400))
        if total_count > 0
        else Decimal(0)
    )

    return {
        "period_start": period_start,
        "period_end": period_end,
        "observed_at": stamp,
        "population": {
            "approved_case_count": total_count,
            "excluded_cancelled_count": excluded_cancelled_count,
        },
        "monthly": monthly_list,
        "by_decision": by_decision,
        "by_supplier": by_supplier,
        "by_material": by_material,
        "coa_missing_count": coa_missing_count,
        # Reported as unmeasured, never as a rate.  Nothing in the schema records
        # whether a case's extraction demanded human review, so any number here
        # would be fabricated -- and a fabricated 0% would read as "OCR needs no
        # review", the precise opposite of what this system guarantees.
        "ocr_review_rate": OCR_REVIEW_RATE_UNMEASURED,
        "internal_test_pending_count": internal_pending_count,
        "average_handling_days": f"{avg_days_val:.2f}",
        "open_nonconformance_count": total_open_ncr_count,
        "_item_defects": item_defects,
        "_disposition_counts": disposition_counts,
        "_defect_case_count": defect_case_count,
    }


def render_supplier_quality_statistics_report(
    rows: Sequence[StatisticsRow | dict[str, Any]],
    period_start: str,
    period_end: str,
    observed_at: datetime,
) -> bytes:
    """Render REP-004 monthly supplier quality statistics report as Excel workbook."""
    data = calculate_quality_statistics_data(rows, period_start, period_end, observed_at)
    lookup_lbl = f"조회 시점 {data['observed_at']}"
    total_count = data["population"]["approved_case_count"]

    by_dec = data["by_decision"]
    accepted_count = next((d["count"] for d in by_dec if d["decision"] == "ACCEPTED"), 0)
    rejected_count = next((d["count"] for d in by_dec if d["decision"] == "REJECTED"), 0)
    special_accepted_count = next(
        (d["count"] for d in by_dec if d["decision"] == "SPECIAL_ACCEPTED"), 0
    )
    retest_count = next((d["count"] for d in by_dec if d["decision"] == "RETEST"), 0)
    on_hold_count = next((d["count"] for d in by_dec if d["decision"] == "ON_HOLD"), 0)

    defect_case_count = data["_defect_case_count"]
    defect_rate_val = (
        (Decimal(defect_case_count) / Decimal(total_count) * Decimal(100))
        if total_count > 0
        else Decimal(0)
    )
    coa_missing_rate_val = (
        (Decimal(data["coa_missing_count"]) / Decimal(total_count) * Decimal(100))
        if total_count > 0
        else Decimal(0)
    )

    # 1. 품질통계요약 Sheet
    summary_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["지표명", "수치", "비고"],
        ["조회 기간", f"{period_start} ~ {period_end}", "KST 기준 산출"],
        ["총 입고/검사 건수", str(total_count), "승인 완료 건 대상"],
        ["적합 건수", str(accepted_count), ""],
        ["부적합 건수", str(rejected_count), ""],
        ["특채 건수", str(special_accepted_count), ""],
        ["재검사 건수", str(retest_count), ""],
        ["보류 건수", str(on_hold_count), ""],
        ["부적합률", f"{defect_rate_val:.2f}%", f"{defect_case_count}/{total_count}"],
        ["평균 처리기간 (일)", data["average_handling_days"], "입고/작성 후 승인 시점까지"],
        [
            "COA 누락률",
            f"{coa_missing_rate_val:.2f}%",
            f"{data['coa_missing_count']}/{total_count}",
        ],
        ["OCR 검토 필요율", data["ocr_review_rate"], f"{data['ocr_review_rate']}"],
        [
            "자체검사 완료율",
            "100.00%",
            "자체검사 완료건 대상",
        ],
    ]

    # 2. 품목별부적합 Sheet
    mat_defect_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["품목 코드", "품목명", "부적합 건수", "부적합률"],
    ]
    for item in data["by_material"]:
        mat_defect_rows.append(
            [
                item["material_name"],
                item["material_name"],
                str(item["defective"]),
                item["defect_rate"],
            ]
        )


    # 3. 검사항목별부적합 Sheet
    item_defect_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["검사항목 코드", "검사항목명", "부적합 건수"],
    ]
    for (code, name), count in sorted(data["_item_defects"].items()):
        item_defect_rows.append([code, name, str(count)])

    # 4. 부적합처리방안 Sheet
    disposition_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["처리방안 코드", "처리방안명", "건수"],
    ]
    for (code, name), count in sorted(data["_disposition_counts"].items()):
        disposition_rows.append([code, name, str(count)])

    sheets = [
        SheetSpec(title="품질통계요약", rows=summary_rows),
        SheetSpec(title="품목별부적합", rows=mat_defect_rows),
        SheetSpec(title="검사항목별부적합", rows=item_defect_rows),
        SheetSpec(title="부적합처리방안", rows=disposition_rows),
    ]

    return render_workbook(sheets)
