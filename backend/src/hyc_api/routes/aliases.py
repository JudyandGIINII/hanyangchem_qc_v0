from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.sql.elements import ColumnElement

from hyc_api.auth import require_principal
from hyc_api.contracts import (
    StandardTestItemAliasCreateRequest,
    StandardTestItemAliasResponse,
    StandardTestItemAliasUpdateRequest,
)
from hyc_api.db_errors import _is_domain_invariant_violation
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import require_if_match
from hyc_data.models import (
    Material,
    MaterialModel,
    StandardTestItem,
    StandardTestItemAlias,
    Supplier,
)

router = APIRouter(prefix="/api/v1", tags=["p5-aliases"])
DBSession = Annotated[Session, Depends(database_session)]


def _alias(session: Session, alias_id: UUID, *, lock: bool = False) -> StandardTestItemAlias:
    statement = select(StandardTestItemAlias).where(
        StandardTestItemAlias.id == alias_id,
        StandardTestItemAlias.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Standard test item alias not found")
    return value


def _standard_item(session: Session, item_id: UUID, *, lock: bool) -> StandardTestItem:
    statement = select(StandardTestItem).where(
        StandardTestItem.id == item_id,
        StandardTestItem.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Standard test item not found")
    return value


def _supplier(session: Session, supplier_id: UUID, *, lock: bool) -> Supplier:
    statement = select(Supplier).where(Supplier.id == supplier_id, Supplier.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return value


def _material(session: Session, material_id: UUID, *, lock: bool) -> Material:
    statement = select(Material).where(Material.id == material_id, Material.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return value


def _model(session: Session, model_id: UUID, *, lock: bool) -> MaterialModel:
    statement = select(MaterialModel).where(
        MaterialModel.id == model_id,
        MaterialModel.deleted_at.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    value = session.scalar(statement)
    if value is None:
        raise HTTPException(status_code=404, detail="Material model not found")
    return value


def _validate_references(
    session: Session,
    body: StandardTestItemAliasCreateRequest,
    *,
    lock: bool,
) -> None:
    _standard_item(session, body.standard_test_item_id, lock=lock)
    if body.supplier_id is not None:
        _supplier(session, body.supplier_id, lock=lock)
    if body.material_id is not None:
        _material(session, body.material_id, lock=lock)
    if body.model_id is not None:
        _model(session, body.model_id, lock=lock)


def _commit(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Stale alias version") from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Alias conflicts with existing scope"
        ) from error
    except DBAPIError as error:
        session.rollback()
        if not _is_domain_invariant_violation(error):
            raise
        raise HTTPException(
            status_code=409, detail="Alias conflicts with existing scope"
        ) from error


def _require_current_version(current_version: int, if_match: str | None) -> None:
    if current_version != require_if_match(if_match):
        raise HTTPException(status_code=409, detail="Stale alias version")


def _response(value: StandardTestItemAlias) -> StandardTestItemAliasResponse:
    return StandardTestItemAliasResponse(
        id=value.id,
        standard_test_item_id=value.standard_test_item_id,
        alias_text=value.alias_text,
        supplier_id=value.supplier_id,
        material_id=value.material_id,
        model_id=value.model_id,
        priority=value.priority,
        active=value.active,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _scope_match(column: Any, value: UUID | None) -> ColumnElement[bool]:
    return column.is_(None) if value is None else or_(column.is_(None), column == value)


@router.get("/standard-test-item-aliases", response_model=list[StandardTestItemAliasResponse])
def list_aliases(request: Request, session: DBSession) -> list[StandardTestItemAliasResponse]:
    require_principal(request)
    return [
        _response(value)
        for value in session.scalars(
            select(StandardTestItemAlias)
            .where(StandardTestItemAlias.deleted_at.is_(None))
            .order_by(
                StandardTestItemAlias.priority,
                StandardTestItemAlias.alias_text,
                StandardTestItemAlias.id,
            )
        )
    ]


@router.get(
    "/standard-test-item-aliases/lookup",
    response_model=list[StandardTestItemAliasResponse],
)
def lookup_aliases(
    request: Request,
    alias_text: str,
    session: DBSession,
    supplier_id: UUID | None = None,
    material_id: UUID | None = None,
    model_id: UUID | None = None,
) -> list[StandardTestItemAliasResponse]:
    require_principal(request)
    statement = (
        select(StandardTestItemAlias)
        .where(
            StandardTestItemAlias.alias_text == alias_text,
            StandardTestItemAlias.active.is_(True),
            StandardTestItemAlias.deleted_at.is_(None),
            and_(
                _scope_match(StandardTestItemAlias.supplier_id, supplier_id),
                _scope_match(StandardTestItemAlias.material_id, material_id),
                _scope_match(StandardTestItemAlias.model_id, model_id),
            ),
        )
        .order_by(
            StandardTestItemAlias.priority,
            StandardTestItemAlias.alias_text,
            StandardTestItemAlias.id,
        )
    )
    return [_response(value) for value in session.scalars(statement)]


@router.post(
    "/standard-test-item-aliases",
    response_model=StandardTestItemAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_alias(
    request: Request,
    body: StandardTestItemAliasCreateRequest,
    session: DBSession,
) -> StandardTestItemAliasResponse:
    require_principal(request)
    _validate_references(session, body, lock=True)
    value = StandardTestItemAlias(**body.model_dump())
    session.add(value)
    _commit(session)
    session.refresh(value)
    return _response(value)


@router.get(
    "/standard-test-item-aliases/{alias_id}",
    response_model=StandardTestItemAliasResponse,
)
def get_alias(
    request: Request, alias_id: UUID, session: DBSession
) -> StandardTestItemAliasResponse:
    require_principal(request)
    return _response(_alias(session, alias_id))


@router.put("/standard-test-item-aliases/{alias_id}", response_model=StandardTestItemAliasResponse)
def update_alias(
    request: Request,
    alias_id: UUID,
    body: StandardTestItemAliasUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> StandardTestItemAliasResponse:
    require_principal(request)
    value = _alias(session, alias_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    _validate_references(session, body, lock=True)
    for field, field_value in body.model_dump().items():
        setattr(value, field, field_value)
    _commit(session)
    session.refresh(value)
    return _response(value)


@router.delete("/standard-test-item-aliases/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_alias(
    request: Request,
    alias_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> Response:
    require_principal(request)
    value = _alias(session, alias_id, lock=True)
    _require_current_version(value.lock_version, if_match)
    value.deleted_at = datetime.now(UTC)
    _commit(session)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
