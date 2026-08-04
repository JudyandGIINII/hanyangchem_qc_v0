from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal, require_role
from hyc_api.contracts import (
    BoundingBox,
    DocumentResponse,
    ExtractionCandidate,
    ExtractionFieldResponse,
    ExtractionRunResponse,
    ExtractionValue,
    ReviewRequest,
    SourceReference,
)
from hyc_api.dependencies import database_session
from hyc_api.document_locks import DigestOwnershipGuard
from hyc_api.services.p3 import confirm_review, require_if_match
from hyc_api.storage import (
    EmptyUploadError,
    HashAddressedStorage,
    StoredDocumentReadError,
    UploadTooLargeError,
)
from hyc_data.models import Document, ExtractionFieldReview, ExtractionRun

router = APIRouter(prefix="/api/v1", tags=["p3-documents"])
DBSession = Annotated[Session, Depends(database_session)]


def _classify_document_bytes(body: bytes, *, p3_fixture_mode: bool) -> tuple[str, str] | None:
    """Classify from a bounded verified-byte header, never client metadata."""

    if body.startswith(b"%PDF-"):
        return "COA_PDF", "application/pdf"
    if p3_fixture_mode and body.startswith(b"P3 "):
        return "SYNTHETIC_COA", "application/octet-stream"
    return None


def _run_response(session: Session, run: ExtractionRun) -> ExtractionRunResponse:
    fields = list(
        session.scalars(
            select(ExtractionFieldReview)
            .where(ExtractionFieldReview.extraction_run_id == run.id)
            .order_by(ExtractionFieldReview.field_key)
        )
    )
    payload_fields = run.candidate_payload.get("fields", [])
    metadata = {
        item.get("field_id"): item
        for item in payload_fields
        if isinstance(item, dict) and isinstance(item.get("field_id"), str)
    }
    responses: list[ExtractionFieldResponse] = []
    for field in fields:
        item = metadata.get(str(field.id), {})
        source_field_key = item.get("source_field_key", field.field_key)
        review_reasons = item.get("review_reasons", [])
        provenance = item.get("provenance", {})
        mapping_disposition = item.get("mapping_disposition")
        mapped_field_key = item.get("mapped_field_key")
        responses.append(
            ExtractionFieldResponse(
                field_id=field.id,
                field_key=field.field_key,
                source_field_key=(
                    source_field_key if isinstance(source_field_key, str) else field.field_key
                ),
                original_text=field.original_text,
                ocr_text=field.ocr_text,
                final_text=field.final_text,
                source=field.source,  # type: ignore[arg-type]
                reason=field.reason,
                confidence=field.confidence,
                page_number=field.page_number,
                bbox=BoundingBox.model_validate(field.bbox),
                required=field.required,
                status=field.status,  # type: ignore[arg-type]
                mapping_disposition=(
                    mapping_disposition if mapping_disposition in {"MAP", "UNMAPPED"} else None
                ),
                mapped_field_key=(mapped_field_key if isinstance(mapped_field_key, str) else None),
                review_reasons=(
                    [str(reason) for reason in review_reasons]
                    if isinstance(review_reasons, list)
                    else []
                ),
                provenance=provenance if isinstance(provenance, dict) else {},
            )
        )
    return ExtractionRunResponse(
        run_id=run.id,
        document_id=run.document_id,
        status=run.status,  # type: ignore[arg-type]
        version=run.lock_version,
        provider_name=run.provider_name,
        conflicts=run.conflicts,
        fields=responses,
    )


def _fixture_candidate(document_id: UUID) -> ExtractionCandidate:
    reference = SourceReference(
        document_id=document_id,
        source_reference=str(document_id),
        page_number=1,
        bbox=BoundingBox(left=0.1, top=0.1, right=0.9, bottom=0.2),
    )
    values = [
        ("LOT_NO", "P3-SYNTH-LOT-20260801", "1.00"),
        ("CACL2_PURITY", "96.50", "1.00"),
        ("MOISTURE", "0.10", "0.85"),
    ]
    return ExtractionCandidate(
        schema_version="1.0",
        candidate_id=uuid4(),
        created_at=datetime.now(UTC),
        document=reference,
        provider_name="synthetic-fixture",
        values=[
            ExtractionValue(
                item_key=key,
                raw_text=raw,
                normalized_value=None,
                provenance=reference,
                confidence=float(confidence),
                review_required=True,
            )
            for key, raw, confidence in values
        ],
        review_required=True,
    )


