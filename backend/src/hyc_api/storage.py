from __future__ import annotations

from typing import Protocol


class ImmutableSourceStorage(Protocol):
    """Future P6 storage seam; P1 deliberately supplies no source-data adapter."""

    def put_immutable(self, digest: str, content: bytes, media_type: str) -> str: ...

    def open_verified(self, digest: str) -> bytes: ...
