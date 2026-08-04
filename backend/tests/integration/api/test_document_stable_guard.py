from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool, QueuePool

import hyc_api.routes.documents as documents_module
import hyc_api.storage as storage_module
from hyc_api.document_locks import DigestOwnershipGuard
from hyc_api.storage import HashAddressedStorage, StoredDocumentReadError
from hyc_data.models import Document

pytestmark = pytest.mark.postgres


async def _single_chunk(body: bytes):
    yield body


def _different_stripe_digest(digest: str) -> str:
    for index in range(1, 1024):
        candidate = hashlib.sha256(f"other-stripe-{index}".encode()).hexdigest()
        if DigestOwnershipGuard._stripe_index(candidate) != DigestOwnershipGuard._stripe_index(
            digest
        ):
            return candidate
    raise AssertionError("could not select a separate process-lock stripe")


def test_postgres_digest_guard_uses_a_dedicated_session_lock_and_releases_it(
    p3_engine_storage,
) -> None:
    digest = hashlib.sha256(b"postgres stable guard fixture").hexdigest()
    first_session = p3_engine_storage.session_factory()
    second_session = p3_engine_storage.session_factory()
    inspector_session = p3_engine_storage.session_factory()
    first = DigestOwnershipGuard(first_session, digest, p3_engine_storage.document_lock_engine)
    second = DigestOwnershipGuard(second_session, digest, p3_engine_storage.document_lock_engine)
    entered = threading.Event()
    release_second = threading.Event()

    def acquire_then_release_second() -> None:
        second.acquire()
        entered.set()
        assert release_second.wait(timeout=2)
        second.release()

    try:
        first.acquire()
        assert first._connection is not None
        backend_pid = first._connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
        assert (
            inspector_session.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE locktype = 'advisory' AND pid = :pid AND granted"
                ),
                {"pid": backend_pid},
            ).scalar_one()
            == 1
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            waiting = executor.submit(acquire_then_release_second)
            assert not entered.wait(timeout=0.2)
            first.release()
            assert entered.wait(timeout=2)
            release_second.set()
            waiting.result(timeout=2)

        assert (
            inspector_session.execute(
                text(
                    "SELECT count(*) FROM pg_locks "
                    "WHERE locktype = 'advisory' AND pid = :pid AND granted"
                ),
                {"pid": backend_pid},
            ).scalar_one()
            == 0
        )
    finally:
        second.release()
        first.release()
        inspector_session.close()
        second_session.close()
        first_session.close()