def _safe_provenance(value: ExtractionValue) -> dict[str, object]:
    return {
        "page_number": value.provenance.page_number,
        "bbox": value.provenance.bbox.model_dump(mode="json"),
        "reading_order": value.reading_order,
        "recipe_id": value.recipe_id,
        "variant_id": value.variant_id,
        "rotation_degrees": value.rotation_degrees,
        "deskew_millidegrees": value.deskew_millidegrees,
        "deskew_status": value.deskew_status,
        "perspective_corrected": value.perspective_corrected,
    }


def _persist_candidate(
    session: Session, *, document_id: UUID, candidate: ExtractionCandidate
) -> ExtractionRun:
    if candidate.document.document_id != document_id:
        raise ValueError("candidate document identity mismatch")
    source_keys = [value.item_key for value in candidate.values]
    if len(source_keys) != len(set(source_keys)):
        raise ValueError("candidate source keys must be unique")
    if not candidate.review_required or any(
        not value.review_required for value in candidate.values
    ):
        raise ValueError("candidate review requirement is invalid")
    provider_name = (
        "local-paddleocr"
        if candidate.provider_name == "local-paddleocr"
        else "FixtureExtractionProvider"
    )
    run = ExtractionRun(
        id=uuid4(),
        document_id=document_id,
        provider_name=provider_name,
        status="REVIEW_REQUIRED",
        candidate_payload={
            "schema_version": candidate.schema_version,
            "candidate_id": str(candidate.candidate_id),
            "provider_name": provider_name,
            "review_required": True,
            "fields": [],
        },
        conflicts=[{"code": "REVIEW_REQUIRED", "visible": True}],
    )
    session.add(run)
    session.flush()

    payload_fields: list[dict[str, Any]] = []
    fields: list[ExtractionFieldReview] = []
    for value in candidate.values:
        field = ExtractionFieldReview(
            id=uuid4(),
            extraction_run_id=run.id,
            field_key=value.item_key,
            original_text=value.raw_text,
            ocr_text=value.raw_text,
            confidence=Decimal(str(value.confidence)),
            page_number=value.provenance.page_number,
            bbox=value.provenance.bbox.model_dump(mode="json"),
            required=True,
            status="REVIEW_REQUIRED",
        )
        fields.append(field)
        payload_fields.append(
            {
                "field_id": str(field.id),
                "source_field_key": value.item_key,
                "review_reasons": list(value.reason_codes),
                "provenance": _safe_provenance(value),
                "mapping_disposition": None,
                "mapped_field_key": None,
            }
        )
    run.candidate_payload = run.candidate_payload | {"fields": payload_fields}
    session.add_all(fields)
    session.flush()
    session.commit()
    session.refresh(run)
    return run


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    response: Response,
    session: DBSession,
    filename: str = Header(alias="X-Filename"),
) -> DocumentResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    if len(filename) > 512:
        raise HTTPException(status_code=422, detail="X-Filename exceeds 512 characters")
    storage = HashAddressedStorage(request.app.state.settings.p3_storage_root)
    stored = None
    cleanup_requested = False
    commit_attempted = False
    guard: DigestOwnershipGuard | None = None
    try:
        stored = await storage.put_stream(request.stream())
    except EmptyUploadError as error:
        raise HTTPException(status_code=422, detail="Document body is empty") from error
    except UploadTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Document body exceeds 10 MiB",
        ) from error
    try:
        # Stable serialization begins before any upload-owned bytes are read
        # or any DB ownership lookup occurs.  The filesystem lease remains a
        # defense-in-depth object-identity guard, not the authority boundary.
        guard = DigestOwnershipGuard(
            session,
            stored.digest,
            lock_engine=request.app.state.document_lock_engine,
        )
        guard.acquire()
        # This upload's descriptors and digest lock remain live from staging
        # through the ownership decision.  Do not reopen the configured path.
        verified_bytes = storage.read_owned_verified(stored)
        classification = _classify_document_bytes(
            verified_bytes, p3_fixture_mode=request.app.state.settings.p3_fixture_mode
        )
        if classification is None:
            raise HTTPException(status_code=422, detail="DOCUMENT_BYTES_UNSUPPORTED")
        document_type, media_type = classification
        existing = session.scalar(select(Document).where(Document.checksum_sha256 == stored.digest))
        if existing is not None:
            # Documents are immutable.  The verified bytes above establish that
            # this is a duplicate; legacy routing metadata is never reconciled.
            response.status_code = status.HTTP_200_OK
            return DocumentResponse(
                document_id=existing.id,
                checksum_sha256=existing.checksum_sha256,
                storage_key=stored.storage_key,
                deduplicated=True,
            )
        document = Document(
            checksum_sha256=stored.digest,
            document_type=document_type,
            original_filename=filename,
            storage_key=stored.storage_key,
            media_type=media_type,
            size_bytes=stored.size_bytes,
        )
        session.add(document)
        try:
            # This is a transaction boundary: a detached root/bucket/object
            # must never be flushed into a durable ownership row.
            storage.assert_canonical_namespace_owned(stored)
            # INSERT/constraint/driver failures during flush are known
            # pre-commit failures, so the outer handler can safely remove a
            # request-owned object.
            session.flush()
        except IntegrityError:
            # Preserve duplicate recovery for a row that appeared outside
            # this endpoint's digest lease.
            try:
                session.rollback()
            except Exception:
                pass
            try:
                existing = session.scalar(
                    select(Document).where(Document.checksum_sha256 == stored.digest)
                )
            except Exception:
                cleanup_requested = True
                raise
            if existing is None:
                cleanup_requested = True
                raise
            response.status_code = status.HTTP_200_OK
            return DocumentResponse(
                document_id=existing.id,
                checksum_sha256=existing.checksum_sha256,
                storage_key=stored.storage_key,
                deduplicated=True,
            )

        # Recheck after flush.  If an adversary detached the canonical entry,
        # rollback remains safe and descriptor-only cleanup removes only this
        # request's original inode.
        storage.prepare_successful_finalization(stored)
        # Only a post-flush commit exception has an uncertain outcome.
        commit_attempted = True
        try:
            session.commit()
        except IntegrityError:
            # An integrity error is a known failed commit.  With the digest
            # lease, endpoint writers cannot race this recovery path.
            try:
                session.rollback()
            except Exception:
                pass
            try:
                existing = session.scalar(
                    select(Document).where(Document.checksum_sha256 == stored.digest)
                )
            except Exception:
                cleanup_requested = True
                raise
            if existing is None:
                cleanup_requested = True
                raise
            response.status_code = status.HTTP_200_OK
            return DocumentResponse(
                document_id=existing.id,
                checksum_sha256=existing.checksum_sha256,
                storage_key=stored.storage_key,
                deduplicated=True,
            )
        except Exception:
            # A non-integrity commit exception can be an uncertain outcome.
            # Retain bytes: deleting after an unknown commit could strand a
            # committed immutable row.
            try:
                session.rollback()
            except Exception:
                pass
            raise
        # POSIX cannot atomically bind a namespace assertion and a database
        # commit. The supported adversary boundary is therefore the final
        # pre-commit assertion above, while the request still owns the digest
        # lease. Retained descriptors are released only after that commit;
        # later out-of-band namespace tampering remains fail-closed on every
        # persisted read via read_verified, rather than attempting an unsafe
        # deletion of an immutable committed record.
    except Exception:
        if not commit_attempted:
            # Pre-commit failures have no possible successful ownership row.
            # Cleanup is independent of rollback/select success so a failing
            # session cannot leave request-owned bytes behind.
            try:
                session.rollback()
            except Exception:
                pass
            cleanup_requested = True
        raise
    finally:
        try:
            if stored is not None:
                if cleanup_requested:
                    try:
                        storage.remove_if_created(stored)
                    except OSError:
                        # remove_if_created releases its descriptor lease in
                        # its own finally.  A refusal remains fail-closed.
                        pass
                else:
                    storage.finalize(stored)
        finally:
            if guard is not None:
                # Release only after finalize/cleanup has released the
                # storage lease.  An unlock failure invalidates its connection,
                # so no pooled connection can retain an unknown session lock.
                guard.release()
    return DocumentResponse(
        document_id=document.id,
        checksum_sha256=document.checksum_sha256,
        storage_key=document.storage_key or stored.storage_key,
        deduplicated=False,
    )


