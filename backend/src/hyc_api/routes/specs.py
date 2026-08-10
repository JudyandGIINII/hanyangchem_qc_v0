from __future__ import annotations

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from hyc_api.auth import require_principal
from hyc_api.contracts import (
    SpecProfileCreateRequest,
    SpecProfileResponse,
    SpecProfileUpdateRequest,
    SpecVersionCreateRequest,
    SpecVersionResponse,
    SpecVersionUpdateRequest,
)
from hyc_api.dependencies import database_session
from hyc_api.services.p3 import require_if_match
from hyc_data.models import Material, MaterialModel, SpecProfile, SpecVersion, Supplier

router = APIRouter(prefix="/api/v1", tags=["p5-specs"])
DBSession = Annotated[Session, Depends(database_session)]


def _profile(session: Session, profile_id: UUID, *, lock: bool = False) -> SpecProfile:
    statement = select(SpecProfile).where(
        SpecProfile.id == profile_id, SpecProfile.deleted_at.is_(None)
    )
    if lock:
        statement = statement.with_for_update()
    profile = session.scalar(statement)
    if profile is None:
        raise HTTPException(status_code=404, detail="Spec profile not found")
    return profile


def _version(session: Session, version_id: UUID, *, lock: bool = False) -> SpecVersion:
    statement = (
        select(SpecVersion)
        .join(SpecProfile, SpecProfile.id == SpecVersion.spec_profile_id)
        .where(
            SpecVersion.id == version_id,
            SpecVersion.deleted_at.is_(None),
            SpecProfile.deleted_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update()
    version = session.scalar(statement)
    if version is None:
        raise HTTPException(status_code=404, detail="Spec version not found")
    return version


def _active_material(session: Session, material_id: UUID, *, lock: bool) -> Material:
    statement = select(Material).where(Material.id == material_id, Material.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    material = session.scalar(statement)
    if material is None:
        raise HTTPException(status_code=404, detail="Material not found")
    return material


def _active_supplier(session: Session, supplier_id: UUID, *, lock: bool) -> Supplier:
    statement = select(Supplier).where(Supplier.id == supplier_id, Supplier.deleted_at.is_(None))
    if lock:
        statement = statement.with_for_update()
    supplier = session.scalar(statement)
    if supplier is None:
        raise HTTPException(status_code=404, detail="Supplier not found")
    return supplier


def _active_model(session: Session, model_id: UUID, *, lock: bool) -> MaterialModel:
    statement = select(MaterialModel).where(
        MaterialModel.id == model_id, MaterialModel.deleted_at.is_(None)
    )
    if lock:
        statement = statement.with_for_update()
    model = session.scalar(statement)
    if model is None:
        raise HTTPException(status_code=404, detail="Material model not found")
    return model


def validate_profile_scope(
    session: Session,
    *,
    material_id: UUID,
    supplier_id: UUID | None,
    model_id: UUID | None,
    lock: bool,
) -> None:
    _active_material(session, material_id, lock=lock)
    if supplier_id is not None:
        _active_supplier(session, supplier_id, lock=lock)
    if model_id is not None:
        model = _active_model(session, model_id, lock=lock)
        if model.material_id != material_id:
            raise HTTPException(
                status_code=422, detail="Material model does not belong to material"
            )


def _commit(session: Session) -> None:
    try:
        session.commit()
    except StaleDataError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail="Stale spec version") from error
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(
            status_code=409, detail="Spec data conflicts with existing record"
        ) from error


def _require_current_version(current_version: int, if_match: str | None) -> None:
    if current_version != require_if_match(if_match):
        raise HTTPException(status_code=409, detail="Stale spec version")


def _profile_response(value: SpecProfile) -> SpecProfileResponse:
    return SpecProfileResponse(
        id=value.id,
        material_id=value.material_id,
        supplier_id=value.supplier_id,
        model_id=value.model_id,
        name=value.name,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def _version_response(value: SpecVersion) -> SpecVersionResponse:
    return SpecVersionResponse(
        id=value.id,
        spec_profile_id=value.spec_profile_id,
        version=value.version,
        status=cast(Literal["DRAFT", "ACTIVE", "RETIRED"], value.status),
        effective_from=value.effective_from,
        effective_to=value.effective_to,
        revision_reason=value.revision_reason,
        lock_version=value.lock_version,
        created_at=value.created_at,
        updated_at=value.updated_at,
    )


def activate_spec_version(
    session: Session, *, version_id: UUID, expected_version: int
) -> SpecVersion:
    version = _version(session, version_id, lock=True)
    _require_current_version(version.lock_version, str(expected_version))
    profile = _profile(session, version.spec_profile_id, lock=True)
    if version.status != "DRAFT":
        raise HTTPException(status_code=409, detail="Illegal spec version transition")
    active = session.scalar(
        select(SpecVersion)
        .where(
            SpecVersion.spec_profile_id == profile.id,
            SpecVersion.id != version.id,
            SpecVersion.status == "ACTIVE",
            SpecVersion.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Spec profile already has an active version")
    version.status = "ACTIVE"
    _commit(session)
    session.refresh(version)
    return version


def retire_spec_version(
    session: Session, *, version_id: UUID, expected_version: int
) -> SpecVersion:
    version = _version(session, version_id, lock=True)
    _require_current_version(version.lock_version, str(expected_version))
    _profile(session, version.spec_profile_id, lock=True)
    if version.status != "ACTIVE":
        raise HTTPException(status_code=409, detail="Illegal spec version transition")
    version.status = "RETIRED"
    _commit(session)
    session.refresh(version)
    return version


@router.get("/spec-profiles", response_model=list[SpecProfileResponse])
def list_profiles(request: Request, session: DBSession) -> list[SpecProfileResponse]:
    require_principal(request)
    return [
        _profile_response(value)
        for value in session.scalars(
            select(SpecProfile)
            .where(SpecProfile.deleted_at.is_(None))
            .order_by(SpecProfile.name, SpecProfile.id)
        )
    ]


@router.post(
    "/spec-profiles", response_model=SpecProfileResponse, status_code=status.HTTP_201_CREATED
)
def create_profile(
    request: Request, body: SpecProfileCreateRequest, session: DBSession
) -> SpecProfileResponse:
    require_principal(request)
    validate_profile_scope(
        session,
        material_id=body.material_id,
        supplier_id=body.supplier_id,
        model_id=body.model_id,
        lock=True,
    )
    profile = SpecProfile(**body.model_dump())
    session.add(profile)
    _commit(session)
    session.refresh(profile)
    return _profile_response(profile)


@router.get("/spec-profiles/{profile_id}", response_model=SpecProfileResponse)
def get_profile(request: Request, profile_id: UUID, session: DBSession) -> SpecProfileResponse:
    require_principal(request)
    return _profile_response(_profile(session, profile_id))


@router.put("/spec-profiles/{profile_id}", response_model=SpecProfileResponse)
def update_profile(
    request: Request,
    profile_id: UUID,
    body: SpecProfileUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SpecProfileResponse:
    require_principal(request)
    profile = _profile(session, profile_id, lock=True)
    _require_current_version(profile.lock_version, if_match)
    validate_profile_scope(
        session,
        material_id=body.material_id,
        supplier_id=body.supplier_id,
        model_id=body.model_id,
        lock=True,
    )
    profile.material_id = body.material_id
    profile.supplier_id = body.supplier_id
    profile.model_id = body.model_id
    profile.name = body.name
    _commit(session)
    session.refresh(profile)
    return _profile_response(profile)


@router.get("/spec-profiles/{profile_id}/versions", response_model=list[SpecVersionResponse])
def list_versions(
    request: Request, profile_id: UUID, session: DBSession
) -> list[SpecVersionResponse]:
    require_principal(request)
    _profile(session, profile_id)
    return [
        _version_response(value)
        for value in session.scalars(
            select(SpecVersion)
            .where(
                SpecVersion.spec_profile_id == profile_id,
                SpecVersion.deleted_at.is_(None),
            )
            .order_by(SpecVersion.version, SpecVersion.id)
        )
    ]


@router.post(
    "/spec-profiles/{profile_id}/versions",
    response_model=SpecVersionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    request: Request,
    profile_id: UUID,
    body: SpecVersionCreateRequest,
    session: DBSession,
) -> SpecVersionResponse:
    require_principal(request)
    _profile(session, profile_id, lock=True)
    version = SpecVersion(spec_profile_id=profile_id, status="DRAFT", **body.model_dump())
    session.add(version)
    _commit(session)
    session.refresh(version)
    return _version_response(version)


@router.get("/spec-versions/{version_id}", response_model=SpecVersionResponse)
def get_version(request: Request, version_id: UUID, session: DBSession) -> SpecVersionResponse:
    require_principal(request)
    return _version_response(_version(session, version_id))


@router.put("/spec-versions/{version_id}", response_model=SpecVersionResponse)
def update_version(
    request: Request,
    version_id: UUID,
    body: SpecVersionUpdateRequest,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SpecVersionResponse:
    require_principal(request)
    version = _version(session, version_id, lock=True)
    _require_current_version(version.lock_version, if_match)
    version.version = body.version
    version.effective_from = body.effective_from
    version.effective_to = body.effective_to
    version.revision_reason = body.revision_reason
    _commit(session)
    session.refresh(version)
    return _version_response(version)


@router.post("/spec-versions/{version_id}/activate", response_model=SpecVersionResponse)
def activate_version(
    request: Request,
    version_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SpecVersionResponse:
    require_principal(request)
    return _version_response(
        activate_spec_version(
            session, version_id=version_id, expected_version=require_if_match(if_match)
        )
    )


@router.post("/spec-versions/{version_id}/retire", response_model=SpecVersionResponse)
def retire_version(
    request: Request,
    version_id: UUID,
    session: DBSession,
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> SpecVersionResponse:
    require_principal(request)
    return _version_response(
        retire_spec_version(
            session, version_id=version_id, expected_version=require_if_match(if_match)
        )
    )
