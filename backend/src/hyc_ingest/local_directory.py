from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from hyc_ingest.ports import SourceAdapter, SourceEntryMetadata

_TEMPORARY_EXTENSIONS = (".tmp", ".part", ".crdownload", ".swp", ".bak")
_IGNORED_PREFIXES = (".~lock", ".", "~$")


class LocalDirectorySourceAdapter(SourceAdapter):
    """Synthetic local directory adapter implementing SourceAdapter.

    Operates over a local file system directory without external calls.
    """

    def __init__(self, directory_path: str | Path) -> None:
        self.root = Path(directory_path).resolve()

    def _resolve_safe_path(self, entry_id: str) -> Path:
        target = (self.root / entry_id).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError(f"Path traversal attempted outside root: {entry_id}")
        return target

    @staticmethod
    def _is_temporary_or_ignored(filename: str) -> bool:
        if any(filename.startswith(prefix) for prefix in _IGNORED_PREFIXES):
            return True
        if any(filename.lower().endswith(ext) for ext in _TEMPORARY_EXTENSIONS):
            return True
        return False

    def list_entries(self) -> list[str]:
        """List relative paths of non-temporary regular files within the root directory."""
        if not self.root.exists() or not self.root.is_dir():
            return []
        entries: list[str] = []
        for path in self.root.rglob("*"):
            if path.is_file() and not self._is_temporary_or_ignored(path.name):
                rel_posix = path.relative_to(self.root).as_posix()
                entries.append(rel_posix)
        entries.sort()
        return entries

    def entry_metadata(self, entry_id: str) -> SourceEntryMetadata:
        """Return file size and modification timestamp in UTC."""
        target = self._resolve_safe_path(entry_id)
        if not target.is_file():
            raise FileNotFoundError(f"Source entry missing or not a file: {entry_id}")
        st = target.stat()
        return SourceEntryMetadata(
            size_bytes=st.st_size,
            modified_at=datetime.fromtimestamp(st.st_mtime, tz=UTC),
        )

    def open_entry(self, entry_id: str) -> bytes:
        """Read and return full byte content of the file."""
        target = self._resolve_safe_path(entry_id)
        if not target.is_file():
            raise FileNotFoundError(f"Source entry missing or not a file: {entry_id}")
        return target.read_bytes()
