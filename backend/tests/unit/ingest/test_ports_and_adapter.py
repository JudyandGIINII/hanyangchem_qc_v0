from __future__ import annotations

from pathlib import Path

import pytest

from hyc_ingest.local_directory import LocalDirectorySourceAdapter


def test_local_directory_adapter_lists_and_filters_files(tmp_path: Path) -> None:
    # Create regular valid files
    (tmp_path / "valid_coa.pdf").write_bytes(b"%PDF-1.4 test coa")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "sample.txt").write_bytes(b"sample data")

    # Create ignored temporary or lock files
    (tmp_path / "upload.tmp").write_bytes(b"temp")
    (tmp_path / "doc.part").write_bytes(b"part")
    (tmp_path / ".~lock.file.pdf").write_bytes(b"lock")
    (tmp_path / ".hidden_file").write_bytes(b"hidden")

    adapter = LocalDirectorySourceAdapter(tmp_path)
    entries = adapter.list_entries()

    assert entries == ["subdir/sample.txt", "valid_coa.pdf"]


def test_local_directory_adapter_metadata_and_open(tmp_path: Path) -> None:
    file_path = tmp_path / "document.pdf"
    content = b"%PDF-1.5 test document"
    file_path.write_bytes(content)

    adapter = LocalDirectorySourceAdapter(tmp_path)
    meta = adapter.entry_metadata("document.pdf")

    assert meta.size_bytes == len(content)
    assert meta.modified_at is not None

    data = adapter.open_entry("document.pdf")
    assert data == content


def test_local_directory_adapter_path_traversal_prevention(tmp_path: Path) -> None:
    adapter = LocalDirectorySourceAdapter(tmp_path)
    with pytest.raises(ValueError, match="Path traversal attempted"):
        adapter.open_entry("../outside.txt")
