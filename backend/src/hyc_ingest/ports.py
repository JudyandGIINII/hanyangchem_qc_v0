from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceEntryMetadata:
    """Metadata describing a document entry in a source."""

    size_bytes: int
    modified_at: datetime


class SourceAdapter(Protocol):
    """Protocol for document source ingestion adapters (e.g. NAS, Drive, Local).

    Consistent with ImmutableSourceStorage protocol style in hyc_api.storage.
    """

    def list_entries(self) -> list[str]:
        """Return relative identifiers/paths of available files in the source."""
        ...

    def open_entry(self, entry_id: str) -> bytes:
        """Read full raw content bytes of a specified entry."""
        ...

    def entry_metadata(self, entry_id: str) -> SourceEntryMetadata:
        """Return size in bytes and last modification time of an entry."""
        ...
