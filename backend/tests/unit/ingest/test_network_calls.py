from __future__ import annotations

import asyncio
import socket
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from hyc_ingest import FileStabilizer, IngestPipeline, LocalDirectorySourceAdapter


def test_hyc_ingest_makes_zero_network_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_connect(*args: object, **kwargs: object) -> None:
        raise RuntimeError("HYC ingest seam violated prohibition: network call attempted!")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    monkeypatch.setattr(socket, "create_connection", forbidden_connect)

    # 1. Instantiate adapter and test file operations
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    file_path = source_dir / "test_coa.pdf"
    file_path.write_bytes(b"%PDF-1.4 test")

    adapter = LocalDirectorySourceAdapter(source_dir)
    entries = adapter.list_entries()
    assert entries == ["test_coa.pdf"]

    meta = adapter.entry_metadata("test_coa.pdf")
    assert meta.size_bytes == 13

    data = adapter.open_entry("test_coa.pdf")
    assert data == b"%PDF-1.4 test"

    # 2. Instantiate FileStabilizer and test evaluation
    stabilizer = FileStabilizer(quiet_period_seconds=5.0)
    is_stable, _, _, _ = stabilizer.evaluate_entry(
        adapter, "test_coa.pdf", first_seen_at=None, last_size=None, last_modified=None
    )
    assert not is_stable


    # 3. Instantiate pipeline and test execute with flag off and on
    primary_dir = tmp_path / "primary"
    pipeline = IngestPipeline(primary_storage_root=primary_dir, quiet_period_seconds=0.0)

    mock_session = MagicMock()
    mock_session.scalar.return_value = None

    result_off = asyncio.run(
        pipeline.execute(mock_session, "source1", adapter, enabled=False)
    )
    assert not result_off.enabled

    result_on = asyncio.run(
        pipeline.execute(mock_session, "source1", adapter, enabled=True)
    )
    assert result_on.enabled