def test_postgres_l1_l2_l1_l2_aba_serializes_cleanup_before_b_precommit(
    p3_engine_storage,
) -> None:
    """The stable guard serializes L1→L2→L1→L2 cleanup before B precommit."""

    body = f"P3 ABA split lock {uuid4().hex}".encode()
    digest = hashlib.sha256(body).hexdigest()
    root = p3_engine_storage.storage_root
    stripe = HashAddressedStorage._lock_name(digest)
    locks = root / ".locks"
    canonical_stripe = locks / stripe
    held_l1 = locks / f"{stripe}.held-l1"
    held_l2 = locks / f"{stripe}.held-l2"
    staged_l2 = locks / f"{stripe}.staged-l2"
    second_entered = threading.Event()
    second_acquired = threading.Event()
    canonical_object = root / digest[:2] / digest
    first_storage = HashAddressedStorage(str(root))
    second_storage = HashAddressedStorage(str(root))
    first = asyncio.run(first_storage.put_stream(_single_chunk(body)))
    assert first.created
    first_session = p3_engine_storage.session_factory()
    first_guard = DigestOwnershipGuard(
        first_session, digest, p3_engine_storage.document_lock_engine
    )
    second_allow_release = threading.Event()
    second_finished = threading.Event()
    second_errors: list[BaseException] = []

    def acquire_second_guard() -> None:
        session = p3_engine_storage.session_factory()
        guard = DigestOwnershipGuard(session, digest, p3_engine_storage.document_lock_engine)
        second_entered.set()
        try:
            guard.acquire()
            second_acquired.set()
            assert second_allow_release.wait(timeout=5)
        except BaseException as error:
            second_errors.append(error)
        finally:
            guard.release()
            session.close()
            second_finished.set()

    second_thread: threading.Thread | None = None
    second = None
    try:
        first_guard.acquire()
        assert canonical_object.exists()
        assert canonical_stripe.exists()

        os.link(canonical_stripe, held_l1)
        staged_l2.touch()
        os.replace(staged_l2, canonical_stripe)
        l2_metadata = canonical_stripe.stat()

        second = asyncio.run(second_storage.put_stream(_single_chunk(body)))
        assert not second.created
        assert (second._lock_dev, second._lock_ino) == (l2_metadata.st_dev, l2_metadata.st_ino)
        os.link(canonical_stripe, held_l2)
        assert canonical_stripe.samefile(held_l2)

        second_thread = threading.Thread(target=acquire_second_guard)
        second_thread.start()
        assert second_entered.wait(timeout=2)
        assert not second_acquired.wait(timeout=0.2)

        l1_metadata = held_l1.stat()
        os.replace(held_l1, canonical_stripe)
        assert (canonical_stripe.stat().st_dev, canonical_stripe.stat().st_ino) == (
            l1_metadata.st_dev,
            l1_metadata.st_ino,
        )
        first_storage.remove_if_created(first)
        assert first._released
        assert not canonical_object.exists()

        os.replace(held_l2, canonical_stripe)
        assert (canonical_stripe.stat().st_dev, canonical_stripe.stat().st_ino) == (
            l2_metadata.st_dev,
            l2_metadata.st_ino,
        )
        assert not canonical_object.exists()
        first_guard.release()
        assert second_acquired.wait(timeout=5)

        with pytest.raises(StoredDocumentReadError, match="STORED_DOCUMENT_UNAVAILABLE"):
            second_storage.read_owned_verified(second)
        with p3_engine_storage.session_factory() as session:
            assert (
                list(session.scalars(select(Document).where(Document.checksum_sha256 == digest)))
                == []
            )

        second_storage.abandon(second)
        assert second._released
        assert (
            second._root_fd,
            second._root_parent_fd,
            second._bucket_fd,
            second._locks_fd,
            second._lock_fd,
        ) == (
            -1,
            -1,
            -1,
            -1,
            -1,
        )
        assert (
            first._root_fd,
            first._root_parent_fd,
            first._bucket_fd,
            first._locks_fd,
            first._lock_fd,
        ) == (
            -1,
            -1,
            -1,
            -1,
            -1,
        )
        second_allow_release.set()
        assert second_finished.wait(timeout=5)
        second_thread.join(timeout=1)
        assert not second_thread.is_alive()
        assert second_errors == []

        key_one, key_two = DigestOwnershipGuard.advisory_keys(digest)
        with p3_engine_storage.session_factory() as session:
            assert (
                session.execute(
                    text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' "
                        "AND classid::bigint = :key_one AND objid::bigint = :key_two"
                    ),
                    {"key_one": key_one & 0xFFFFFFFF, "key_two": key_two & 0xFFFFFFFF},
                ).scalar_one()
                == 0
            )

        assert not held_l1.exists()
        assert not held_l2.exists()
        assert not staged_l2.exists()
        with canonical_stripe.open("rb+") as handle:
            assert storage_module.fcntl is not None
            storage_module.fcntl.flock(
                handle.fileno(), storage_module.fcntl.LOCK_EX | storage_module.fcntl.LOCK_NB
            )
            storage_module.fcntl.flock(handle.fileno(), storage_module.fcntl.LOCK_UN)

        probe_session = p3_engine_storage.session_factory()
        try:
            probe = DigestOwnershipGuard(
                probe_session, digest, p3_engine_storage.document_lock_engine
            )
            probe.acquire()
            probe.release()
        finally:
            probe_session.close()
    finally:
        if second is not None and not second._released:
            second_storage.abandon(second)
        if not first._released:
            first_storage.abandon(first)
        first_guard.release()
        second_allow_release.set()
        if second_thread is not None:
            second_thread.join(timeout=5)
        first_session.close()


