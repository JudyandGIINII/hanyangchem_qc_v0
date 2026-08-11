from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import ReportArtifact, ReportJob

POSTGRES_DSN = os.environ.get("HYC_P3_TEST_POSTGRES_DSN") or os.environ.get(
    "HYC_P2_TEST_POSTGRES_DSN"
)
pytestmark = pytest.mark.postgres

_DOMAIN_INVARIANT_SQLSTATE = "P0001"


@pytest.fixture(scope="module")
def engine() -> Engine:
    if not POSTGRES_DSN:
        pytest.skip("HYC_P3_TEST_POSTGRES_DSN must name a disposable PostgreSQL database")
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_DSN)
    command.upgrade(config, "head")
    value = create_engine(POSTGRES_DSN)
    yield value
    command.downgrade(config, "base")
    with value.connect() as connection:
        remaining = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        )
        assert remaining.scalar_one() == 0
    value.dispose()


def _sqlstate(error: DBAPIError) -> str | None:
    original = getattr(error, "orig", None)
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


def _seed_succeeded_job(session: Session) -> tuple[UUID, UUID]:
    job = ReportJob(
        kind="INTEGRATED_INSPECTION",
        parameters={"inspection_case_id": str(uuid4()), "include_audit": False},
        state="SUCCEEDED",
        requested_by_id=uuid4(),
        actor_role="LEAD",
    )
    session.add(job)
    session.flush()
    artifact = ReportArtifact(
        report_job_id=job.id,
        content_digest="a" * 64,
        storage_key="reports/2026/08/test.xlsx",
        byte_size=1024,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    session.add(artifact)
    session.commit()
    return job.id, artifact.id


def test_report_artifact_update_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        job_id, artifact_id = _seed_succeeded_job(session)
        with pytest.raises(DBAPIError) as caught:
            session.execute(
                text("UPDATE report_artifacts SET byte_size = 2048 WHERE id = :id"),
                {"id": artifact_id},
            )
        session.rollback()
        assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE


def test_report_artifact_delete_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        job_id, artifact_id = _seed_succeeded_job(session)
        with pytest.raises(DBAPIError) as caught:
            session.execute(
                text("DELETE FROM report_artifacts WHERE id = :id"),
                {"id": artifact_id},
            )
        session.rollback()
        assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE


def test_report_artifact_insert_still_works(engine: Engine) -> None:
    with Session(engine) as session:
        job_id, artifact_id = _seed_succeeded_job(session)
        stored = session.execute(
            text("SELECT content_digest FROM report_artifacts WHERE id = :id"),
            {"id": artifact_id},
        ).scalar_one()
        assert stored == "a" * 64
