from __future__ import annotations

import re
from collections.abc import Generator
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hyc_api.reports.ocr_operations import (
    NO_OBSERVATIONS,
    collect_ocr_operations,
)
from hyc_data.models import Base, Document, ExtractionFieldReview, ExtractionRun

# No postgres marker: the fixture falls back to sqlite, so these run in `make check`.
# A module-level marker would deselect them there while no postgres gate covers
# unit/ either, which would leave them running nowhere.


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


def _document(session: Session) -> Document:
    # checksum_sha256 is unique by constraint, so each document needs its own digest.
    digest = f"{uuid4().hex}{uuid4().hex}"
    document = Document(
        checksum_sha256=digest,
        document_type="COA",
        original_filename="coa.pdf",
        media_type="application/pdf",
        size_bytes=10,
        storage_key=f"{digest[:2]}/{digest}",
    )
    session.add(document)
    session.flush()
    return document


def _run(session: Session, *, status: str, provider: str, conflicts: list[dict]) -> ExtractionRun:
    run = ExtractionRun(
        document_id=_document(session).id,
        provider_name=provider,
        status=status,
        candidate_payload={},
        conflicts=conflicts,
    )
    session.add(run)
    session.flush()
    return run


def _field(session: Session, run: ExtractionRun, *, status: str, confidence: str) -> None:
    session.add(
        ExtractionFieldReview(
            extraction_run_id=run.id,
            field_key=f"f-{uuid4().hex[:8]}",
            original_text="1.00",
            ocr_text="1.00",
            confidence=Decimal(confidence),
            page_number=1,
            bbox={},
            status=status,
        )
    )
    session.flush()


def test_empty_database_reports_no_observations_never_a_rate(session: Session) -> None:
    # A 0% completion rate would read as "nothing has been reviewed", which is a
    # different claim from "nothing has been extracted yet".
    snapshot = collect_ocr_operations(session)
    assert snapshot.run_count == 0
    assert snapshot.review_completion_rate == NO_OBSERVATIONS
    assert "%" not in snapshot.review_completion_rate


def test_counts_runs_by_status_and_provider(session: Session) -> None:
    _run(session, status="REVIEW_REQUIRED", provider="local-paddleocr", conflicts=[])
    _run(session, status="CONFIRMED", provider="local-paddleocr", conflicts=[])
    _run(session, status="CONFIRMED", provider="fixture", conflicts=[])

    snapshot = collect_ocr_operations(session)
    assert snapshot.run_count == 3
    assert snapshot.runs_by_status == [("CONFIRMED", 2), ("REVIEW_REQUIRED", 1)]
    assert snapshot.runs_by_provider == [("fixture", 1), ("local-paddleocr", 2)]


def test_review_completion_rate_reflects_outstanding_fields(session: Session) -> None:
    run = _run(session, status="REVIEW_REQUIRED", provider="local-paddleocr", conflicts=[])
    _field(session, run, status="CONFIRMED", confidence="1.00")
    _field(session, run, status="CONFIRMED", confidence="1.00")
    _field(session, run, status="REVIEW_REQUIRED", confidence="1.00")
    _field(session, run, status="REVIEW_REQUIRED", confidence="1.00")

    snapshot = collect_ocr_operations(session)
    assert snapshot.field_count == 4
    assert snapshot.fields_awaiting_review == 2
    assert snapshot.review_completion_rate == "50.00%"


def test_low_confidence_fields_are_counted_not_judged(session: Session) -> None:
    run = _run(session, status="REVIEW_REQUIRED", provider="local-paddleocr", conflicts=[])
    _field(session, run, status="REVIEW_REQUIRED", confidence="0.42")
    _field(session, run, status="CONFIRMED", confidence="1.00")

    snapshot = collect_ocr_operations(session)
    assert snapshot.low_confidence_field_count == 1


def test_payload_states_that_no_kpi_threshold_exists(session: Session) -> None:
    # The absence of a threshold must be asserted in the payload, or a consumer
    # will read silence as "within target".
    payload = collect_ocr_operations(session).as_payload()
    assert payload["kpi_thresholds"] is None
    assert "PRD 3.3" in payload["kpi_threshold_note"]


def test_module_defines_no_pass_fail_threshold() -> None:
    # Structural guard, in the style used by the feature-flag suite: the module
    # must not grow a target/limit/goal constant without this test failing.
    source = (
        __import__("pathlib")
        .Path("backend/src/hyc_api/reports/ocr_operations.py")
        .read_text()
    )
    forbidden = re.compile(
        r"\b(THRESHOLD|TARGET|KPI_LIMIT|MIN_ACCURACY|PASS_RATE)\s*[:=]", re.IGNORECASE
    )
    offenders = [m.group(0) for m in forbidden.finditer(source)]
    assert offenders == [], f"pass/fail threshold introduced: {offenders}"
