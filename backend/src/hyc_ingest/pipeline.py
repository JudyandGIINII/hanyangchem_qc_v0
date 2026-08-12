from __future__ import annotations

import hashlib
from collections.abc import AsyncIterable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.storage import HashAddressedStorage
from hyc_data.models import Document, IngestCursor
from hyc_ingest.ports import SourceAdapter
from hyc_ingest.stabilization import ClockFunc, FileStabilizer, default_clock


async def _stream_bytes(data: bytes) -> AsyncIterable[bytes]:
    yield data


@dataclass(slots=True)
class IngestResult:
    """Summary result of an ingestion pipeline run."""

    enabled: bool
    processed_count: int = 0
    ingested_count: int = 0
    deduplicated_count: int = 0
    pending_stability_count: int = 0
    failed_count: int = 0
    errors: list[str] = field(default_factory=list)


class IngestPipeline:
    """Document ingestion pipeline wiring discovery, stabilization, hashing,
    deduplication using HashAddressedStorage + DB Document, and FR-DOC-005 storage mirroring.
    """

    def __init__(
        self,
        primary_storage_root: str | Path,
        mirror_roots: list[str | Path] | None = None,
        quiet_period_seconds: float = 5.0,
        clock: ClockFunc = default_clock,
    ) -> None:
        self.primary_storage_root = str(primary_storage_root)
        self.mirror_roots = [str(m) for m in (mirror_roots or [])]
        self.stabilizer = FileStabilizer(
            quiet_period_seconds=quiet_period_seconds,
            clock=clock,
        )

    async def execute(
        self,
        session: Session,
        source_id: str,
        adapter: SourceAdapter,
        *,
        enabled: bool = True,
    ) -> IngestResult:
        """Executes the ingestion pipeline.

        Condition 4: When enabled is False, nothing starts and list_entries is not called.
        """
        if not enabled:
            return IngestResult(enabled=False)

        result = IngestResult(enabled=True)
        entries = adapter.list_entries()
        result.processed_count = len(entries)

        for entry_id in entries:
            cursor = session.scalar(
                select(IngestCursor).where(
                    IngestCursor.source_id == source_id,
                    IngestCursor.entry_id == entry_id,
                )
            )

            if cursor is not None and cursor.status == "INGESTED":
                try:
                    meta = adapter.entry_metadata(entry_id)
                    if (
                        cursor.size_bytes == meta.size_bytes
                        and cursor.modified_at == meta.modified_at
                    ):
                        result.deduplicated_count += 1
                        continue
                except (FileNotFoundError, OSError):
                    cursor.status = "VANISHED"
                    cursor.error_reason = "File vanished after ingestion"
                    session.commit()
                    continue

            first_seen_at = cursor.first_seen_at if cursor else None
            last_size = cursor.size_bytes if cursor else None
            last_modified = cursor.modified_at if cursor else None

            is_stable, meta_info, updated_first_seen, reason = self.stabilizer.evaluate_entry(
                adapter=adapter,
                entry_id=entry_id,
                first_seen_at=first_seen_at,
                last_size=last_size,
                last_modified=last_modified,
            )

            now = self.stabilizer.clock()
            if cursor is None:
                cursor = IngestCursor(
                    id=uuid4(),
                    source_id=source_id,
                    entry_id=entry_id,
                    status="PENDING_STABILITY" if not is_stable else "INGESTED",
                    size_bytes=meta_info.size_bytes if meta_info else None,
                    modified_at=meta_info.modified_at if meta_info else None,
                    first_seen_at=updated_first_seen,
                    last_seen_at=now,
                    error_reason=reason,
                )
                session.add(cursor)
            else:
                cursor.size_bytes = meta_info.size_bytes if meta_info else None
                cursor.modified_at = meta_info.modified_at if meta_info else None
                cursor.first_seen_at = updated_first_seen
                cursor.last_seen_at = now
                cursor.error_reason = reason

            if not is_stable or meta_info is None:
                if reason and reason.startswith("VANISHED"):
                    cursor.status = "VANISHED"
                    result.failed_count += 1
                else:
                    cursor.status = "PENDING_STABILITY"
                    result.pending_stability_count += 1
                session.commit()
                continue

            try:
                content = adapter.open_entry(entry_id)
            except Exception as exc:
                cursor.status = "FAILED"
                cursor.error_reason = f"READ_ERROR: {exc}"
                result.failed_count += 1
                result.errors.append(f"{entry_id}: {exc}")
                session.commit()
                continue

            digest = hashlib.sha256(content).hexdigest()
            cursor.checksum_sha256 = digest

            storage = HashAddressedStorage(self.primary_storage_root)
            stored = await storage.put_stream(_stream_bytes(content))

            existing_doc = session.scalar(
                select(Document).where(Document.checksum_sha256 == digest)
            )

            if existing_doc is not None:
                storage.abandon(stored)
                cursor.document_id = existing_doc.id
                cursor.status = "INGESTED"
                result.deduplicated_count += 1
            else:
                doc_type = "COA_PDF" if content.startswith(b"%PDF-") else "SYNTHETIC_COA"
                media_type = (
                    "application/pdf" if doc_type == "COA_PDF" else "application/octet-stream"
                )
                doc = Document(
                    id=uuid4(),
                    checksum_sha256=digest,
                    document_type=doc_type,
                    original_filename=Path(entry_id).name,
                    storage_key=stored.storage_key,
                    media_type=media_type,
                    size_bytes=stored.size_bytes,
                    immutable=True,
                )
                session.add(doc)
                storage.prepare_successful_finalization(stored)
                session.flush()
                storage.finalize(stored)
                cursor.document_id = doc.id
                cursor.status = "INGESTED"
                result.ingested_count += 1

            # FR-DOC-005 Storage Mirror: Primary succeeds regardless of mirror outcome.
            if self.mirror_roots:
                for mirror_root in self.mirror_roots:
                    try:
                        mirror_target = Path(mirror_root) / f"sha256/{digest[:2]}/{digest}"
                        mirror_target.parent.mkdir(parents=True, exist_ok=True)
                        mirror_target.write_bytes(content)
                    except Exception as mirror_exc:
                        # Primary document is preserved; mirror failure is explicitly recorded.
                        result.errors.append(f"MIRROR_FAILED ({mirror_root}): {mirror_exc}")

            session.commit()

        return result
