from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import IngestCursor

POSTGRES_DSN = os.environ.get("HYC_P3_TEST_POSTGRES_DSN") or os.environ.get(
    "HYC_P2_TEST_POSTGRES_DSN"
)
pytestmark = pytest.mark.postgres


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


def test_ingest_cursor_persistence_and_uniqueness(engine: Engine) -> None:
    with Session(engine) as session:
        cursor = IngestCursor(
            id=uuid4(),
            source_id="nas_coa_folder",
            entry_id="2026/08/batch_001.pdf",
            status="PENDING_STABILITY",
            size_bytes=2048,
            modified_at=datetime.now(UTC),
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        session.add(cursor)
        session.commit()

        fetched = session.get(IngestCursor, cursor.id)
        assert fetched is not None
        assert fetched.source_id == "nas_coa_folder"
        assert fetched.entry_id == "2026/08/batch_001.pdf"
        assert fetched.status == "PENDING_STABILITY"


def test_ingest_cursor_unique_constraint(engine: Engine) -> None:
    with Session(engine) as session:
        c1 = IngestCursor(
            id=uuid4(),
            source_id="nas_dup_folder",
            entry_id="unique_file.pdf",
            status="PENDING_STABILITY",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        session.add(c1)
        session.commit()

        c2 = IngestCursor(
            id=uuid4(),
            source_id="nas_dup_folder",
            entry_id="unique_file.pdf",
            status="PENDING_STABILITY",
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
        )
        session.add(c2)
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()
