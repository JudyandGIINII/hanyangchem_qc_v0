"""P6-5 master import: preview, apply, revert.

Applying goes through the same master rows the API already writes, so the
duplicate-code and optimistic-lock rules the database enforces are not bypassed
by importing.  There is deliberately no path that applies without a preview
having been recorded first: `apply_master_import` only accepts a batch already
in PREVIEWED state, so a caller cannot skip the human confirmation step.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import Principal
from hyc_api.master_import import (
    ImportPlan,
    MasterImportEntity,
    build_master_import_plan,
)
from hyc_data.models import (
    MasterImportBatch,
    MasterImportRow,
    Material,
    MaterialModel,
    Supplier,
)

_ENTITY_MODELS: dict[str, type[Material] | type[Supplier] | type[MaterialModel]] = {
    "MATERIAL": Material,
    "SUPPLIER": Supplier,
    "MATERIAL_MODEL": MaterialModel,
}
_CODE_COLUMN = {
    "MATERIAL": "material_code",
    "SUPPLIER": "supplier_code",
    "MATERIAL_MODEL": "model_code",
}


def _model_for(entity: str) -> Any:
    model = _ENTITY_MODELS.get(entity)
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported master import entity")
    return model


def _batch_payload(batch: MasterImportBatch, rows: list[MasterImportRow]) -> dict[str, Any]:
    return {
        "batch_id": str(batch.id),
        "entity": batch.entity,
        "state": batch.state,
        "source_filename": batch.source_filename,
        "source_digest": batch.source_digest,
        "rows": [
            {
                "row_number": row.row_number,
                "action": row.action,
                "code": row.code,
                "name": row.name,
                "errors": list(row.errors),
            }
            for row in rows
        ],
    }


def _rows_of(session: Session, batch: MasterImportBatch) -> list[MasterImportRow]:
    return list(
        session.scalars(
            select(MasterImportRow)
            .where(MasterImportRow.batch_id == batch.id)
            .order_by(MasterImportRow.row_number)
        )
    )


def preview_master_import(
    session: Session,
    *,
    workbook_bytes: bytes,
    entity: MasterImportEntity,
    source_filename: str,
    principal: Principal,
) -> dict[str, Any]:
    plan: ImportPlan = build_master_import_plan(workbook_bytes, entity)
    batch = MasterImportBatch(
        entity=entity,
        source_filename=source_filename,
        source_digest=hashlib.sha256(workbook_bytes).hexdigest(),
        state="PREVIEWED",
        requested_by_id=principal.actor_id,
        actor_role=principal.role,
    )
    session.add(batch)
    session.flush()
    for row in plan.rows:
        session.add(
            MasterImportRow(
                batch_id=batch.id,
                row_number=row.row_number,
                action=row.action,
                code=row.code or None,
                name=row.name or None,
                errors=list(row.errors),
            )
        )
    session.flush()
    return _batch_payload(batch, _rows_of(session, batch))


def apply_master_import(
    session: Session, *, batch_id: UUID, principal: Principal
) -> dict[str, Any]:
    batch = session.scalar(
        select(MasterImportBatch).where(MasterImportBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Master import batch not found")
    if batch.state != "PREVIEWED":
        # Re-applying, or applying a reverted batch, would double-write rows.
        raise HTTPException(status_code=409, detail="Batch is not in PREVIEWED state")

    rows = _rows_of(session, batch)
    if any(row.action == "REJECT" for row in rows):
        # Partial application would leave the master half-updated with no record
        # of which half, so a file containing any rejected row applies nothing.
        raise HTTPException(status_code=409, detail="Batch contains rejected rows")

    model = _model_for(batch.entity)
    code_column = _CODE_COLUMN[batch.entity]
    for row in rows:
        if row.action == "CREATE":
            created = model(name=row.name or "")
            setattr(created, code_column, row.code)
            session.add(created)
            session.flush()
            row.target_id = created.id
        elif row.action == "UPDATE" and row.code is not None:
            existing = session.scalar(
                select(model)
                .where(getattr(model, code_column) == row.code, model.deleted_at.is_(None))
                .with_for_update()
            )
            if existing is None:
                raise HTTPException(status_code=409, detail="Target row disappeared")
            existing.name = row.name or existing.name
            row.target_id = existing.id
    batch.state = "APPLIED"
    session.flush()
    return _batch_payload(batch, _rows_of(session, batch))


def revert_master_import(
    session: Session, *, batch_id: UUID, principal: Principal
) -> dict[str, Any]:
    batch = session.scalar(
        select(MasterImportBatch).where(MasterImportBatch.id == batch_id).with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Master import batch not found")
    if batch.state != "APPLIED":
        raise HTTPException(status_code=409, detail="Batch is not in APPLIED state")

    model = _model_for(batch.entity)
    for row in _rows_of(session, batch):
        if row.action != "CREATE" or row.target_id is None:
            # Only creations are undone. An UPDATE's prior value is not recorded
            # here, so silently restoring a guessed value would be worse than
            # leaving it and saying so.
            continue
        created = session.scalar(select(model).where(model.id == row.target_id))
        if created is not None and created.deleted_at is None:
            created.deleted_at = datetime.now(UTC)
    batch.state = "REVERTED"
    batch.reverted_at = datetime.now(UTC)
    session.flush()
    return _batch_payload(batch, _rows_of(session, batch))
