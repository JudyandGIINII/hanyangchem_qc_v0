from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.reports.deterministic import SheetSpec, render_workbook
from hyc_data.models import (
    DecisionSnapshotRow,
    InspectionCase,
    Material,
    MaterialLot,
    ReceiptLotAllocation,
)

SEOUL_TZ = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class StatisticsRow:
    """Input row representing an approved inspection case for statistics."""

    inspection_case_id: str
    snapshot_created_at: datetime
    status: str
    final_decision: str | None
    material_code: str
    material_name: str
    created_at: datetime | None = None
    has_coa_document: bool = True
    ocr_review_required: bool = False
    internal_test_required: bool = False
    internal_test_completed: bool = False
    failed_test_items: tuple[tuple[str, str], ...] = ()
    nonconformance_dispositions: tuple[tuple[str, str], ...] = ()


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


def build_statistics_rows(session: Session) -> list[StatisticsRow]:
    """Bridge the approved-case query onto the renderer's input rows.

    The renderer stays database-free so the sheet layout and the Asia/Seoul month
    bucketing remain unit-testable; this is the only place the two meet.  Period
    filtering deliberately happens in the renderer rather than here, so the KST
    calendar rule has exactly one implementation.
    """

    rows: list[StatisticsRow] = []
    for case, snapshot in query_approved_inspection_cases(session):
        material = session.execute(
            select(Material.material_code, Material.name)
            .select_from(InspectionCase)
            .join(
                ReceiptLotAllocation,
                InspectionCase.receipt_lot_allocation_id == ReceiptLotAllocation.id,
            )
            .join(MaterialLot, ReceiptLotAllocation.material_lot_id == MaterialLot.id)
            .join(Material, MaterialLot.material_id == Material.id)
            .where(InspectionCase.id == case.id)
        ).one_or_none()
        code, name = material if material is not None else ("", "")
        payload = snapshot.payload if isinstance(snapshot.payload, dict) else {}
        reasons = payload.get("decision_reasons", {})
        rows.append(
            StatisticsRow(
                inspection_case_id=str(case.id),
                snapshot_created_at=snapshot.created_at,
                status=case.status,
                final_decision=str(reasons.get("final", "")) or None,
                material_code=str(code or ""),
                material_name=str(name or ""),
                created_at=case.created_at,
            )
        )
    return rows


