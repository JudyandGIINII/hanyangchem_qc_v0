from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import AsyncIterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class EmptyUploadError(Exception):
    """The streamed upload contained no bytes."""


class UploadTooLargeError(Exception):
    """The streamed upload exceeded the fixture limit."""


class ImmutableSourceStorage(Protocol):
    """Future P6 storage seam; P1 deliberately supplies no source-data adapter."""

    def put_immutable(self, digest: str, content: bytes, media_type: str) -> str: ...

    def open_verified(self, digest: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class StoredObject:
    digest: str
    storage_key: str
    size_bytes: int
    created: bool


class HashAddressedStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root)

    async def put_stream(self, chunks: AsyncIterable[bytes]) -> StoredObject:
        root_existed = self.root.exists()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        digest = hashlib.sha256()
        size = 0
        descriptor, temporary_name = tempfile.mkstemp(prefix="p3-upload-", dir=self.root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > 10 * 1024 * 1024:
                        raise UploadTooLargeError
                    digest.update(chunk)
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if size == 0:
                raise EmptyUploadError
            checksum = digest.hexdigest()
            directory = self.root / checksum[:2]
            directory.mkdir(exist_ok=True, mode=0o700)
            target = directory / checksum
            created = False
            try:
                os.link(temporary, target)
                created = True
                directory_fd = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except FileExistsError:
                pass
            return StoredObject(checksum, f"sha256/{checksum[:2]}/{checksum}", size, created)
        finally:
            temporary.unlink(missing_ok=True)
            if not root_existed:
                try:
                    self.root.rmdir()
                except OSError:
                    pass

    def remove_if_created(self, stored: StoredObject) -> None:
        if stored.created:
            (self.root / stored.storage_key.removeprefix("sha256/")).unlink(missing_ok=True)
