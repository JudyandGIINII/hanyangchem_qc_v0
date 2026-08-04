from __future__ import annotations

import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

import hyc_api.storage as storage_module
from hyc_api.dependencies import database_session
from hyc_api.storage import HashAddressedStorage
from hyc_data.models import Document

pytestmark = pytest.mark.postgres


def test_document_sequential_and_concurrent_deduplication(p3) -> None:
    body = f"P3 SYNTHETIC DEDUPE {uuid4()}".encode()
    headers = p3.inspector | {"X-Filename": "synthetic.txt", "Content-Type": "text/plain"}
    first = p3.client.post("/api/v1/documents", content=body, headers=headers)
    second = p3.client.post("/api/v1/documents", content=body, headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert first.json()["document_id"] == second.json()["document_id"]

    concurrent_body = f"P3 SYNTHETIC CONCURRENT {uuid4()}".encode()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(
            executor.map(
                lambda _: p3.client.post(
                    "/api/v1/documents", content=concurrent_body, headers=headers
                ),
                range(2),
            )
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["document_id"] for response in responses}) == 1


@pytest.mark.parametrize(
    ("body", "expected_status", "expected_message"),
    [
        (b"", 422, "Document body is empty"),
        (b"x" * (10 * 1024 * 1024 + 1), 413, "Document body exceeds 10 MiB"),
    ],
    ids=["empty", "over-limit"],
)
def test_document_upload_rejects_invalid_sizes_without_storage_residue(
    p3, body: bytes, expected_status: int, expected_message: str
) -> None:
    settings = p3.client.app.state.settings
    configured_root = Path(settings.p3_storage_root)
    invalid_root = configured_root / f"invalid-upload-{uuid4().hex}"
    settings.p3_storage_root = str(invalid_root)
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=body,
            headers=p3.inspector
            | {"X-Filename": "invalid-size.txt", "Content-Type": "text/plain"},
        )
    finally:
        settings.p3_storage_root = str(configured_root)

    assert response.status_code == expected_status
    assert response.json() == {
        "schema_version": "1.0",
        "code": "HTTP_ERROR",
        "message": expected_message,
        "correlation_id": response.headers["X-Correlation-ID"],
    }
    assert str(invalid_root) not in response.text
    assert "p3-upload-" not in response.text
    assert not invalid_root.exists()


def test_document_upload_rejects_long_filename_before_storage_write(p3) -> None:
    settings = p3.client.app.state.settings
    configured_root = Path(settings.p3_storage_root)
    untouched_root = configured_root / f"long-filename-{uuid4().hex}"
    settings.p3_storage_root = str(untouched_root)
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=b"P3 fixture that must not be written",
            headers=p3.inspector | {"X-Filename": "x" * 513},
        )
    finally:
        settings.p3_storage_root = str(configured_root)
    assert response.status_code == 422
    assert response.json()["message"] == "X-Filename exceeds 512 characters"
    assert not untouched_root.exists()