def test_postgres_digest_guards_do_not_consume_application_queuepool_capacity(p3) -> None:
    """Two advisory guards leave a two-slot application pool free for DB work."""

    application_engine = create_engine(
        p3.database_url,
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.2,
        pool_pre_ping=True,
    )
    lock_engine = create_engine(p3.database_url, poolclass=NullPool, pool_pre_ping=True)
    assert isinstance(application_engine.pool, QueuePool)
    assert isinstance(lock_engine.pool, NullPool)
    assert lock_engine.pool is not application_engine.pool
    session_factory = sessionmaker(application_engine, expire_on_commit=False)
    first_digest = hashlib.sha256(b"capacity barrier first").hexdigest()
    second_digest = _different_stripe_digest(first_digest)
    guards_ready = threading.Barrier(3)
    run_queries = threading.Event()
    errors: list[BaseException] = []

    def acquire_then_query(digest: str) -> None:
        session: Session = session_factory()
        guard = DigestOwnershipGuard(session, digest, lock_engine)
        try:
            guard.acquire()
            guards_ready.wait(timeout=2)
            assert run_queries.wait(timeout=2)
            assert session.execute(text("SELECT 1")).scalar_one() == 1
        except BaseException as error:
            errors.append(error)
        finally:
            guard.release()
            session.close()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(acquire_then_query, first_digest)
            second = executor.submit(acquire_then_query, second_digest)
            guards_ready.wait(timeout=2)
            # The guards acquired their PostgreSQL connections already. They
            # must not have borrowed either application QueuePool slot.
            assert application_engine.pool.checkedout() == 0
            run_queries.set()
            first.result(timeout=3)
            second.result(timeout=3)

        assert errors == []
        assert application_engine.pool.checkedout() == 0
        first_key_one, first_key_two = DigestOwnershipGuard.advisory_keys(first_digest)
        second_key_one, second_key_two = DigestOwnershipGuard.advisory_keys(second_digest)
        with application_engine.connect() as inspector:
            assert (
                inspector.execute(
                    text(
                        "SELECT count(*) FROM pg_locks "
                        "WHERE locktype = 'advisory' AND granted AND ("
                        "(classid::bigint = :first_key_one AND objid::bigint = :first_key_two) OR "
                        "(classid::bigint = :second_key_one AND objid::bigint = :second_key_two))"
                    ),
                    {
                        "first_key_one": first_key_one & 0xFFFFFFFF,
                        "first_key_two": first_key_two & 0xFFFFFFFF,
                        "second_key_one": second_key_one & 0xFFFFFFFF,
                        "second_key_two": second_key_two & 0xFFFFFFFF,
                    },
                ).scalar_one()
                == 0
            )
        assert application_engine.pool.checkedout() == 0
    finally:
        lock_engine.dispose()
        application_engine.dispose()


def test_upload_route_passes_the_app_lock_engine_to_the_guard(p3, monkeypatch) -> None:
    """The HTTP path must never let the guard select the app QueuePool itself."""

    original_guard = documents_module.DigestOwnershipGuard
    seen_lock_engines = []

    class RecordingGuard(original_guard):
        def __init__(self, session, digest, lock_engine=None) -> None:
            seen_lock_engines.append(lock_engine)
            super().__init__(session, digest, lock_engine)

    monkeypatch.setattr(documents_module, "DigestOwnershipGuard", RecordingGuard)
    marker = uuid4().hex
    response = p3.client.post(
        "/api/v1/documents",
        content=f"P3 SYNTHETIC lock wiring {marker}".encode(),
        headers=p3.inspector
        | {"X-Filename": f"lock-wiring-{marker}.txt", "Content-Type": "text/plain"},
    )
    assert response.status_code == 201, response.text
    assert seen_lock_engines == [p3.client.app.state.document_lock_engine]
