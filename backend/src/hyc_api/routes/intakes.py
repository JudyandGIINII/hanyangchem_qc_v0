from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import create_fixture_session, require_principal, require_role
from hyc_api.contracts import (
    FixtureContextResponse,
    IntakeRequest,
    IntakeResponse,
    LocalSessionRequest,
    LocalSessionResponse,
)
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import create_intake, require_idempotency_key
from hyc_data.models import SpecItem, StandardTestItem
from hyc_data.p3_fixture_seed import (
    MATERIAL_ID,
    MODEL_ID,
    SPEC_VERSION_ID,
    SUPPLIER_ID,
    seed_p3_fixture,
)

router = APIRouter(prefix="/api/v1", tags=["p3"])
DBSession = Annotated[Session, Depends(database_session)]


@router.post("/local-auth/sessions", response_model=LocalSessionResponse)
def local_session(request: Request, body: LocalSessionRequest) -> LocalSessionResponse:
    session_handle, principal = create_fixture_session(request, body.fixture_principal)
    return LocalSessionResponse(
        session_handle=session_handle,
        actor_id=principal.actor_id,
        role=principal.role,
        auth_label="P3 fixture local identity/session — not production authentication",
    )


@router.get("/fixtures/p3/context", response_model=FixtureContextResponse)
def fixture_context(request: Request, session: DBSession) -> FixtureContextResponse:
    require_principal(request)
    seed_p3_fixture(session)
    mapping_item_codes = list(
        session.scalars(
            select(StandardTestItem.code)
            .join(SpecItem, SpecItem.standard_test_item_id == StandardTestItem.id)
            .where(SpecItem.spec_version_id == SPEC_VERSION_ID)
            .order_by(StandardTestItem.code)
        )
    )
    return FixtureContextResponse(
        supplier_id=SUPPLIER_ID,
        material_id=MATERIAL_ID,
        model_id=MODEL_ID,
        spec_version_id=SPEC_VERSION_ID,
        supplier_name="P3 합성 공급사",
        material_name="염화칼슘 비드 (합성 fixture)",
        mapping_item_codes=mapping_item_codes,
    )


@router.post("/intakes", response_model=IntakeResponse, status_code=status.HTTP_201_CREATED)
def intake(
    request: Request,
    body: IntakeRequest,
    session: DBSession,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> IntakeResponse:
    principal = require_principal(request)
    require_role(principal, "INSPECTOR")
    result = create_intake(
        session,
        request=body,
        principal=principal,
        idempotency_key=require_idempotency_key(idempotency_key),
    )
    return IntakeResponse.model_validate(result)