def test_document_db_failure_after_storage_write_removes_orphan(p3) -> None:
    body = f"P3 injected write failure {uuid4().hex}".encode()
    digest = hashlib.sha256(body).hexdigest()
    root = Path(p3.client.app.state.settings.p3_storage_root)

    def fail_document_insert(connection, cursor, statement, parameters, context, executemany):
        del connection, cursor, parameters, context, executemany
        if "INSERT INTO documents" in statement:
            raise RuntimeError("injected document insert failure")

    engine = p3.client.app.state.engine
    event.listen(engine, "before_cursor_execute", fail_document_insert)
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=body,
            headers=p3.inspector | {"X-Filename": "injected-failure.txt"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", fail_document_insert)
    assert response.status_code == 500
    bucket = root / digest[:2]
    assert not (bucket / digest).exists()
    if bucket.exists():
        # The PostgreSQL suite shares its storage root, so a different document
        # can legitimately occupy the same two-hex-character digest bucket.
        assert all(
            entry.name != digest and not entry.name.startswith(".p3-upload-")
            for entry in bucket.iterdir()
        )


def test_detached_bucket_before_commit_rolls_back_and_preserves_replacement_victim(p3) -> None:
    """A flush-time namespace swap cannot commit a row for retained-only bytes."""

    body = f"P3 SYNTHETIC DETACHED BUCKET {uuid4().hex}".encode()
    digest = hashlib.sha256(body).hexdigest()
    root = Path(p3.client.app.state.settings.p3_storage_root)
    prefix = digest[:2]
    original_bucket = root / prefix
    detached_bucket = root / f"{prefix}-detached-{uuid4().hex}"
    replacement_victim = root / prefix / digest
    swap_complete = threading.Event()

    def detach_at_flush(connection, cursor, statement, parameters, context, executemany):
        del connection, cursor, parameters, context, executemany
        if "INSERT INTO documents" not in statement or swap_complete.is_set():
            return
        original_bucket.rename(detached_bucket)
        replacement_victim.parent.mkdir()
        replacement_victim.write_bytes(b"attacker-chosen replacement victim")
        swap_complete.set()

    engine = p3.client.app.state.engine
    event.listen(engine, "before_cursor_execute", detach_at_flush)
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=body,
            headers=p3.inspector | {"X-Filename": "detached-before-commit.txt"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", detach_at_flush)

    assert swap_complete.is_set()
    assert 400 <= response.status_code < 600
    assert response.status_code != 201
    assert replacement_victim.read_bytes() == b"attacker-chosen replacement victim"
    assert not (detached_bucket / digest).exists()
    with Session(engine) as session:
        assert session.scalar(select(Document.id).where(Document.checksum_sha256 == digest)) is None


def test_failed_creator_releases_digest_lease_before_second_uploader_commits(
    p3, monkeypatch
) -> None:
    """A failed creator cannot delete bytes selected by a waiting duplicate."""

    body = f"P3 SYNTHETIC LEASE RACE {uuid4().hex}".encode()
    digest = hashlib.sha256(body).hexdigest()
    root = Path(p3.client.app.state.settings.p3_storage_root)
    headers = p3.inspector | {"X-Filename": "lease-race.txt", "Content-Type": "text/plain"}
    first_insert_entered = threading.Event()
    second_waiting_at_digest_lock = threading.Event()
    calls_lock = threading.Lock()
    lock_attempts = 0

    if storage_module.fcntl is None:
        pytest.skip("filesystem locking is unavailable")
    original_flock = storage_module.fcntl.flock

    def signal_second_lock(descriptor: int, operation: int) -> None:
        nonlocal lock_attempts
        if operation == storage_module.fcntl.LOCK_EX:
            with calls_lock:
                lock_attempts += 1
                if lock_attempts == 2:
                    second_waiting_at_digest_lock.set()
        original_flock(descriptor, operation)

    monkeypatch.setattr(storage_module.fcntl, "flock", signal_second_lock)

    def fail_first_insert(connection, cursor, statement, parameters, context, executemany):
        del connection, cursor, parameters, context, executemany
        if "INSERT INTO documents" in statement and not first_insert_entered.is_set():
            first_insert_entered.set()
            assert second_waiting_at_digest_lock.wait(timeout=5)
            assert list(root.glob(".p3-upload-*"))
            raise RuntimeError("injected first document insert failure")

    engine = p3.client.app.state.engine
    event.listen(engine, "before_cursor_execute", fail_first_insert)
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(
                p3.client.post, "/api/v1/documents", content=body, headers=headers
            )
            assert first_insert_entered.wait(timeout=5)
            second = executor.submit(
                p3.client.post, "/api/v1/documents", content=body, headers=headers
            )
            first_response = first.result(timeout=10)
            second_response = second.result(timeout=10)
    finally:
        event.remove(engine, "before_cursor_execute", fail_first_insert)

    assert first_response.status_code == 500
    assert second_response.status_code == 201
    with Session(engine) as session:
        documents = list(
            session.scalars(select(Document).where(Document.checksum_sha256 == digest))
        )
    assert len(documents) == 1
    document = documents[0]
    assert HashAddressedStorage(str(root)).read_verified(
        checksum_sha256=digest,
        storage_key=document.storage_key,
        expected_size=document.size_bytes,
    ) == body


def test_precommit_failure_cleans_owned_bytes_when_rollback_raises(p3) -> None:
    """Best-effort rollback must not gate pre-commit owned-object cleanup."""

    body = f"P3 SYNTHETIC ROLLBACK FAILURE {uuid4().hex}".encode()
    digest = hashlib.sha256(body).hexdigest()
    root = Path(p3.client.app.state.settings.p3_storage_root)
    engine = p3.client.app.state.engine

    class FailingRollbackSession:
        def __init__(self, session: Session) -> None:
            self._session = session

        def rollback(self) -> None:
            raise RuntimeError("injected rollback failure")

        def __getattr__(self, name: str):
            return getattr(self._session, name)

    def failing_rollback_session():
        session = p3.client.app.state.session_factory()
        try:
            yield FailingRollbackSession(session)
        finally:
            session.close()

    def fail_initial_lookup(connection, cursor, statement, parameters, context, executemany):
        del connection, cursor, parameters, context, executemany
        if "FROM documents" in statement:
            raise RuntimeError("injected document lookup failure")

    event.listen(engine, "before_cursor_execute", fail_initial_lookup)
    p3.client.app.dependency_overrides[database_session] = failing_rollback_session
    try:
        response = p3.client.post(
            "/api/v1/documents",
            content=body,
            headers=p3.inspector | {"X-Filename": "rollback-failure.txt"},
        )
    finally:
        event.remove(engine, "before_cursor_execute", fail_initial_lookup)
        p3.client.app.dependency_overrides.pop(database_session, None)

    assert response.status_code == 500
    assert not (root / digest[:2] / digest).exists()
