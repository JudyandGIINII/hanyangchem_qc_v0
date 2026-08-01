from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal, require_role
from hyc_api.contracts import (
    ApprovalRequest,
    InspectionCreateRequest,
    InspectionResponse,
    InternalResultsRequest,
    LineageRequest,
)
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import (
    approve_inspection,
    clone_lineage,
    complete_idempotency,
    create_inspection,
    evaluate_inspection,
    put_internal_results,
    require_idempotency_key,
    require_if_match,
    reserve_idempotency,
    submit_inspection,
)
from hyc_data.models import InspectionCase

router = APIRouter(prefix="/api/v1", tags=["p3-inspections"])
DBSession = Annotated[Session, Depends(database_session)]


def _case(session: Session, inspection_id: UUID, *, lock: bool = False) -> InspectionCase:
    case = session.get(InspectionCase, inspection_id, with_for_update=lock)
    if case is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return case


@router.post("/inspections", status_code=status.HTTP_201_CREATED)
def create_case(
    request: Request,
    body: InspectionCreateRequest,
    session: DBSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> dict[str, str]:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    result = create_inspection(
        session,
        allocation_id=body.allocation_id,
        extraction_run_id=body.extraction_run_id,
        principal=principal,
        idempotency_key=require_idempotency_key(idempotency_key),
    )
    return {"inspection_id": str(result["inspection_id"])}


@router.get("/inspections/{inspection_id}", response_model=InspectionResponse)
def get_case(
    request: Request,
    inspection_id: UUID,
    session: DBSession,
) -> InspectionResponse:
    require_principal(request)
    return InspectionResponse.model_validate(
        evaluate_inspection(session, _case(session, inspection_id), persist=False)
    )


@router.put("/inspections/{inspection_id}/internal-results", response_model=InspectionResponse)
def internal_results(
    request: Request,
    inspection_id: UUID,
    body: InternalResultsRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> InspectionResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    case = _case(session, inspection_id, lock=True)
    result = put_internal_results(
        session,
        case=case,
        request=body,
        expected_version=require_if_match(if_match),
    )
    return InspectionResponse.model_validate(result)


@router.post("/inspections/{inspection_id}/submit", response_model=InspectionResponse)
def submit_case(
    request: Request,
    inspection_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> InspectionResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    result = submit_inspection(
        session,
        case=_case(session, inspection_id, lock=True),
        expected_version=require_if_match(if_match),
        principal=principal,
    )
    return InspectionResponse.model_validate(result)


@router.post("/inspections/{inspection_id}/approvals", response_model=InspectionResponse)
def approval(
    request: Request,
    inspection_id: UUID,
    body: ApprovalRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    fault_at: str | None = Header(default=None, alias="X-P3-Fault-At"),
) -> InspectionResponse:
    principal = require_principal(request)
    require_role(principal, "LEAD")
    key = require_idempotency_key(idempotency_key)
    record, replay = reserve_idempotency(
        session,
        principal=principal,
        scope=f"p3.inspections.{inspection_id}.approval",
        key=key,
        payload={"action": body.action, "reason": body.reason},
    )
    if replay is not None:
        return InspectionResponse.model_validate(replay)
    if fault_at and not request.app.state.settings.p3_fault_injection_enabled:
        raise HTTPException(status_code=403, detail="P3 fault injection is disabled")
    case = approve_inspection(
        session,
        case_id=inspection_id,
        expected_version=require_if_match(if_match),
        principal=principal,
        action=body.action,
        reason=body.reason,
        fault_at=fault_at,
    )
    session.refresh(case)
    response = evaluate_inspection(session, case, persist=False)
    complete_idempotency(record, status=200, body=response, resource_ref=str(case.id))
    session.commit()
    return InspectionResponse.model_validate(response)


def _lineage(
    request: Request,
    inspection_id: UUID,
    body: LineageRequest,
    session: Session,
    *,
    retest: bool,
) -> InspectionResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    case = clone_lineage(
        session,
        predecessor=_case(session, inspection_id, lock=True),
        reason=body.reason,
        retest=retest,
        principal=principal,
    )
    return InspectionResponse.model_validate(evaluate_inspection(session, case))


@router.post(
    "/inspections/{inspection_id}/revisions", response_model=InspectionResponse, status_code=201
)
def revision(
    request: Request,
    inspection_id: UUID,
    body: LineageRequest,
    session: DBSession,
) -> InspectionResponse:
    return _lineage(request, inspection_id, body, session, retest=False)


@router.post(
    "/inspections/{inspection_id}/retests", response_model=InspectionResponse, status_code=201
)
def retest(
    request: Request,
    inspection_id: UUID,
    body: LineageRequest,
    session: DBSession,
) -> InspectionResponse:
    return _lineage(request, inspection_id, body, session, retest=True)