@router.post(
    "/documents/{document_id}/extractions",
    response_model=ExtractionRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def extract_document(
    request: Request,
    document_id: UUID,
    session: DBSession,
) -> ExtractionRunResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    document = session.scalar(select(Document).where(Document.id == document_id).with_for_update())
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    confirmed_run = session.scalar(
        select(ExtractionRun.id)
        .where(
            ExtractionRun.document_id == document.id,
            ExtractionRun.status == "CONFIRMED",
        )
        .with_for_update()
        .limit(1)
    )
    if confirmed_run is not None:
        raise HTTPException(status_code=409, detail="DOCUMENT_EXTRACTION_ALREADY_CONFIRMED")
    try:
        body = HashAddressedStorage(request.app.state.settings.p3_storage_root).read_verified(
            checksum_sha256=document.checksum_sha256,
            storage_key=document.storage_key,
            expected_size=document.size_bytes,
        )
    except StoredDocumentReadError as error:
        session.rollback()
        raise HTTPException(status_code=422, detail=error.code) from error
    classification = _classify_document_bytes(
        body, p3_fixture_mode=request.app.state.settings.p3_fixture_mode
    )
    if classification is None:
        session.rollback()
        raise HTTPException(status_code=422, detail="DOCUMENT_BYTES_UNSUPPORTED")
    document_type, _media_type = classification
    if document_type == "COA_PDF":
        if not request.app.state.settings.local_ocr_enabled:
            raise HTTPException(status_code=422, detail="LOCAL_OCR_DISABLED")
        provider = request.app.state.local_ocr_provider
        if provider is None:
            raise HTTPException(status_code=503, detail="LOCAL_OCR_UNAVAILABLE")
        from hyc_local_ocr.errors import LocalOcrError

        try:
            candidate = provider.extract(str(document.id), str(document.id), document_bytes=body)
        except LocalOcrError as error:
            session.rollback()
            raise HTTPException(status_code=422, detail=error.code) from error
    else:
        candidate = _fixture_candidate(document.id)
    try:
        run = _persist_candidate(session, document_id=document.id, candidate=candidate)
    except Exception:
        session.rollback()
        raise
    return _run_response(session, run)


@router.get(
    "/documents/{document_id}/extractions/{run_id}",
    response_model=ExtractionRunResponse,
)
def get_extraction_run(
    request: Request,
    document_id: UUID,
    run_id: UUID,
    session: DBSession,
) -> ExtractionRunResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    run = session.get(ExtractionRun, run_id)
    if run is None or run.document_id != document_id:
        raise HTTPException(status_code=404, detail="Extraction run not found")
    return _run_response(session, run)


@router.put(
    "/documents/{document_id}/reviews/{run_id}",
    response_model=ExtractionRunResponse,
)
def review_document(
    request: Request,
    document_id: UUID,
    run_id: UUID,
    body: ReviewRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> ExtractionRunResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    run = confirm_review(
        session,
        document_id=document_id,
        run_id=run_id,
        request=body,
        expected_version=require_if_match(if_match),
        principal=principal,
    )
    return _run_response(session, run)
