from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from hyc_api.config import Settings
from hyc_api.document_locks import DigestOwnershipGuard
from hyc_api.main import create_app


def _postgres_test_url() -> str:
    return URL.create(
        "postgresql+psycopg",
        "local_user",
        "placeholder",
        "localhost",
        database="hyc",
    ).render_as_string(False)


def _different_stripe_digest(digest: str) -> str:
    for index in range(1, 1024):
        candidate = hashlib.sha256(f"other-{index}".encode()).hexdigest()
        if DigestOwnershipGuard._stripe_index(candidate) != DigestOwnershipGuard._stripe_index(
            digest
        ):
            return candidate
    raise AssertionError("could not select a separate process-lock stripe")


def test_process_digest_guard_blocks_same_digest_but_not_a_different_stripe() -> None:
    """The stable guard is independent of any mutable filesystem lock inode."""

    engine = create_engine("sqlite+pysqlite:///:memory:")
    digest = hashlib.sha256(b"stable guard fixture").hexdigest()
    different_digest = _different_stripe_digest(digest)
    first = DigestOwnershipGuard(Session(engine), digest)
    same = DigestOwnershipGuard(Session(engine), digest)
    different = DigestOwnershipGuard(Session(engine), different_digest)
    same_entered = threading.Event()
    different_entered = threading.Event()
    release_same = threading.Event()

    def acquire_then_release_same() -> None:
        same.acquire()
        same_entered.set()
        assert release_same.wait(timeout=2)
        same.release()

    first.acquire()
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            same_future = executor.submit(acquire_then_release_same)
            different.acquire()
            different_entered.set()
            different.release()
            assert different_entered.is_set()
            assert not same_entered.is_set()
            first.release()
            assert same_entered.wait(timeout=2)
            release_same.set()
            same_future.result(timeout=2)
    finally:
        different.release()
        first.release()
        engine.dispose()


def test_postgres_app_wires_an_independent_nullpool_lock_engine_and_disposes_both() -> None:
    app = create_app(
        Settings(database_url=_postgres_test_url())
    )
    application_engine = app.state.engine
    lock_engine = app.state.document_lock_engine
    assert lock_engine is not None
    assert application_engine.dialect.name == "postgresql"
    assert lock_engine.dialect.name == "postgresql"
    assert isinstance(lock_engine.pool, NullPool)
    assert lock_engine.pool is not application_engine.pool

    disposed: list[str] = []
    event.listen(application_engine, "engine_disposed", lambda _: disposed.append("application"))
    event.listen(lock_engine, "engine_disposed", lambda _: disposed.append("lock"))
    with TestClient(app):
        pass
    assert sorted(disposed) == ["application", "lock"]


def test_postgres_guard_fails_closed_without_an_independent_nullpool() -> None:
    application_engine = create_engine(_postgres_test_url())
    non_postgres_lock_engine = create_engine("sqlite+pysqlite:///:memory:", poolclass=NullPool)
    sqlite_engine = create_engine("sqlite+pysqlite:///:memory:")
    digest = hashlib.sha256(b"fail closed lock engine fixture").hexdigest()
    session = Session(application_engine)
    sqlite_session = Session(sqlite_engine)
    try:
        with pytest.raises(RuntimeError, match="independent NullPool"):
            DigestOwnershipGuard(session, digest).acquire()
        # The failed PostgreSQL acquisition must have released its process
        # stripe; the non-PostgreSQL fallback can take that same stripe.
        sqlite_guard = DigestOwnershipGuard(sqlite_session, digest)
        sqlite_guard.acquire()
        sqlite_guard.release()
        with pytest.raises(RuntimeError, match="independent NullPool"):
            DigestOwnershipGuard(session, digest, application_engine).acquire()
        with pytest.raises(RuntimeError, match="independent NullPool"):
            DigestOwnershipGuard(session, digest, non_postgres_lock_engine).acquire()
    finally:
        session.close()
        sqlite_session.close()
        sqlite_engine.dispose()
        non_postgres_lock_engine.dispose()
        application_engine.dispose()


def test_sqlite_app_does_not_create_a_document_lock_engine() -> None:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    try:
        assert app.state.document_lock_engine is None
    finally:
        app.state.engine.dispose()
