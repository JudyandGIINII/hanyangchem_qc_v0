from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal
from hyc_api.contracts import QualityStatisticsResponse
from hyc_api.dependencies import database_session
from hyc_api.reports.statistics import (
    build_statistics_rows,
    calculate_quality_statistics_data,
    period_bounds_utc,
)
from hyc_data.models import DecisionSnapshotRow, InspectionCase

router = APIRouter(prefix="/api/v1", tags=["p6-statistics"])
DBSession = Annotated[Session, Depends(database_session)]


@router.get(
    "/statistics/quality",
    response_model=QualityStatisticsResponse,
    status_code=status.HTTP_200_OK,
)
def get_quality_statistics(
    request: Request,
    period_start: str,
    period_end: str,
    session: DBSession,
) -> QualityStatisticsResponse:
    require_principal(request)

    try:
        start_date = date.fromisoformat(period_start)
        end_date = date.fromisoformat(period_end)
    except ValueError as error:
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid date format for period_start or period_end. "
                "Expected ISO date YYYY-MM-DD"
            ),
        ) from error

    if start_date > end_date:
        raise HTTPException(
            status_code=422,
            detail="period_start cannot be after period_end",
        )

    # Bounds are pushed into SQL. Loading the whole approved history for a one-month
    # report costs several follow-up queries per case and degrades quadratically.
    start_utc, end_utc = period_bounds_utc(period_start, period_end)
    rows = build_statistics_rows(session, start_utc, end_utc)

    # Excluded CANCELLED count in period (or overall)
    cancelled_stmt = (
        select(func.count(InspectionCase.id))
        .join(
            DecisionSnapshotRow,
            DecisionSnapshotRow.inspection_case_id == InspectionCase.id,
        )
        .where(InspectionCase.status == "CANCELLED")
    )
    excluded_cancelled_count = session.scalar(cancelled_stmt) or 0

    now_utc = datetime.now(UTC)
    data = calculate_quality_statistics_data(
        rows,
        period_start=period_start,
        period_end=period_end,
        observed_at=now_utc,
        excluded_cancelled_count=excluded_cancelled_count,
    )

    clean_data = {k: v for k, v in data.items() if not k.startswith("_")}
    return QualityStatisticsResponse.model_validate(clean_data)

