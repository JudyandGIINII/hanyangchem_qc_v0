from __future__ import annotations

import asyncio
import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import hyc_api.storage as storage_module
from hyc_api.config import Settings
from hyc_api.main import create_app
from hyc_api.routes.documents import _classify_document_bytes
from hyc_api.storage import HashAddressedStorage, StoredDocumentReadError, StoredObject
from hyc_local_ocr.contracts import LocalOcrLimits
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pdf_backend import PyMuPdfDocumentBackend


async def _single_chunk(body: bytes):
    yield body


def _stored(root: Path, body: bytes) -> tuple[HashAddressedStorage, StoredObject]:
    storage = HashAddressedStorage(str(root))
    stored = asyncio.run(storage.put_stream(_single_chunk(body)))
    return storage, stored


def _assert_lease_released(stored: StoredObject) -> None:
    assert stored._released is True
    for attribute in ("_root_fd", "_root_parent_fd", "_bucket_fd", "_locks_fd", "_lock_fd"):
        descriptor = getattr(stored, attribute)
        assert descriptor == -1
        with pytest.raises(OSError):
            os.fstat(descriptor)


def test_verified_storage_read_success_and_identity_failures(tmp_path: Path) -> None:
    body = b"generated storage fixture"
    storage, stored = _stored(tmp_path, body)
    digest, key = stored.digest, stored.storage_key

    assert (
        storage.read_verified(checksum_sha256=digest, storage_key=key, expected_size=len(body))
        == body
    )

    cases = [
        ("not-a-digest", key, len(body), "STORED_DOCUMENT_IDENTITY_INVALID"),
        (digest, f"sha256/{digest[:2]}/../{digest}", len(body), "STORED_DOCUMENT_KEY_MISMATCH"),
        (digest, f"sha256/00/{digest}", len(body), "STORED_DOCUMENT_KEY_MISMATCH"),
        (digest, key, None, "STORED_DOCUMENT_SIZE_INVALID"),
        (digest, key, len(body) + 1, "STORED_DOCUMENT_SIZE_MISMATCH"),
        (digest, key, 10 * 1024 * 1024 + 1, "STORED_DOCUMENT_TOO_LARGE"),
    ]
    for checksum, storage_key, size, code in cases:
        with pytest.raises(StoredDocumentReadError, match=code):
            storage.read_verified(
                checksum_sha256=checksum,
                storage_key=storage_key,
                expected_size=size,
            )
    storage.finalize(stored)


def test_byte_classification_is_bounded_and_fixture_opt_in_only() -> None:
    assert (
        _classify_document_bytes(
            b"generated leading bytes\x00%PDF-generated", p3_fixture_mode=False
        )
        is None
    )
    assert _classify_document_bytes(b"P3 generated fixture", p3_fixture_mode=True) == (
        "SYNTHETIC_COA",
        "application/octet-stream",
    )
    assert _classify_document_bytes(b"P3 generated fixture", p3_fixture_mode=False) is None
    assert _classify_document_bytes(b"\x89PNG\r\n\x1a\n", p3_fixture_mode=True) is None


def test_nonzero_pdf_marker_matches_real_pdf_backend_guard() -> None:
    body = b"prefix that is not a PDF\x00%PDF-1.7"
    assert _classify_document_bytes(body, p3_fixture_mode=False) is None
    with pytest.raises(LocalOcrError, match="LOCAL_OCR_UNSUPPORTED_MEDIA_TYPE"):
        PyMuPdfDocumentBackend().load(body, LocalOcrLimits())


def test_verified_storage_rejects_same_size_digest_tamper(tmp_path: Path) -> None:
    body = b"generated-payload"
    storage, stored = _stored(tmp_path, body)
    digest, key = stored.digest, stored.storage_key
    target = tmp_path / digest[:2] / digest
    target.write_bytes(b"tampered-payload!")
    assert target.stat().st_size == len(body)

    with pytest.raises(StoredDocumentReadError, match="STORED_DOCUMENT_DIGEST_MISMATCH"):
        storage.read_verified(checksum_sha256=digest, storage_key=key, expected_size=len(body))
    storage.abandon(stored)


