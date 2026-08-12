"""P6-6 OCR operational monitoring.

Counts what the extraction tables already record.  No new table is created: a
separate metrics store would drift from the rows it summarises, and at this
volume there is nothing to gain by paying for that risk.

This module deliberately contains no pass/fail threshold.  PRD 3.3 requires a
baseline measured from real operating data before any KPI target is set, and no
COA corpus exists yet (P4-B is unapproved).  A number invented here would harden
into a standard nobody measured, so the API reports observations only and the
caller is told the thresholds are absent rather than met.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hyc_data.models import ExtractionFieldReview, ExtractionRun

#: Returned in place of any rate that has no denominator yet.  Kept as a string so
#: a caller renders it verbatim instead of formatting a misleading 0.
NO_OBSERVATIONS = "관측 없음"


@dataclass(frozen=True, slots=True)
class OcrOperationsSnapshot:
    """A point-in-time observation of extraction activity."""

    observed_at: datetime
    run_count: int
    runs_by_status: list[tuple[str, int]]
    runs_by_provider: list[tuple[str, int]]
    field_count: int
    fields_awaiting_review: int
    review_completion_rate: str
    low_confidence_field_count: int
    conflict_run_count: int

    def as_payload(self) -> dict[str, Any]:
        return {
            "observed_at": self.observed_at.astimezone(UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "run_count": self.run_count,
            "runs_by_status": [
                {"status": status, "count": count} for status, count in self.runs_by_status
            ],
            "runs_by_provider": [
                {"provider_name": provider, "count": count}
                for provider, count in self.runs_by_provider
            ],
            "field_count": self.field_count,
            "fields_awaiting_review": self.fields_awaiting_review,
            "review_completion_rate": self.review_completion_rate,
            "low_confidence_field_count": self.low_confidence_field_count,
            "conflict_run_count": self.conflict_run_count,
            # Stated in the payload rather than only in documentation: a consumer
            # must not read the absence of a threshold as everything being within one.
            "kpi_thresholds": None,
            "kpi_threshold_note": (
                "KPI 임계값은 정의되지 않았습니다. PRD 3.3에 따라 초기 운영 데이터로 "
                "기준선을 측정한 뒤에만 설정할 수 있습니다."
            ),
        }


def _rate(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return NO_OBSERVATIONS
    value = Decimal(numerator) / Decimal(denominator) * Decimal(100)
    return f"{value:.2f}%"


def _low_confidence_threshold() -> Decimal:
    """The value below which a field is *counted*, not judged.

    This is a reporting bucket boundary, not a quality gate: nothing accepts or
    rejects on it, and it never gates a decision.
    """

    return Decimal("1.00")


def collect_ocr_operations(
    session: Session,
    observed_at: datetime | None = None,
) -> OcrOperationsSnapshot:
    run_rows: Sequence[tuple[str, int]] = tuple(
        session.execute(
            select(ExtractionRun.status, func.count(ExtractionRun.id))
            .group_by(ExtractionRun.status)
            .order_by(ExtractionRun.status)
        ).tuples()
    )
    provider_rows: Sequence[tuple[str, int]] = tuple(
        session.execute(
            select(ExtractionRun.provider_name, func.count(ExtractionRun.id))
            .group_by(ExtractionRun.provider_name)
            .order_by(ExtractionRun.provider_name)
        ).tuples()
    )
    run_count = sum(count for _, count in run_rows)

    field_count = int(
        session.scalar(select(func.count(ExtractionFieldReview.id))) or 0
    )
    awaiting = int(
        session.scalar(
            select(func.count(ExtractionFieldReview.id)).where(
                ExtractionFieldReview.status == "REVIEW_REQUIRED"
            )
        )
        or 0
    )
    low_confidence = int(
        session.scalar(
            select(func.count(ExtractionFieldReview.id)).where(
                ExtractionFieldReview.confidence < _low_confidence_threshold()
            )
        )
        or 0
    )
    conflict_runs = int(
        session.scalar(
            select(func.count(ExtractionRun.id)).where(
                func.json_array_length(ExtractionRun.conflicts) > 0
            )
        )
        or 0
    )

    return OcrOperationsSnapshot(
        observed_at=observed_at or datetime.now(UTC),
        run_count=run_count,
        runs_by_status=[(str(s), int(c)) for s, c in run_rows],
        runs_by_provider=[(str(p), int(c)) for p, c in provider_rows],
        field_count=field_count,
        fields_awaiting_review=awaiting,
        review_completion_rate=_rate(field_count - awaiting, field_count),
        low_confidence_field_count=low_confidence,
        conflict_run_count=conflict_runs,
    )
