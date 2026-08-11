from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal
from hyc_api.contracts import ReportCreateRequest, ReportCreateResponse, ReportJobResponse
from hyc_api.db_errors import _commit
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import require_idempotency_key
from hyc_api.services.reports import InProcessReportRunner, create_report_job, load_report_job
from hyc_api.storage import HashAddressedStorage, StoredDocumentReadError
from hyc_data.models import AuditLog, ReportArtifact
from hyc_domain.reports import ReportKind, UnsupportedReportKind

router = APIRouter(prefix="/api/v1", tags=["p6-reports"])
DBSession = Annotated[Session, Depends(database_session)]

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post("/reports", response_model=ReportCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_report(
    request: Request,
    body: ReportCreateRequest,
    session: DBSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ReportCreateResponse:
    principal = require_principal(request)
    try:
        result = create_report_job(
            session,
            kind=body.kind,
            parameters=body.parameters,
            principal=principal,
            idempotency_key=require_idempotency_key(idempotency_key),
            runner=InProcessReportRunner(request.app.state.settings),
        )
    except UnsupportedReportKind as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return ReportCreateResponse(job_id=UUID(str(result["job_id"])), state=str(result["state"]))


@router.get("/reports/{job_id}", response_model=ReportJobResponse)
def get_report(job_id: UUID, request: Request, session: DBSession) -> ReportJobResponse:
    require_principal(request)
    try:
        job = load_report_job(session, job_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail="Report job not found") from error
    artifact = session.scalar(select(ReportArtifact).where(ReportArtifact.report_job_id == job.id))
    return ReportJobResponse(
        job_id=job.id,
        kind=ReportKind(job.kind),
        state=job.state,
        failure_code=job.failure_code,
        artifact_digest=artifact.content_digest if artifact is not None else None,
    )


@router.get("/reports/{job_id}/download")
def download_report(job_id: UUID, request: Request, session: DBSession) -> StreamingResponse:
    principal = require_principal(request)
    try:
        job = load_report_job(session, job_id)
    except RuntimeError as error:
        raise HTTPException(status_code=404, detail="Report job not found") from error
    if job.state != "SUCCEEDED":
        raise HTTPException(status_code=409, detail="Report artifact is not ready")
    artifact = session.scalar(select(ReportArtifact).where(ReportArtifact.report_job_id == job.id))
    if artifact is None:
        raise HTTPException(status_code=404, detail="Report artifact not found")
    try:
        storage = HashAddressedStorage(request.app.state.settings.p6_report_storage_root)
        payload = storage.read_verified(
            checksum_sha256=artifact.content_digest,
            storage_key=artifact.storage_key,
            expected_size=artifact.byte_size,
        )
    except StoredDocumentReadError as error:
        raise HTTPException(status_code=404, detail=error.code) from error
    session.add(
        AuditLog(
            entity_type="report_job",
            entity_id=job.id,
            action="REPORT_DOWNLOADED",
            payload={
                "actor_id": str(principal.actor_id),
                "role": principal.role,
                "content_digest": artifact.content_digest,
            },
        )
    )
    _commit(
        session,
        stale_detail="Stale report download audit",
        conflict_detail="Report download audit conflicts with existing record",
    )
    chunks: Iterator[bytes] = iter((payload,))
    return StreamingResponse(
        chunks,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f'attachment; filename="report-{job.id}.xlsx"'},
    )