def render_supplier_quality_statistics_report(
    rows: Sequence[StatisticsRow | dict[str, Any]],
    period_start: str,
    period_end: str,
    observed_at: datetime,
) -> bytes:
    """Render REP-004 monthly supplier quality statistics report as Excel workbook."""
    start_date = date.fromisoformat(period_start)
    end_date = date.fromisoformat(period_end)

    start_dt_kst = datetime.combine(start_date, time.min, tzinfo=SEOUL_TZ)
    end_dt_kst = datetime.combine(end_date, time.max, tzinfo=SEOUL_TZ)

    stamp = observed_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    lookup_lbl = f"조회 시점 {stamp}"

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
                "created_at": r.created_at,
                "has_coa_document": r.has_coa_document,
                "ocr_review_required": r.ocr_review_required,
                "internal_test_required": r.internal_test_required,
                "internal_test_completed": r.internal_test_completed,
                "failed_test_items": r.failed_test_items,
                "nonconformance_dispositions": r.nonconformance_dispositions,
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
            filtered_rows.append(r_dict)

    total_count = len(filtered_rows)

    accepted_count = 0
    rejected_count = 0
    special_accepted_count = 0
    retest_count = 0
    on_hold_count = 0

    handling_seconds_total = 0.0
    defect_case_count = 0
    coa_missing_count = 0
    ocr_review_count = 0
    internal_required_count = 0
    internal_completed_count = 0

    material_total_cases: dict[str, int] = defaultdict(int)
    material_defect_cases: dict[str, int] = defaultdict(int)
    material_names: dict[str, str] = {}

    item_defects: dict[tuple[str, str], int] = defaultdict(int)
    disposition_counts: dict[tuple[str, str], int] = defaultdict(int)

    for r in filtered_rows:
        decision = str(r.get("final_decision") or "")
        if decision == "ACCEPTED":
            accepted_count += 1
        elif decision == "REJECTED":
            rejected_count += 1
        elif decision == "SPECIAL_ACCEPTED":
            special_accepted_count += 1
        elif decision == "RETEST":
            retest_count += 1
        elif decision == "ON_HOLD":
            on_hold_count += 1

        m_code = str(r.get("material_code", "UNKNOWN"))
        m_name = str(r.get("material_name", "미지정"))
        material_names[m_code] = m_name
        material_total_cases[m_code] += 1

        is_defect = False
        if decision in ("REJECTED", "SPECIAL_ACCEPTED") or bool(
            r.get("nonconformance_dispositions")
        ):
            is_defect = True

        if is_defect:
            defect_case_count += 1
            material_defect_cases[m_code] += 1

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

        if r.get("internal_test_required", False) or r.get("status") == "INTERNAL_TEST_PENDING":
            internal_required_count += 1
            if r.get("internal_test_completed", False):
                internal_completed_count += 1

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


    defect_rate = (defect_case_count / total_count) if total_count > 0 else 0.0
    avg_handling_days = (
        (handling_seconds_total / total_count / 86400.0) if total_count > 0 else 0.0
    )
    coa_missing_rate = (coa_missing_count / total_count) if total_count > 0 else 0.0
    ocr_review_rate = (ocr_review_count / total_count) if total_count > 0 else 0.0
    internal_completion_rate = (
        (internal_completed_count / internal_required_count)
        if internal_required_count > 0
        else 1.0
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
        ["부적합률", f"{defect_rate * 100:.2f}%", f"{defect_case_count}/{total_count}"],
        ["평균 처리기간 (일)", f"{avg_handling_days:.2f}", "입고/작성 후 승인 시점까지"],
        ["COA 누락률", f"{coa_missing_rate * 100:.2f}%", f"{coa_missing_count}/{total_count}"],
        ["OCR 검토 필요율", f"{ocr_review_rate * 100:.2f}%", f"{ocr_review_count}/{total_count}"],
        [
            "자체검사 완료율",
            f"{internal_completion_rate * 100:.2f}%",
            f"{internal_completed_count}/{internal_required_count}",
        ],
    ]

    # 2. 품목별부적합 Sheet
    mat_defect_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["품목 코드", "품목명", "부적합 건수", "부적합률"],
    ]
    for m_code in sorted(material_names):
        m_name = material_names[m_code]
        d_cnt = material_defect_cases[m_code]
        t_cnt = material_total_cases[m_code]
        m_rate = (d_cnt / t_cnt) if t_cnt > 0 else 0.0
        mat_defect_rows.append([m_code, m_name, str(d_cnt), f"{m_rate * 100:.2f}%"])

    # 3. 검사항목별부적합 Sheet
    item_defect_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["검사항목 코드", "검사항목명", "부적합 건수"],
    ]
    for (code, name), count in sorted(item_defects.items()):
        item_defect_rows.append([code, name, str(count)])

    # 4. 부적합처리방안 Sheet
    disposition_rows: list[list[str]] = [
        ["출처", lookup_lbl],
        ["처리방안 코드", "처리방안명", "건수"],
    ]
    for (code, name), count in sorted(disposition_counts.items()):
        disposition_rows.append([code, name, str(count)])

    sheets = [
        SheetSpec(title="품질통계요약", rows=summary_rows),
        SheetSpec(title="품목별부적합", rows=mat_defect_rows),
        SheetSpec(title="검사항목별부적합", rows=item_defect_rows),
        SheetSpec(title="부적합처리방안", rows=disposition_rows),
    ]

    return render_workbook(sheets)
