from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from hyc_ingest.ports import SourceAdapter, SourceEntryMetadata

ClockFunc = Callable[[], datetime]


def default_clock() -> datetime:
    return datetime.now(UTC)


class FileStabilizer:
    """FR-DOC-002 file stabilization evaluator.

    Takes an injected clock callable so stabilization tests drive a fake clock
    and remain fully deterministic without sleeping. Fails closed on vanished,
    partial, or changing files.
    """

    def __init__(
        self,
        quiet_period_seconds: float = 5.0,
        clock: ClockFunc = default_clock,
    ) -> None:
        self.quiet_period = timedelta(seconds=quiet_period_seconds)
        self.clock = clock

    def evaluate_entry(
        self,
        adapter: SourceAdapter,
        entry_id: str,
        first_seen_at: datetime | None,
        last_size: int | None,
        last_modified: datetime | None,
    ) -> tuple[bool, SourceEntryMetadata | None, datetime, str | None]:
        """Evaluates whether an entry is stable.

        Returns:
            (is_stable, metadata_or_none, updated_first_seen_at, failure_reason)
        """
        now = self.clock()

        try:
            meta = adapter.entry_metadata(entry_id)
        except (FileNotFoundError, OSError, ValueError) as error:
            return False, None, now, f"VANISHED: {error}"

        if meta.size_bytes < 0:
            return False, meta, now, "INVALID_SIZE"

        if (
            first_seen_at is None
            or last_size is None
            or last_modified is None
            or meta.size_bytes != last_size
            or meta.modified_at != last_modified
        ):
            if self.quiet_period.total_seconds() == 0:
                return True, meta, now, None
            return False, meta, now, "UNSTABLE_CHANGING"


        elapsed = now - first_seen_at
        if elapsed >= self.quiet_period:
            return True, meta, first_seen_at, None

        return False, meta, first_seen_at, "QUIET_PERIOD_PENDING"
