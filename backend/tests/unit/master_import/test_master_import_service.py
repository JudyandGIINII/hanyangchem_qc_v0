from __future__ import annotations

from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from hyc_api.auth import Principal
from hyc_api.master_import import synthesize_master_import_workbook
from hyc_api.services.master_import import (
    apply_master_import,
    preview_master_import,
    revert_master_import,
)
from hyc_data.models import Base, Material

# No postgres marker: the fixture uses sqlite, so these run in `make check`.


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
    engine.dispose()


@pytest.fixture
def lead() -> Principal:
    return Principal(uuid4(), "LEAD", "fixture-lead")


def _preview(session: Session, lead: Principal, rows: list[tuple[str, str]]) -> dict:
    workbook = synthesize_master_import_workbook("MATERIAL", rows)
    return preview_master_import(
        session,
        workbook_bytes=workbook,
        entity="MATERIAL",
        source_filename="master.xlsx",
        principal=lead,
    )


def test_preview_records_a_plan_without_touching_the_master_table(
    session: Session, lead: Principal
) -> None:
    body = _preview(session, lead, [("M-01", "염화칼슘"), ("M-02", "비드")])
    assert body["state"] == "PREVIEWED"
    assert len(body["rows"]) == 2
    # The whole point of a preview: nothing is written to the master yet.
    assert session.scalars(select(Material)).all() == []


def test_apply_creates_rows_and_marks_the_batch_applied(
    session: Session, lead: Principal
) -> None:
    body = _preview(session, lead, [("M-01", "염화칼슘")])
    applied = apply_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    assert applied["state"] == "APPLIED"
    names = [m.name for m in session.scalars(select(Material))]
    assert names == ["염화칼슘"]


def test_applying_twice_is_rejected(session: Session, lead: Principal) -> None:
    # Without this a retried request would double-write every created row.
    body = _preview(session, lead, [("M-01", "염화칼슘")])
    apply_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    with pytest.raises(HTTPException) as caught:
        apply_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    assert caught.value.status_code == 409


def test_a_batch_with_any_rejected_row_applies_nothing(
    session: Session, lead: Principal
) -> None:
    # Partial application would leave the master half-updated with no record of
    # which half, so the whole file must refuse.
    body = _preview(session, lead, [("M-01", "염화칼슘"), ("M-02", "")])
    assert any(row["action"] == "REJECT" for row in body["rows"])
    with pytest.raises(HTTPException) as caught:
        apply_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    assert caught.value.status_code == 409
    assert session.scalars(select(Material)).all() == []


def test_revert_soft_deletes_only_what_the_batch_created(
    session: Session, lead: Principal
) -> None:
    pre_existing = Material(name="기존 품목", material_code="M-OLD")
    session.add(pre_existing)
    session.flush()

    body = _preview(session, lead, [("M-01", "염화칼슘")])
    apply_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    reverted = revert_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)

    assert reverted["state"] == "REVERTED"
    live = [m.name for m in session.scalars(select(Material)) if m.deleted_at is None]
    assert live == ["기존 품목"]


def test_reverting_a_batch_that_was_never_applied_is_rejected(
    session: Session, lead: Principal
) -> None:
    body = _preview(session, lead, [("M-01", "염화칼슘")])
    with pytest.raises(HTTPException) as caught:
        revert_master_import(session, batch_id=UUID(body["batch_id"]), principal=lead)
    assert caught.value.status_code == 409


def test_apply_requires_a_recorded_preview(session: Session, lead: Principal) -> None:
    # An unknown batch id must not be treated as an implicit preview, or the
    # human confirmation step could be skipped entirely.
    with pytest.raises(HTTPException) as caught:
        apply_master_import(session, batch_id=uuid4(), principal=lead)
    assert caught.value.status_code == 404