def test_verified_storage_rejects_bucket_directory_symlink_escape(tmp_path: Path) -> None:
    body = b"generated bucket symlink fixture"
    storage, stored = _stored(tmp_path, body)
    digest, key = stored.digest, stored.storage_key
    bucket = tmp_path / digest[:2]
    for child in bucket.iterdir():
        child.unlink()
    bucket.rmdir()
    outside = tmp_path / "outside-bucket"
    outside.mkdir()
    (outside / digest).write_bytes(body)
    bucket.symlink_to(outside, target_is_directory=True)

    with pytest.raises(StoredDocumentReadError, match="STORED_DOCUMENT_OUTSIDE_ROOT"):
        storage.read_verified(checksum_sha256=digest, storage_key=key, expected_size=len(body))
    storage.abandon(stored)


def test_storage_write_rejects_symlink_bucket_without_outside_hard_link(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    outside = tmp_path / "outside"
    outside.mkdir()
    body = b"generated symlink bucket write fixture"
    digest = hashlib.sha256(body).hexdigest()
    root.mkdir()
    (root / digest[:2]).symlink_to(outside, target_is_directory=True)

    with pytest.raises(OSError):
        asyncio.run(HashAddressedStorage(str(root)).put_stream(_single_chunk(body)))
    assert not (outside / digest).exists()


def test_created_upload_cleanup_removes_object_and_empty_bucket(tmp_path: Path) -> None:
    body = b"generated rejected upload cleanup fixture"
    storage, stored = _stored(tmp_path, body)
    digest = stored.digest
    storage.remove_if_created(stored)
    assert not (tmp_path / digest[:2] / digest).exists()
    assert not (tmp_path / digest[:2]).exists()


def test_abandon_releases_each_retained_lease_descriptor_once(tmp_path: Path) -> None:
    storage, stored = _stored(tmp_path, b"generated abandoned lease fixture")

    storage.abandon(stored)
    storage.abandon(stored)

    _assert_lease_released(stored)


def test_cleanup_refuses_after_root_replacement(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    body = b"generated retained-root cleanup fixture"
    storage, stored = _stored(root, body)
    original_root = tmp_path / "storage-original"
    root.rename(original_root)
    root.mkdir()
    victim_bucket = root / stored.digest[:2]
    victim_bucket.mkdir()
    victim = victim_bucket / stored.digest
    victim.write_bytes(b"attacker-chosen replacement victim")

    with pytest.raises(OSError, match="canonical storage namespace ownership changed"):
        storage.assert_canonical_namespace_owned(stored)
    with pytest.raises(OSError, match="storage directory was swapped"):
        storage.remove_if_created(stored)

    assert victim.exists()
    assert (original_root / stored.digest[:2] / stored.digest).exists()
    _assert_lease_released(stored)


def test_cleanup_uses_retained_bucket_descriptor_after_bucket_replacement(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    body = b"generated retained-bucket cleanup fixture"
    storage, stored = _stored(root, body)
    prefix = stored.digest[:2]
    original_bucket = root / f"{prefix}-original"
    (root / prefix).rename(original_bucket)
    replacement_bucket = root / prefix
    replacement_bucket.mkdir()
    victim = replacement_bucket / stored.digest
    victim.write_bytes(b"attacker-chosen replacement victim")

    with pytest.raises(StoredDocumentReadError, match="STORED_DOCUMENT_UNAVAILABLE"):
        storage.read_owned_verified(stored)
    storage.remove_if_created(stored)

    assert victim.exists()
    assert not (original_bucket / stored.digest).exists()


def test_storage_root_swap_and_remove_cannot_escape(tmp_path: Path) -> None:
    root = tmp_path / "storage"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        asyncio.run(HashAddressedStorage(str(root)).put_stream(_single_chunk(b"P3 root swap")))
    assert list(outside.iterdir()) == []

    root.unlink()
    body = b"generated remove symlink fixture"
    storage, stored = _stored(root, body)
    digest = stored.digest
    bucket = root / digest[:2]
    target = bucket / digest
    target.unlink()
    bucket.rmdir()
    (outside / digest).write_bytes(body)
    bucket.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        storage.remove_if_created(stored)
    assert (outside / digest).read_bytes() == body


def test_storage_rejects_root_and_bucket_swaps_after_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "storage"
    root.mkdir()
    storage = HashAddressedStorage(str(root))
    original_open_bucket = storage._open_bucket

    def swap_root(root_fd: int, prefix: str) -> tuple[int, bool]:
        result = original_open_bucket(root_fd, prefix)
        root.rename(tmp_path / "storage-moved")
        root.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(storage, "_open_bucket", swap_root)
    with pytest.raises(OSError, match="swapped"):
        asyncio.run(storage.put_stream(_single_chunk(b"P3 root swap after open")))
    assert list(outside.iterdir()) == []

    root = tmp_path / "second-storage"
    root.mkdir()
    storage = HashAddressedStorage(str(root))
    original_open_bucket = storage._open_bucket

    def swap_bucket(root_fd: int, prefix: str) -> tuple[int, bool]:
        result = original_open_bucket(root_fd, prefix)
        bucket = root / prefix
        bucket.rename(root / f"{prefix}-moved")
        bucket.symlink_to(outside, target_is_directory=True)
        return result

    monkeypatch.setattr(storage, "_open_bucket", swap_bucket)
    with pytest.raises(OSError, match="swapped"):
        asyncio.run(storage.put_stream(_single_chunk(b"P3 bucket swap after open")))
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("replacement", ["symlink", "directory", "fifo"])
def test_verified_storage_rejects_non_regular_or_link_targets(
    tmp_path: Path, replacement: str
) -> None:
    body = b"generated non-regular fixture"
    storage, stored = _stored(tmp_path, body)
    digest, key = stored.digest, stored.storage_key
    target = tmp_path / digest[:2] / digest
    target.unlink()
    if replacement == "symlink":
        outside = tmp_path / "outside.bin"
        outside.write_bytes(body)
        target.symlink_to(outside)
    elif replacement == "directory":
        target.mkdir()
    else:
        os.mkfifo(target)

    expected = (
        "STORED_DOCUMENT_UNAVAILABLE" if replacement == "symlink" else "STORED_DOCUMENT_NOT_REGULAR"
    )
    with pytest.raises(StoredDocumentReadError, match=expected):
        storage.read_verified(checksum_sha256=digest, storage_key=key, expected_size=len(body))
    storage.abandon(stored)


def test_same_digest_waiter_keeps_temp_until_first_lease_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second writer reaches flock only after staging and blocks on the live lease."""

    if storage_module.fcntl is None:
        pytest.skip("filesystem locking is unavailable")
    root = tmp_path / "storage"
    body = b"generated deterministic digest lock race"
    first_storage, first = _stored(root, body)
    second_storage = HashAddressedStorage(str(root))
    lock_boundary = threading.Event()
    second_completed = threading.Event()
    original_flock = storage_module.fcntl.flock

    def observe_second_lock(descriptor: int, operation: int) -> None:
        if operation == storage_module.fcntl.LOCK_EX:
            lock_boundary.set()
        original_flock(descriptor, operation)

    monkeypatch.setattr(storage_module.fcntl, "flock", observe_second_lock)

    def put_second() -> StoredObject:
        try:
            return asyncio.run(second_storage.put_stream(_single_chunk(body)))
        finally:
            second_completed.set()

    with ThreadPoolExecutor(max_workers=1) as executor:
        second_future = executor.submit(put_second)
        assert lock_boundary.wait(timeout=5)
        assert list(root.glob(".p3-upload-*"))
        assert not second_completed.is_set()
        first_storage.remove_if_created(first)
        second = second_future.result(timeout=5)

    assert second.created is True
    assert second_storage.read_owned_verified(second) == body
    second_storage.finalize(second)
    assert second_storage.read_verified(
        checksum_sha256=second.digest,
        storage_key=second.storage_key,
        expected_size=len(body),
    ) == body


@pytest.mark.parametrize("replace_locks_directory", [False, True])
def test_split_stripe_cleanup_refuses_deletion_and_releases_all_lease_fds(
    tmp_path: Path, replace_locks_directory: bool
) -> None:
    """A replacement lock inode cannot split an old creator from a new writer."""

    if storage_module.fcntl is None:
        pytest.skip("filesystem locking is unavailable")
    root = tmp_path / "storage"
    body = b"generated split striped-lock cleanup fixture"
    first_storage, first = _stored(root, body)
    stripe = first._stripe_name
    assert stripe is not None
    locks = root / ".locks"
    if replace_locks_directory:
        locks.rename(root / ".locks-detached")
        locks.mkdir()
    else:
        (locks / stripe).unlink()
    replacement_stripe = locks / stripe
    replacement_stripe.touch(exist_ok=True)

    second_storage, second = _stored(root, body)
    assert second.created is False
    assert second._stripe_name == stripe

    with pytest.raises(OSError, match="storage (lock directory|lock stripe) identity changed"):
        first_storage.remove_if_created(first)

    target = root / first.digest[:2] / first.digest
    assert target.read_bytes() == body
    _assert_lease_released(first)
    second_storage.prepare_successful_finalization(second)
    second_storage.finalize(second)
    _assert_lease_released(second)
    assert HashAddressedStorage(str(root)).read_verified(
        checksum_sha256=first.digest,
        storage_key=first.storage_key,
        expected_size=len(body),
    ) == body


def test_finalize_releases_lease_when_lock_namespace_verification_fails(tmp_path: Path) -> None:
    if storage_module.fcntl is None:
        pytest.skip("filesystem locking is unavailable")
    root = tmp_path / "storage"
    body = b"generated finalize failure lock release fixture"
    storage, stored = _stored(root, body)
    stripe = stored._stripe_name
    assert stripe is not None
    stripe_path = root / ".locks" / stripe
    stripe_path.unlink()
    stripe_path.touch()

    with pytest.raises(OSError, match="canonical storage namespace ownership changed"):
        storage.finalize(stored)
    _assert_lease_released(stored)

    second_storage, second = _stored(root, body)
    second_storage.finalize(second)
    _assert_lease_released(second)


def test_digest_locks_use_a_bounded_striped_namespace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "storage"
    storage = HashAddressedStorage(str(root))
    descriptors_before = len(os.listdir("/dev/fd"))

    def fail_after_lock(root_fd: int, prefix: str) -> tuple[int, bool]:
        del root_fd, prefix
        raise OSError("injected post-lock failure")

    monkeypatch.setattr(storage, "_open_bucket", fail_after_lock)
    digests: set[str] = set()
    for index in range(HashAddressedStorage._LOCK_STRIPE_COUNT * 2):
        body = f"generated unique failed digest {index}".encode()
        digest = hashlib.sha256(body).hexdigest()
        digests.add(digest)
        with pytest.raises(OSError, match="injected post-lock failure"):
            asyncio.run(storage.put_stream(_single_chunk(body)))

    assert len(digests) == HashAddressedStorage._LOCK_STRIPE_COUNT * 2
    lock_entries = list((root / ".locks").iterdir())
    assert len(lock_entries) <= HashAddressedStorage._LOCK_STRIPE_COUNT
    assert all(entry.is_file() and len(entry.name) == 2 for entry in lock_entries)
    sample_digest = next(iter(digests))
    assert HashAddressedStorage._lock_name(sample_digest) == HashAddressedStorage._lock_name(
        sample_digest
    )
    stripes = {HashAddressedStorage._lock_name(digest) for digest in digests}
    assert len(stripes) < len(digests)
    assert len(os.listdir("/dev/fd")) == descriptors_before


def test_fixture_mode_does_not_construct_optional_local_ocr_provider() -> None:
    def should_not_run(_: Settings):
        raise AssertionError("fixture mode must not initialize local OCR")

    app = create_app(Settings(local_ocr_enabled=False), local_ocr_provider_factory=should_not_run)
    assert app.state.local_ocr_provider is None


def test_explicit_local_flag_constructs_injected_provider_once() -> None:
    provider = object()
    calls: list[Settings] = []

    def factory(settings: Settings):
        calls.append(settings)
        return provider  # type: ignore[return-value]

    app = create_app(Settings(local_ocr_enabled=True), local_ocr_provider_factory=factory)
    assert app.state.local_ocr_provider is provider
    assert len(calls) == 1
