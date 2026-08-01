from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal, require_role
from hyc_api.contracts import (
    BoundingBox,
    DocumentResponse,
    ExtractionFieldResponse,
    ExtractionRunResponse,
    ReviewRequest,
)
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import confirm_review, require_if_match
from hyc_api.storage import EmptyUploadError, HashAddressedStorage, UploadTooLargeError
from hyc_data.models import Document, ExtractionFieldReview, ExtractionRun

router = APIRouter(prefix="/api/v1", tags=["p3-documents"])
DBSession = Annotated[Session, Depends(database_session)]


def _run_response(session: Session, run: ExtractionRun) -> ExtractionRunResponse:
    fields = list(
        session.scalars(
            select(ExtractionFieldReview)
            .where(ExtractionFieldReview.extraction_run_id == run.id)
            .order_by(ExtractionFieldReview.field_key)
        )
    )
    return ExtractionRunResponse(
        run_id=run.id,
        document_id=run.document_id,
        status=run.status,  # type: ignore[arg-type]
        version=run.lock_version,
        conflicts=run.conflicts,
        fields=[
            ExtractionFieldResponse(
                field_key=field.field_key,
                original_text=field.original_text,
                ocr_text=field.ocr_text,
                confidence=field.confidence,
                page_number=field.page_number,
                bbox=BoundingBox.model_validate(field.bbox),
                required=field.required,
                status=field.status,  # type: ignore[arg-type]
            )
            for field in fields
        ],
    )


@router.post("/documents", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    response: Response,
    session: DBSession,
    filename: str = Header(alias="X-Filename"),
) -> DocumentResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    try:
        stored = await HashAddressedStorage(request.app.state.settings.p3_storage_root).put_stream(
            request.stream()
        )
    except EmptyUploadError as error:
        raise HTTPException(status_code=422, detail="Document body is empty") from error
    except UploadTooLargeError as error:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Document body exceeds 10 MiB",
        ) from error
    existing = session.scalar(select(Document).where(Document.checksum_sha256 == stored.digest))
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return DocumentResponse(
            document_id=existing.id,
            checksum_sha256=existing.checksum_sha256,
            storage_key=existing.storage_key or stored.storage_key,
            deduplicated=True,
        )
    document = Document(
        checksum_sha256=stored.digest,
        document_type="SYNTHETIC_COA",
        original_filename=filename,
        storage_key=stored.storage_key,
        media_type=request.headers.get("Content-Type", "application/octet-stream"),
        size_bytes=stored.size_bytes,
    )
    try:
        session.add(document)
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(Document).where(Document.checksum_sha256 == stored.digest))
        if existing is None:
            HashAddressedStorage(request.app.state.settings.p3_storage_root).remove_if_created(
                stored
            )
            raise
        response.status_code = status.HTTP_200_OK
        return DocumentResponse(
            document_id=existing.id,
            checksum_sha256=existing.checksum_sha256,
            storage_key=existing.storage_key or stored.storage_key,
            deduplicated=True,
        )
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
    if session.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    candidate_fields = [
        {"key": "LOT_NO", "raw": "P3-SYNTH-LOT-20260801", "confidence": "1.00"},
        {"key": "CACL2_PURITY", "raw": "96.50", "confidence": "1.00"},
        {"key": "MOISTURE", "raw": "0.10", "confidence": "0.85"},
    ]
    candidate = {
        "provider": "FixtureExtractionProvider",
        "review_required": True,
        "fields": candidate_fields,
    }
    run = ExtractionRun(
        document_id=document_id,
        provider_name="FixtureExtractionProvider",
        status="REVIEW_REQUIRED",
        candidate_payload=candidate,
        conflicts=[{"code": "REVIEW_REQUIRED", "visible": True}],
    )
    session.add(run)
    session.flush()
    for item in candidate_fields:
        raw = str(item["raw"])
        session.add(
            ExtractionFieldReview(
                extraction_run_id=run.id,
                field_key=str(item["key"]),
                original_text=raw,
                ocr_text=raw,
                confidence=Decimal(str(item["confidence"])),
                page_number=1,
                bbox={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.2},
                required=True,
                status="REVIEW_REQUIRED",
            )
        )
    session.commit()
    session.refresh(run)
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
