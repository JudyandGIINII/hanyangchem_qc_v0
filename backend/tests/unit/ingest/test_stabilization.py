from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from hyc_ingest.local_directory import LocalDirectorySourceAdapter
from hyc_ingest.stabilization import FileStabilizer


class FakeClock:

    def __init__(self, start_time: datetime | None = None) -> None:
        self.current_time = start_time or datetime(2026, 8, 13, 10, 0, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self.current_time += timedelta(seconds=seconds)

    def __call__(self) -> datetime:
        return self.current_time


def test_stabilization_requires_quiet_period_with_fake_clock(tmp_path: Path) -> None:
    file_path = tmp_path / "coa.pdf"
    file_path.write_bytes(b"%PDF-1.4 header")

    adapter = LocalDirectorySourceAdapter(tmp_path)
    fake_clock = FakeClock()

    stabilizer = FileStabilizer(quiet_period_seconds=5.0, clock=fake_clock)

    # 1. First observation (t = 0s) -> pending, establishes first_seen_at
    is_stable, meta, first_seen, reason = stabilizer.evaluate_entry(
        adapter, "coa.pdf", first_seen_at=None, last_size=None, last_modified=None
    )
    assert not is_stable
    assert meta is not None
    assert first_seen == fake_clock.current_time
    assert reason == "UNSTABLE_CHANGING"

    # 2. Observation at t = 3s (< 5s quiet period) -> pending
    fake_clock.advance(3.0)
    is_stable_3s, _, first_seen_3s, reason_3s = stabilizer.evaluate_entry(
        adapter,
        "coa.pdf",
        first_seen_at=first_seen,
        last_size=meta.size_bytes,
        last_modified=meta.modified_at,
    )
    assert not is_stable_3s
    assert first_seen_3s == first_seen
    assert reason_3s == "QUIET_PERIOD_PENDING"

    # 3. Observation at t = 6s (>= 5s quiet period) -> STABLE!
    fake_clock.advance(3.0)
    is_stable_6s, meta_6s, first_seen_6s, reason_6s = stabilizer.evaluate_entry(
        adapter,
        "coa.pdf",
        first_seen_at=first_seen,
        last_size=meta.size_bytes,
        last_modified=meta.modified_at,
    )
    assert is_stable_6s
    assert meta_6s is not None
    assert reason_6s is None


def test_stabilization_resets_on_size_or_mtime_change(tmp_path: Path) -> None:
    file_path = tmp_path / "writing.pdf"
    file_path.write_bytes(b"%PDF partial")

    adapter = LocalDirectorySourceAdapter(tmp_path)
    fake_clock = FakeClock()
    stabilizer = FileStabilizer(quiet_period_seconds=5.0, clock=fake_clock)

    # First observation at t = 0s
    _, meta1, first_seen1, _ = stabilizer.evaluate_entry(
        adapter, "writing.pdf", first_seen_at=None, last_size=None, last_modified=None
    )
    assert meta1 is not None

    # Advance fake clock by 4s and append data (size changes)
    fake_clock.advance(4.0)
    file_path.write_bytes(b"%PDF partial and finished content")

    # Second observation -> size changed -> timer resets to t = 4s
    is_stable2, meta2, first_seen2, reason2 = stabilizer.evaluate_entry(
        adapter,
        "writing.pdf",
        first_seen_at=first_seen1,
        last_size=meta1.size_bytes,
        last_modified=meta1.modified_at,
    )
    assert not is_stable2
    assert meta2 is not None
    assert first_seen2 == fake_clock.current_time  # Reset to t = 4s
    assert reason2 == "UNSTABLE_CHANGING"


def test_stabilization_fails_closed_when_file_vanishes(tmp_path: Path) -> None:
    file_path = tmp_path / "vanish.pdf"
    file_path.write_bytes(b"content")

    adapter = LocalDirectorySourceAdapter(tmp_path)
    fake_clock = FakeClock()
    stabilizer = FileStabilizer(quiet_period_seconds=5.0, clock=fake_clock)

    # First observation
    _, meta, first_seen, _ = stabilizer.evaluate_entry(
        adapter, "vanish.pdf", first_seen_at=None, last_size=None, last_modified=None
    )

    # Delete file
    file_path.unlink()

    # Next evaluation -> fails closed
    is_stable, meta_v, _, reason = stabilizer.evaluate_entry(
        adapter,
        "vanish.pdf",
        first_seen_at=first_seen,
        last_size=meta.size_bytes if meta else 7,
        last_modified=meta.modified_at if meta else None,
    )
    assert not is_stable
    assert meta_v is None
    assert reason is not None and reason.startswith("VANISHED")
