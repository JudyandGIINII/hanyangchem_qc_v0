from __future__ import annotations

import hashlib
import os
import re
import secrets
import stat
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

try:
    import fcntl
except ImportError:  # pragma: no cover - supported deployments are POSIX only.
    fcntl = None  # type: ignore[assignment]


class EmptyUploadError(Exception):
    """The streamed upload contained no bytes."""


class UploadTooLargeError(Exception):
    """The streamed upload exceeded the fixture limit."""


class StoredDocumentReadError(Exception):
    """A DB-owned immutable document failed bounded identity verification."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ImmutableSourceStorage(Protocol):
    """Future P6 storage seam; P1 deliberately supplies no source-data adapter."""

    def put_immutable(self, digest: str, content: bytes, media_type: str) -> str: ...

    def open_verified(self, digest: str) -> bytes: ...


@dataclass(slots=True)
class StoredObject:
    """A request-local digest lease; descriptor fields must never be persisted."""

    digest: str
    storage_key: str
    size_bytes: int
    created: bool
    _root_fd: int = field(default=-1, repr=False, compare=False)
    _root_parent_fd: int = field(default=-1, repr=False, compare=False)
    _bucket_fd: int = field(default=-1, repr=False, compare=False)
    _locks_fd: int = field(default=-1, repr=False, compare=False)
    _lock_fd: int = field(default=-1, repr=False, compare=False)
    _root_created: bool = field(default=False, repr=False, compare=False)
    _bucket_created: bool = field(default=False, repr=False, compare=False)
    _object_dev: int | None = field(default=None, repr=False, compare=False)
    _object_ino: int | None = field(default=None, repr=False, compare=False)
    _locks_dev: int | None = field(default=None, repr=False, compare=False)
    _locks_ino: int | None = field(default=None, repr=False, compare=False)
    _stripe_name: str | None = field(default=None, repr=False, compare=False)
    _lock_dev: int | None = field(default=None, repr=False, compare=False)
    _lock_ino: int | None = field(default=None, repr=False, compare=False)
    _finalization_verified: bool = field(default=False, repr=False, compare=False)
    _released: bool = field(default=False, repr=False, compare=False)


class HashAddressedStorage:
    """Fail-closed dir-fd storage with a per-digest lease across DB ownership."""

    _MAX_SIZE = 10 * 1024 * 1024
    _LOCKS_DIRECTORY = ".locks"
    _LOCK_STRIPE_COUNT = 256

    def __init__(self, root: str) -> None:
        self.root = Path(root)

    @staticmethod
    def _directory_flags() -> int:
        directory = getattr(os, "O_DIRECTORY", None)
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if directory is None or nofollow is None:
            raise OSError("secure directory descriptor flags are unavailable")
        return os.O_RDONLY | int(directory) | int(nofollow)

    @staticmethod
    def _file_create_flags() -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise OSError("secure no-follow flag is unavailable")
        return os.O_WRONLY | os.O_CREAT | os.O_EXCL | int(nofollow)

    @staticmethod
    def _file_read_flags() -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise OSError("secure no-follow flag is unavailable")
        return os.O_RDONLY | os.O_NONBLOCK | int(nofollow)

    @staticmethod
    def _lock_create_flags() -> int:
        nofollow = getattr(os, "O_NOFOLLOW", None)
        if nofollow is None:
            raise OSError("secure no-follow flag is unavailable")
        return os.O_RDWR | os.O_CREAT | int(nofollow)

    def _open_root(self, *, create: bool) -> tuple[int, int, bool]:
        created = False
        if create:
            self.root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        parent_fd = os.open(self.root.parent, self._directory_flags())
        try:
            if create:
                try:
                    os.mkdir(self.root.name, mode=0o700, dir_fd=parent_fd)
                    created = True
                    self._fsync(parent_fd)
                except FileExistsError:
                    pass
            root_fd = os.open(self.root.name, self._directory_flags(), dir_fd=parent_fd)
            if not stat.S_ISDIR(os.fstat(root_fd).st_mode):
                raise OSError("configured storage root is not a directory")
        except Exception:
            if "root_fd" in locals():
                os.close(root_fd)
            os.close(parent_fd)
            raise
        return root_fd, parent_fd, created

    @staticmethod
    def _assert_current_directory(parent_fd: int, name: str, directory_fd: int) -> None:
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(directory_fd)
        if (
            not stat.S_ISDIR(current.st_mode)
            or current.st_dev != opened.st_dev
            or current.st_ino != opened.st_ino
        ):
            raise OSError("storage directory was swapped")

    @staticmethod
    def _fsync(descriptor: int) -> None:
        os.fsync(descriptor)

    def _open_bucket(self, root_fd: int, prefix: str) -> tuple[int, bool]:
        created = False
        try:
            os.mkdir(prefix, mode=0o700, dir_fd=root_fd)
            created = True
            self._fsync(root_fd)
        except FileExistsError:
            pass
        bucket_fd = os.open(prefix, self._directory_flags(), dir_fd=root_fd)
        try:
            if not stat.S_ISDIR(os.fstat(bucket_fd).st_mode):
                raise OSError("storage bucket is not a directory")
            self._assert_current_directory(root_fd, prefix, bucket_fd)
        except Exception:
            os.close(bucket_fd)
            raise
        return bucket_fd, created

    def _open_locks(self, root_fd: int) -> int:
        try:
            os.mkdir(self._LOCKS_DIRECTORY, mode=0o700, dir_fd=root_fd)
            self._fsync(root_fd)
        except FileExistsError:
            pass
        locks_fd = os.open(self._LOCKS_DIRECTORY, self._directory_flags(), dir_fd=root_fd)
        try:
            if not stat.S_ISDIR(os.fstat(locks_fd).st_mode):
                raise OSError("storage lock directory is not a directory")
            self._assert_current_directory(root_fd, self._LOCKS_DIRECTORY, locks_fd)
        except Exception:
            os.close(locks_fd)
            raise
        return locks_fd

    def _acquire_digest_lock(
        self, root_fd: int, digest: str
    ) -> tuple[int, int, str, int, int, int, int]:
        if fcntl is None:
            raise OSError("filesystem locking is unavailable")
        locks_fd = self._open_locks(root_fd)
        lock_fd = -1
        try:
            lock_name = self._lock_name(digest)
            lock_fd = os.open(lock_name, self._lock_create_flags(), 0o600, dir_fd=locks_fd)
            lock_metadata = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_metadata.st_mode):
                raise OSError("storage lock is not a regular file")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            self._assert_current_directory(root_fd, self._LOCKS_DIRECTORY, locks_fd)
            current = os.stat(lock_name, dir_fd=locks_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(current.st_mode)
                or current.st_dev != lock_metadata.st_dev
                or current.st_ino != lock_metadata.st_ino
            ):
                raise OSError("storage lock stripe identity changed")
            locks_metadata = os.fstat(locks_fd)
            return (
                locks_fd,
                lock_fd,
                lock_name,
                locks_metadata.st_dev,
                locks_metadata.st_ino,
                lock_metadata.st_dev,
                lock_metadata.st_ino,
            )
        except Exception:
            if lock_fd >= 0:
                os.close(lock_fd)
            os.close(locks_fd)
            raise

    @classmethod
    def _lock_name(cls, digest: str) -> str:
        """Map every digest to one of a fixed number of lock inodes."""

        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("lock digest is invalid")
        stripe = int(digest[:8], 16) % cls._LOCK_STRIPE_COUNT
        return f"{stripe:02x}"

    @staticmethod
    def _canonical_key(stored: StoredObject) -> tuple[str, str]:
        if not re.fullmatch(r"[0-9a-f]{64}", stored.digest):
            raise ValueError("stored digest is invalid")
        prefix = stored.digest[:2]
        canonical = f"sha256/{prefix}/{stored.digest}"
        if stored.storage_key != canonical:
            raise ValueError("stored key is not canonical")
        return prefix, stored.digest

    @staticmethod
    def _remove_empty_bucket_if_owned(root_fd: int, bucket_fd: int, prefix: str) -> None:
        try:
            HashAddressedStorage._assert_current_directory(root_fd, prefix, bucket_fd)
            os.rmdir(prefix, dir_fd=root_fd)
            os.fsync(root_fd)
        except OSError:
            return

    def _remove_empty_root_if_owned(self, stored: StoredObject) -> None:
        if not stored._root_created:
            return
        try:
            self._assert_current_directory(stored._root_parent_fd, self.root.name, stored._root_fd)
            os.rmdir(self.root.name, dir_fd=stored._root_parent_fd)
            self._fsync(stored._root_parent_fd)
        except OSError:
            return

    @staticmethod
    def _close_quietly(descriptor: int) -> None:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _release(self, stored: StoredObject) -> None:
        if stored._released:
            return
        stored._released = True
        if stored._lock_fd >= 0 and fcntl is not None:
            try:
                fcntl.flock(stored._lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        self._close_quietly(stored._lock_fd)
        self._close_quietly(stored._locks_fd)
        self._close_quietly(stored._bucket_fd)
        self._close_quietly(stored._root_fd)
        self._close_quietly(stored._root_parent_fd)
        stored._lock_fd = -1
        stored._locks_fd = -1
        stored._bucket_fd = -1
        stored._root_fd = -1
        stored._root_parent_fd = -1

    @staticmethod
    def _require_live_lease(stored: StoredObject) -> None:
        if (
            stored._released
            or stored._root_fd < 0
            or stored._root_parent_fd < 0
            or stored._bucket_fd < 0
            or stored._locks_fd < 0
            or stored._lock_fd < 0
        ):
            raise OSError("storage ownership lease is unavailable")
        if not stat.S_ISDIR(os.fstat(stored._root_fd).st_mode) or not stat.S_ISDIR(
            os.fstat(stored._bucket_fd).st_mode
        ):
            raise OSError("storage ownership descriptor is invalid")

    async def put_stream(self, chunks: AsyncIterable[bytes]) -> StoredObject:
        root_fd = root_parent_fd = bucket_fd = locks_fd = lock_fd = -1
        lock_name: str | None = None
        locks_dev = locks_ino = lock_dev = lock_ino = None
        temporary_name: str | None = None
        checksum: str | None = None
        root_created = bucket_created = created = False
        lease_returned = False
        try:
            root_fd, root_parent_fd, root_created = self._open_root(create=True)
            for _ in range(32):
                candidate = f".p3-upload-{secrets.token_hex(16)}"
                try:
                    temporary_fd = os.open(
                        candidate, self._file_create_flags(), 0o600, dir_fd=root_fd
                    )
                    temporary_name = candidate
                    break
                except FileExistsError:
                    continue
            else:
                raise OSError("could not allocate secure upload temporary file")

            digest = hashlib.sha256()
            size = 0
            with os.fdopen(temporary_fd, "wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > self._MAX_SIZE:
                        raise UploadTooLargeError
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                self._fsync(handle.fileno())
            if size == 0:
                raise EmptyUploadError

            checksum = digest.hexdigest()
            prefix = checksum[:2]
            self._assert_current_directory(root_parent_fd, self.root.name, root_fd)
            (
                locks_fd,
                lock_fd,
                lock_name,
                locks_dev,
                locks_ino,
                lock_dev,
                lock_ino,
            ) = self._acquire_digest_lock(root_fd, checksum)
            self._assert_current_directory(root_parent_fd, self.root.name, root_fd)
            # A waiter must not retain an older bucket descriptor while the
            # lease holder removes its empty bucket during failed-request
            # cleanup.  Open/create the digest bucket only after the lock.
            bucket_fd, bucket_created = self._open_bucket(root_fd, prefix)
            self._assert_current_directory(root_parent_fd, self.root.name, root_fd)
            self._assert_current_directory(root_fd, prefix, bucket_fd)
            try:
                os.link(
                    temporary_name,
                    checksum,
                    src_dir_fd=root_fd,
                    dst_dir_fd=bucket_fd,
                    follow_symlinks=False,
                )
                created = True
                self._fsync(bucket_fd)
            except FileExistsError:
                pass
            metadata = os.stat(checksum, dir_fd=bucket_fd, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise OSError("stored object is not regular")
            object_dev, object_ino = metadata.st_dev, metadata.st_ino
            os.unlink(temporary_name, dir_fd=root_fd)
            self._fsync(root_fd)
            temporary_name = None

            stored = StoredObject(
                digest=checksum,
                storage_key=f"sha256/{prefix}/{checksum}",
                size_bytes=size,
                created=created,
                _root_fd=root_fd,
                _root_parent_fd=root_parent_fd,
                _bucket_fd=bucket_fd,
                _locks_fd=locks_fd,
                _lock_fd=lock_fd,
                _root_created=root_created,
                _bucket_created=bucket_created,
                _object_dev=object_dev,
                _object_ino=object_ino,
                _locks_dev=locks_dev,
                _locks_ino=locks_ino,
                _stripe_name=lock_name,
                _lock_dev=lock_dev,
                _lock_ino=lock_ino,
            )
            root_fd = root_parent_fd = bucket_fd = locks_fd = lock_fd = -1
            lease_returned = True
            return stored
        finally:
            if temporary_name is not None and root_fd >= 0:
                try:
                    os.unlink(temporary_name, dir_fd=root_fd)
                except FileNotFoundError:
                    pass
            if created and not lease_returned and bucket_fd >= 0 and checksum is not None:
                try:
                    if (
                        lock_name is not None
                        and locks_dev is not None
                        and locks_ino is not None
                        and lock_dev is not None
                        and lock_ino is not None
                    ):
                        self._assert_lock_namespace_identity(
                            root_parent_fd=root_parent_fd,
                            root_fd=root_fd,
                            locks_fd=locks_fd,
                            lock_fd=lock_fd,
                            locks_dev=locks_dev,
                            locks_ino=locks_ino,
                            stripe_name=lock_name,
                            lock_dev=lock_dev,
                            lock_ino=lock_ino,
                        )
                        os.unlink(checksum, dir_fd=bucket_fd)
                        self._fsync(bucket_fd)
                except OSError:
                    pass
            if bucket_created and bucket_fd >= 0 and checksum is not None:
                self._remove_empty_bucket_if_owned(root_fd, bucket_fd, checksum[:2])
            if lock_fd >= 0 and fcntl is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except OSError:
                    pass
            self._close_quietly(lock_fd)
            self._close_quietly(locks_fd)
            self._close_quietly(bucket_fd)
            if root_created and root_fd >= 0 and root_parent_fd >= 0:
                try:
                    self._assert_current_directory(root_parent_fd, self.root.name, root_fd)
                    os.rmdir(self.root.name, dir_fd=root_parent_fd)
                    self._fsync(root_parent_fd)
                except OSError:
                    pass
            self._close_quietly(root_fd)
            self._close_quietly(root_parent_fd)

    def finalize(self, stored: StoredObject) -> None:
        """Release a successful request lease after canonical verification."""

        if stored._released:
            return
        try:
            if not stored._finalization_verified:
                self.assert_canonical_namespace_owned(stored)
        finally:
            self._release(stored)

    def prepare_successful_finalization(self, stored: StoredObject) -> None:
        """Assert canonical ownership at the final pre-commit boundary."""

        self.assert_canonical_namespace_owned(stored)
        stored._finalization_verified = True

    def abandon(self, stored: StoredObject) -> None:
        """Release a lease after a failed cleanup without claiming success."""

        self._release(stored)

    def remove_if_created(self, stored: StoredObject) -> None:
        """Unlink only the request-owned inode through retained descriptors."""

        try:
            if not stored.created:
                return
            prefix, digest = self._canonical_key(stored)
            self._require_live_lease(stored)
            self._assert_stored_lock_namespace_identity(stored)
            if stored._object_dev is None or stored._object_ino is None:
                raise OSError("created object ownership identity is unavailable")
            metadata = os.stat(digest, dir_fd=stored._bucket_fd, follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_dev != stored._object_dev
                or metadata.st_ino != stored._object_ino
            ):
                raise OSError("created object ownership identity changed")
            os.unlink(digest, dir_fd=stored._bucket_fd)
            self._fsync(stored._bucket_fd)
            self._remove_empty_bucket_if_owned(stored._root_fd, stored._bucket_fd, prefix)
            self._remove_empty_root_if_owned(stored)
        finally:
            self._release(stored)

    @staticmethod
    def _matches_descriptor(metadata: os.stat_result, descriptor: int) -> bool:
        opened = os.fstat(descriptor)
        return (
            stat.S_ISDIR(metadata.st_mode)
            and metadata.st_dev == opened.st_dev
            and metadata.st_ino == opened.st_ino
        )

    def _assert_lock_namespace_identity(
        self,
        *,
        root_parent_fd: int,
        root_fd: int,
        locks_fd: int,
        lock_fd: int,
        locks_dev: int,
        locks_ino: int,
        stripe_name: str,
        lock_dev: int,
        lock_ino: int,
    ) -> None:
        """Require the flock's directory and stripe to remain canonical."""

        self._assert_current_directory(root_parent_fd, self.root.name, root_fd)
        locks_metadata = os.fstat(locks_fd)
        if (
            not stat.S_ISDIR(locks_metadata.st_mode)
            or locks_metadata.st_dev != locks_dev
            or locks_metadata.st_ino != locks_ino
        ):
            raise OSError("storage lock directory identity changed")
        try:
            self._assert_current_directory(root_fd, self._LOCKS_DIRECTORY, locks_fd)
        except OSError as error:
            raise OSError("storage lock directory identity changed") from error
        lock_metadata = os.fstat(lock_fd)
        current = os.stat(stripe_name, dir_fd=locks_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_dev != lock_dev
            or lock_metadata.st_ino != lock_ino
            or not stat.S_ISREG(current.st_mode)
            or current.st_dev != lock_dev
            or current.st_ino != lock_ino
        ):
            raise OSError("storage lock stripe identity changed")

    def _assert_stored_lock_namespace_identity(self, stored: StoredObject) -> None:
        if (
            stored._locks_dev is None
            or stored._locks_ino is None
            or stored._stripe_name is None
            or stored._lock_dev is None
            or stored._lock_ino is None
        ):
            raise OSError("storage lock identity is unavailable")
        self._assert_lock_namespace_identity(
            root_parent_fd=stored._root_parent_fd,
            root_fd=stored._root_fd,
            locks_fd=stored._locks_fd,
            lock_fd=stored._lock_fd,
            locks_dev=stored._locks_dev,
            locks_ino=stored._locks_ino,
            stripe_name=stored._stripe_name,
            lock_dev=stored._lock_dev,
            lock_ino=stored._lock_ino,
        )

    def _read_owned_object(self, stored: StoredObject) -> bytes:
        """Read the retained object only when its inode identity remains exact."""

        if stored._object_dev is None or stored._object_ino is None:
            raise OSError("stored object ownership identity is unavailable")
        _, digest = self._canonical_key(stored)
        descriptor = -1
        try:
            descriptor = os.open(digest, self._file_read_flags(), dir_fd=stored._bucket_fd)
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_dev != stored._object_dev
                or metadata.st_ino != stored._object_ino
                or metadata.st_size != stored.size_bytes
            ):
                raise OSError("stored object ownership identity changed")
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = -1
                body = handle.read(self._MAX_SIZE + 1)
        finally:
            self._close_quietly(descriptor)
        if len(body) != stored.size_bytes:
            raise OSError("stored object size changed")
        if len(body) > self._MAX_SIZE or hashlib.sha256(body).hexdigest() != stored.digest:
            raise OSError("stored object digest changed")
        return body

    def assert_canonical_namespace_owned(self, stored: StoredObject) -> None:
        """Fail closed unless the live lease still owns the configured namespace.

        Cleanup separately requires the retained lock namespace before it may
        unlink a created object.  A detached bucket can still be cleaned only
        while that serialization authority remains canonical.
        """

        prefix, digest = self._canonical_key(stored)
        self._require_live_lease(stored)
        try:
            self._assert_current_directory(stored._root_parent_fd, self.root.name, stored._root_fd)
            configured_root = os.stat(self.root, follow_symlinks=False)
            if not self._matches_descriptor(configured_root, stored._root_fd):
                raise OSError("configured storage root was swapped")
            self._assert_stored_lock_namespace_identity(stored)
            self._assert_current_directory(stored._root_fd, prefix, stored._bucket_fd)
            object_metadata = os.stat(
                digest, dir_fd=stored._bucket_fd, follow_symlinks=False
            )
            if (
                stored._object_dev is None
                or stored._object_ino is None
                or not stat.S_ISREG(object_metadata.st_mode)
                or object_metadata.st_dev != stored._object_dev
                or object_metadata.st_ino != stored._object_ino
                or object_metadata.st_size != stored.size_bytes
            ):
                raise OSError("canonical stored object ownership identity changed")
            self._read_owned_object(stored)
        except OSError as error:
            raise OSError("canonical storage namespace ownership changed") from error

    def read_owned_verified(self, stored: StoredObject) -> bytes:
        """Verify a leased upload through its canonical, live namespace."""

        try:
            self.assert_canonical_namespace_owned(stored)
            return self._read_owned_object(stored)
        except OSError as error:
            raise StoredDocumentReadError("STORED_DOCUMENT_UNAVAILABLE") from error

    def read_verified(
        self,
        *,
        checksum_sha256: str,
        storage_key: str | None,
        expected_size: int | None,
    ) -> bytes:
        """Read persisted bytes using only their canonical database identity."""

        if not re.fullmatch(r"[0-9a-f]{64}", checksum_sha256):
            raise StoredDocumentReadError("STORED_DOCUMENT_IDENTITY_INVALID")
        canonical_key = f"sha256/{checksum_sha256[:2]}/{checksum_sha256}"
        if storage_key != canonical_key:
            raise StoredDocumentReadError("STORED_DOCUMENT_KEY_MISMATCH")
        if expected_size is None or expected_size < 1:
            raise StoredDocumentReadError("STORED_DOCUMENT_SIZE_INVALID")
        if expected_size > self._MAX_SIZE:
            raise StoredDocumentReadError("STORED_DOCUMENT_TOO_LARGE")

        root_fd = root_parent_fd = bucket_fd = descriptor = -1
        try:
            root_fd, root_parent_fd, _ = self._open_root(create=False)
            try:
                bucket_fd = os.open(
                    checksum_sha256[:2], self._directory_flags(), dir_fd=root_fd
                )
            except OSError as error:
                raise StoredDocumentReadError("STORED_DOCUMENT_OUTSIDE_ROOT") from error
            descriptor = os.open(checksum_sha256, self._file_read_flags(), dir_fd=bucket_fd)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise StoredDocumentReadError("STORED_DOCUMENT_NOT_REGULAR")
            if metadata.st_size != expected_size:
                raise StoredDocumentReadError("STORED_DOCUMENT_SIZE_MISMATCH")
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = -1
                body = handle.read(self._MAX_SIZE + 1)
        except StoredDocumentReadError:
            raise
        except OSError as error:
            raise StoredDocumentReadError("STORED_DOCUMENT_UNAVAILABLE") from error
        finally:
            self._close_quietly(descriptor)
            self._close_quietly(bucket_fd)
            self._close_quietly(root_fd)
            self._close_quietly(root_parent_fd)
        if len(body) != expected_size:
            raise StoredDocumentReadError("STORED_DOCUMENT_SIZE_MISMATCH")
        if len(body) > self._MAX_SIZE:
            raise StoredDocumentReadError("STORED_DOCUMENT_TOO_LARGE")
        if hashlib.sha256(body).hexdigest() != checksum_sha256:
            raise StoredDocumentReadError("STORED_DOCUMENT_DIGEST_MISMATCH")
        return body
