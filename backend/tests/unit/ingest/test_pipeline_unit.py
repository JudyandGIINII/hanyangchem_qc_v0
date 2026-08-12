from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

from hyc_ingest.local_directory import LocalDirectorySourceAdapter
from hyc_ingest.pipeline import IngestPipeline
from hyc_ingest.ports import SourceAdapter


def test_ingest_pipeline_flag_off_does_not_read_directory() -> None:
    mock_adapter = MagicMock(spec=SourceAdapter)
    pipeline = IngestPipeline(primary_storage_root="/tmp/dummy")

    mock_session = MagicMock()

    result = asyncio.run(
        pipeline.execute(
            session=mock_session,
            source_id="test_source",
            adapter=mock_adapter,
            enabled=False,
        )
    )

    assert not result.enabled
    assert result.processed_count == 0
    # Condition 4 of seam: list_entries MUST NOT be called when flag is off
    mock_adapter.list_entries.assert_not_called()
    mock_session.scalar.assert_not_called()


def test_storage_mirror_primary_succeeds_mirror_fails(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "sample_coa.pdf").write_bytes(b"%PDF-1.4 sample content")

    primary_dir = tmp_path / "primary_storage"
    unwritable_mirror_file = tmp_path / "blocked_mirror_file"
    unwritable_mirror_file.write_bytes(b"blocker")

    adapter = LocalDirectorySourceAdapter(source_dir)

    pipeline = IngestPipeline(
        primary_storage_root=primary_dir,
        mirror_roots=[unwritable_mirror_file],
        quiet_period_seconds=0.0,
    )

    mock_session = MagicMock()
    mock_session.scalar.return_value = None

    result = asyncio.run(
        pipeline.execute(
            session=mock_session,
            source_id="synthetic_nas",
            adapter=adapter,
            enabled=True,
        )
    )

    assert result.enabled
    assert result.processed_count == 1
    assert result.ingested_count == 1
    # Primary succeeded, mirror error explicitly recorded
    assert any("MIRROR_FAILED" in err for err in result.errors)
