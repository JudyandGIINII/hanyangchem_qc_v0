from __future__ import annotations

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal, require_role
from hyc_api.contracts import (
    NonconformanceApprovalResponse,
    NonconformanceAttachmentResponse,
    NonconformanceCreateRequest,
    NonconformanceDispositionResponse,
    NonconformanceResponse,
    NonconformanceUpdateRequest,
)
from hyc_api.db_errors import _commit
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import require_if_match
from hyc_data.models import (
    Document,
    InspectionCase,
    Nonconformance,
    NonconformanceApproval,
    NonconformanceAttachment,
    NonconformanceDisposition,
    SpecItem,
    utc_now,
)

router = APIRouter(prefix="/api/v1", tags=["p5-nonconformances"])
DBSession = Annotated[Session, Depends(database_session)]


def _nonconformance(session: Session, value_id: UUID, *, lock: bool = False) -> Nonconformance:
    statement = select(Nonconformance).where(
        Nonconformance.id == value_id,
        Nonconformance.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Nonconformance not found")
    return value


def _disposition(
    session: Session, disposition_id: UUID, *, lock: bool = False
) -> NonconformanceDisposition:
    statement = select(NonconformanceDisposition).where(
        NonconformanceDisposition.id == disposition_id,
        NonconformanceDisposition.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Nonconformance disposition not found")
    return value


def _inspection_case(session: Session, case_id: UUID, *, lock: bool) -> InspectionCase:
    statement = select(InspectionCase).where(
        InspectionCase.id == case_id,
        InspectionCase.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Inspection case not found")
    return value


def _spec_item(session: Session, item_id: UUID, *, lock: bool) -> SpecItem:
    statement = select(SpecItem).where(SpecItem.id == item_id, SpecItem.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Spec item not found")
    return value


def _document(session: Session, document_id: UUID, *, lock: bool) -> Document:
    statement = select(Document).where(Document.id == document_id, Document.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return value


def _require_current_version(current_version: int, if_match: str | None) -> None:
    if current_version != require_if_match(if_match):
        raise HTTPException(status_code=409, detail="Stale nonconformance version")


def _disposition_response(value: NonconformanceDisposition) -> NonconformanceDispositionResponse:
    return NonconformanceDispositionResponse(
        id=value.id,
        code=value.code,
        name=value.name,
        active=value.active,
        sort_order=value.sort_order,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _response(value: Nonconformance) -> NonconformanceResponse:
    return NonconformanceResponse(
        id=value.id,
        ncr_number=value.ncr_number,
        inspection_case_id=value.inspection_case_id,
        spec_item_id=value.spec_item_id,
        severity=cast(Literal["MAJOR", "MINOR"] | None, value.severity),
        quantity=value.quantity,
        description=value.description,
        cause=value.cause,
        disposition_id=value.disposition_id,
        disposition_snapshot=value.disposition_snapshot,
        target_completion_date=value.target_completion_date,
        completion_date=value.completion_date,
        status=cast(
            Literal["DRAFT", "SUBMITTED", "APPROVED", "REJECTED", "CLOSED"], value.status
        ),
        retest_case_id=value.retest_case_id,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _approval_response(value: NonconformanceApproval) -> NonconformanceApprovalResponse:
    return NonconformanceApprovalResponse(
        id=value.id,
        nonconformance_id=value.nonconformance_id,
        actor_id=value.actor_id,
        actor_role=cast(Literal["LEAD"], value.actor_role),
        action=cast(Literal["APPROVE", "REJECT"], value.action),
        created_at=value.created_at,
    )


def _attachment_response(value: NonconformanceAttachment) -> NonconformanceAttachmentResponse:
    return NonconformanceAttachmentResponse(
        id=value.id,
        nonconformance_id=value.nonconformance_id,
        document_id=value.document_id,
    )


def _validate_references(
    session: Session,
    body: NonconformanceCreateRequest,
    *,
    lock: bool,
) -> None:
    _inspection_case(session, body.inspection_case_id, lock=lock)
    if body.spec_item_id is not None:
        _spec_item(session, body.spec_item_id, lock=lock)
    if body.retest_case_id is not None:
        _inspection_case(session, body.retest_case_id, lock=lock)


def _apply(value: Nonconformance, body: NonconformanceUpdateRequest) -> None:
    value.ncr_number = body.ncr_number
    value.inspection_case_id = body.inspection_case_id
    value.spec_item_id = body.spec_item_id
    value.severity = body.severity
    value.quantity = body.quantity
    value.description = body.description
    value.cause = body.cause
    value.target_completion_date = body.target_completion_date
    value.completion_date = body.completion_date
    value.status = body.status
    value.retest_case_id = body.retest_case_id


@router.get("/nonconformance-dispositions", response_model=list[NonconformanceDispositionResponse])
def list_dispositions(
    request: Request,
    session: DBSession,
    include_inactive: bool = False,
) -> list[NonconformanceDispositionResponse]:
    require_principal(request)
    statement = select(NonconformanceDisposition).where(
        NonconformanceDisposition.deleted_at.is_(None)
    )
    if not include_inactive:
        statement = statement.where(NonconformanceDisposition.active.is_(True))
    return [
        _disposition_response(value)
        for value in session.scalars(
            statement.order_by(NonconformanceDisposition.sort_order, NonconformanceDisposition.id)
        )
    ]


@router.get("/nonconformances", response_model=list[NonconformanceResponse])
def list_nonconformances(request: Request, session: DBSession) -> list[NonconformanceResponse]:
    require_principal(request)
    return [
        _response(value)
        for value in session.scalars(
            select(Nonconformance)
            .where(Nonconformance.deleted_at.is_(None))
            .order_by(Nonconformance.ncr_number, Nonconformance.id)
        )
    ]


@router.post(
    "/nonconformances",
    response_model=NonconformanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_nonconformance(
    request: Request,
    body: NonconformanceCreateRequest,
    session: DBSession,
) -> NonconformanceResponse:
    require_principal(request)
    _validate_references(session, body, lock=True)
    disposition = (
        _disposition(session, body.disposition_id, lock=True)
        if body.disposition_id is not None
        else None
    )
    value = Nonconformance(
        **body.model_dump(),
        disposition_snapshot=(
            {"code": disposition.code, "name": disposition.name}
            if disposition is not None
            else None
        ),
    )
    session.add(value)
    _commit(
        session,
        stale_detail="Stale nonconformance version",
        conflict_detail="Nonconformance data conflicts with existing record",
    )
    session.refresh(value)
    return _response(value)


@router.get("/nonconformances/{nonconformance_id}", response_model=NonconformanceResponse)
def get_nonconformance(
    request: Request,
    nonconformance_id: UUID,
    session: DBSession,
) -> NonconformanceResponse:
    require_principal(request)
    return _response(_nonconformance(session, nonconformance_id))


@router.put("/nonconformances/{nonconformance_id}", response_model=NonconformanceResponse)
def update_nonconformance(
    request: Request,
    nonconformance_id: UUID,
    body: NonconformanceUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> NonconformanceResponse:
    require_principal(request)
    value = _nonconformance(session, nonconformance_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    _validate_references(session, body, lock=True)
    if value.disposition_id != body.disposition_id:
        disposition = (
            _disposition(session, body.disposition_id, lock=True)
            if body.disposition_id is not None
            else None
        )
        value.disposition_id = body.disposition_id
        value.disposition_snapshot = (
            {"code": disposition.code, "name": disposition.name}
            if disposition is not None
            else None
        )
    _apply(value, body)
    value.updated_at = utc_now()
    _commit(
        session,
        stale_detail="Stale nonconformance version",
        conflict_detail="Nonconformance data conflicts with existing record",
    )
    session.refresh(value)
    return _response(value)


def _approve_or_reject(
    request: Request,
    nonconformance_id: UUID,
    session: Session,
    if_match: str | None,
    *,
    action: Literal["APPROVE", "REJECT"],
) -> NonconformanceApprovalResponse:
    principal = require_principal(request)
    require_role(principal, "LEAD")
    value = _nonconformance(session, nonconformance_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    value.status = "APPROVED" if action == "APPROVE" else "REJECTED"
    value.updated_at = utc_now()
    approval = NonconformanceApproval(
        nonconformance_id=value.id,
        actor_id=principal.actor_id,
        actor_role=principal.role,
        action=action,
    )
    session.add(approval)
    _commit(
        session,
        stale_detail="Stale nonconformance version",
        conflict_detail="Nonconformance data conflicts with existing record",
    )
    session.refresh(approval)
    return _approval_response(approval)


@router.post(
    "/nonconformances/{nonconformance_id}/approve",
    response_model=NonconformanceApprovalResponse,
)
def approve_nonconformance(
    request: Request,
    nonconformance_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> NonconformanceApprovalResponse:
    return _approve_or_reject(
        request,
        nonconformance_id,
        session,
        if_match,
        action="APPROVE",
    )


@router.post(
    "/nonconformances/{nonconformance_id}/reject",
    response_model=NonconformanceApprovalResponse,
)
def reject_nonconformance(
    request: Request,
    nonconformance_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> NonconformanceApprovalResponse:
    return _approve_or_reject(
        request,
        nonconformance_id,
        session,
        if_match,
        action="REJECT",
    )


@router.post(
    "/nonconformances/{nonconformance_id}/attachments/{document_id}",
    response_model=NonconformanceAttachmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_attachment(
    request: Request,
    nonconformance_id: UUID,
    document_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> NonconformanceAttachmentResponse:
    require_principal(request)
    value = _nonconformance(session, nonconformance_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    _document(session, document_id, lock=True)
    attachment = NonconformanceAttachment(nonconformance_id=value.id, document_id=document_id)
    value.updated_at = utc_now()
    session.add(attachment)
    _commit(
        session,
        stale_detail="Stale nonconformance version",
        conflict_detail="Nonconformance data conflicts with existing record",
    )
    session.refresh(attachment)
    return _attachment_response(attachment)


@router.delete(
    "/nonconformances/{nonconformance_id}/attachments/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_attachment(
    request: Request,
    nonconformance_id: UUID,
    document_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Response:
    require_principal(request)
    value = _nonconformance(session, nonconformance_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    attachment = session.scalar(
        select(NonconformanceAttachment)
        .where(
            NonconformanceAttachment.nonconformance_id == value.id,
            NonconformanceAttachment.document_id == document_id,
        )
        .with_for_update()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="Nonconformance attachment not found")
    value.updated_at = utc_now()
    session.delete(attachment)
    _commit(
        session,
        stale_detail="Stale nonconformance version",
        conflict_detail="Nonconformance data conflicts with existing record",
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
