from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from hyc_api.auth import require_principal
from hyc_api.contracts import (
    MaterialCreateRequest,
    MaterialModelCreateRequest,
    MaterialModelResponse,
    MaterialModelUpdateRequest,
    MaterialResponse,
    MaterialUpdateRequest,
    SupplierCreateRequest,
    SupplierResponse,
    SupplierUpdateRequest,
)
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import require_if_match
from hyc_data.models import Material, MaterialModel, Supplier

router = APIRouter(prefix="/api/v1", tags=["p5-masters"])
DBSession = Annotated[Session, Depends(database_session)]


def _supplier(session: Session, supplier_id: UUID, *, lock: bool = False) -> Supplier:
    statement = select(Supplier).where(Supplier.id == supplier_id, Supplier.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    supplier = session.scalar(statement)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


def _material(session: Session, material_id: UUID, *, lock: bool = False) -> Material:
    statement = select(Material).where(Material.id == material_id, Material.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    material = session.scalar(statement)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


def _material_model(session: Session, model_id: UUID, *, lock: bool = False) -> MaterialModel:
    statement = select(MaterialModel).where(
        MaterialModel.id == model_id, MaterialModel.deleted_at.is_(None)
    )
    if lock:
        statement = statement.with_for_update()
    model = session.scalar(statement)
    if model is None:
        raise HTTPException(status_code=404, detail="Material model not found")
    return model


def _commit(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Stale master-data version") from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Master-data code conflicts with existing record"
        ) from error


def _require_current_version(current_version: int, if_match: str | None) -> None:
    if current_version != require_if_match(if_match):
        raise HTTPException(status_code=409, detail="Stale master-data version")


def _supplier_response(value: Supplier) -> SupplierResponse:
    return SupplierResponse(
        id=value.id,
        supplier_code=value.supplier_code,
        name=value.name,
        active=value.active,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _material_response(value: Material) -> MaterialResponse:
    return MaterialResponse(
        id=value.id,
        material_code=value.material_code,
        name=value.name,
        default_unit=value.default_unit,
        active=value.active,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _model_response(value: MaterialModel) -> MaterialModelResponse:
    return MaterialModelResponse(
        id=value.id,
        material_id=value.material_id,
        model_code=value.model_code,
        name=value.name,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


@router.get("/suppliers", response_model=list[SupplierResponse])
def list_suppliers(request: Request, session: DBSession) -> list[SupplierResponse]:
    require_principal(request)
    return [
        _supplier_response(value)
        for value in session.scalars(
            select(Supplier)
            .where(Supplier.deleted_at.is_(None))
            .order_by(Supplier.name, Supplier.id)
        )
    ]


@router.post("/suppliers", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
def create_supplier(
    request: Request, body: SupplierCreateRequest, session: DBSession
) -> SupplierResponse:
    require_principal(request)
    supplier = Supplier(**body.model_dump())
    session.add(supplier)
    _commit(session)
    session.refresh(supplier)
    return _supplier_response(supplier)


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier(request: Request, supplier_id: UUID, session: DBSession) -> SupplierResponse:
    require_principal(request)
    return _supplier_response(_supplier(session, supplier_id))


@router.put("/suppliers/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    request: Request,
    supplier_id: UUID,
    body: SupplierUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SupplierResponse:
    require_principal(request)
    supplier = _supplier(session, supplier_id, lock=True)
    _require_current_version(supplier.lock_version, if_match)
    supplier.supplier_code = body.supplier_code
    supplier.name = body.name
    supplier.active = body.active
    _commit(session)
    session.refresh(supplier)
    return _supplier_response(supplier)


@router.get("/materials", response_model=list[MaterialResponse])
def list_materials(request: Request, session: DBSession) -> list[MaterialResponse]:
    require_principal(request)
    return [
        _material_response(value)
        for value in session.scalars(
            select(Material)
            .where(Material.deleted_at.is_(None))
            .order_by(Material.name, Material.id)
        )
    ]


@router.post("/materials", response_model=MaterialResponse, status_code=status.HTTP_201_CREATED)
def create_material(
    request: Request, body: MaterialCreateRequest, session: DBSession
) -> MaterialResponse:
    require_principal(request)
    material = Material(**body.model_dump())
    session.add(material)
    _commit(session)
    session.refresh(material)
    return _material_response(material)


@router.get("/materials/{material_id}", response_model=MaterialResponse)
def get_material(request: Request, material_id: UUID, session: DBSession) -> MaterialResponse:
    require_principal(request)
    return _material_response(_material(session, material_id))


@router.put("/materials/{material_id}", response_model=MaterialResponse)
def update_material(
    request: Request,
    material_id: UUID,
    body: MaterialUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> MaterialResponse:
    require_principal(request)
    material = _material(session, material_id, lock=True)
    _require_current_version(material.lock_version, if_match)
    material.material_code = body.material_code
    material.name = body.name
    material.default_unit = body.default_unit
    material.active = body.active
    _commit(session)
    session.refresh(material)
    return _material_response(material)


@router.get("/material-models", response_model=list[MaterialModelResponse])
def list_material_models(request: Request, session: DBSession) -> list[MaterialModelResponse]:
    require_principal(request)
    return [
        _model_response(value)
        for value in session.scalars(
            select(MaterialModel)
            .where(MaterialModel.deleted_at.is_(None))
            .order_by(MaterialModel.name, MaterialModel.id)
        )
    ]


@router.post(
    "/material-models", response_model=MaterialModelResponse, status_code=status.HTTP_201_CREATED
)
def create_material_model(
    request: Request, body: MaterialModelCreateRequest, session: DBSession
) -> MaterialModelResponse:
    require_principal(request)
    _material(session, body.material_id)
    model = MaterialModel(**body.model_dump())
    session.add(model)
    _commit(session)
    session.refresh(model)
    return _model_response(model)


@router.get("/material-models/{model_id}", response_model=MaterialModelResponse)
def get_material_model(
    request: Request, model_id: UUID, session: DBSession
) -> MaterialModelResponse:
    require_principal(request)
    return _model_response(_material_model(session, model_id))


@router.put("/material-models/{model_id}", response_model=MaterialModelResponse)
def update_material_model(
    request: Request,
    model_id: UUID,
    body: MaterialModelUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> MaterialModelResponse:
    require_principal(request)
    model = _material_model(session, model_id, lock=True)
    _require_current_version(model.lock_version, if_match)
    _material(session, body.material_id)
    model.material_id = body.material_id
    model.model_code = body.model_code
    model.name = body.name
    _commit(session)
    session.refresh(model)
    return _model_response(model)
