from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hyc_api.auth import Principal
from hyc_api.contracts import (
    IntakeRequest,
    InternalResultsRequest,
    ReviewRequest,
    parse_canonical_decimal_string,
)
from hyc_data.models import (
    AuditLog,
    DocumentAllocationLink,
    DocumentSection,
    ExtractionFieldReview,
    ExtractionRun,
    IdempotencyKey,
    InboundReceipt,
    InspectionCase,
    InternalResult,
    MaterialLot,
    ReceiptLotAllocation,
    SampleMeasurement,
    SpecItem,
    SpecProfile,
    SpecVersion,
    StandardTestItem,
    SupplierResult,
)
from hyc_data.repositories import (
    ApprovalPrecondition,
    ApprovalRepository,
    AuthorizationDenied,
    OptimisticConflict,
)
from hyc_domain.idempotency import request_hash
from hyc_domain.judgment import EngineDecision, JudgmentEngine
from hyc_domain.lots import LotIdentity

_CONFIRM_REVIEW_CONFLICT_CONSTRAINTS = frozenset(
    {
        "uq_document_section_index",
        "uq_document_allocation_link",
        "uq_document_section_one_confirmed_allocation",
        "uq_document_one_confirmed_extraction_run",
    }
)
_IDEMPOTENCY_RESERVATION_CONSTRAINT = "uq_idempotency_principal_scope_key"


def _canonical_finite_decimal(raw: object) -> Decimal | None:
    try:
        value = parse_canonical_decimal_string(raw)
    except ValueError:
        return None
    if not isinstance(raw, str):
        return None
    integer_part, _, fractional_part = raw.removeprefix("-").partition(".")
    if len(integer_part) > 12 or len(fractional_part) > 12:
        return None
    return value


def require_if_match(raw: str | None) -> int:
    if raw is None:
        raise HTTPException(status_code=422, detail="If-Match is required")
    version_text = raw.strip().strip('"')
    if not version_text.isdigit() or int(version_text) < 1:
        raise HTTPException(status_code=422, detail="If-Match must be a positive version")
    return int(version_text)


def require_idempotency_key(raw: str | None) -> str:
    if raw is None or not raw.strip() or len(raw) > 256:
        raise HTTPException(status_code=422, detail="Idempotency-Key is required")
    return raw.strip()


def reserve_idempotency(
    session: Session,
    *,
    principal: Principal,
    scope: str,
    key: str,
    payload: dict[str, Any],
) -> tuple[IdempotencyKey, dict[str, Any] | None]:
    digest = request_hash(payload)
    record = session.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.principal_id == str(principal.actor_id),
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == key,
        )
        .with_for_update()
    )
    if record is not None:
        if record.request_hash != digest:
            raise HTTPException(status_code=409, detail="Idempotency key request conflict")
        if record.state == "COMPLETED" and record.response_body is not None:
            body = json.loads(record.response_body)
            if not isinstance(body, dict):
                raise RuntimeError("stored idempotency response is invalid")
            return record, body
        raise HTTPException(status_code=409, detail="Idempotency request is already pending")
    record = IdempotencyKey(
        principal_id=str(principal.actor_id),
        scope=scope,
        key=key,
        request_hash=digest,
        state="PENDING",
        lease_expires_at=datetime.now(UTC) + timedelta(minutes=5),
        lease_owner="p3-api",
    )
    try:
        with session.begin_nested():
            session.add(record)
            session.flush()
    except IntegrityError as error:
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        if getattr(diagnostic, "constraint_name", None) != (_IDEMPOTENCY_RESERVATION_CONSTRAINT):
            raise
        concurrent = session.scalar(
            select(IdempotencyKey)
            .where(
                IdempotencyKey.principal_id == str(principal.actor_id),
                IdempotencyKey.scope == scope,
                IdempotencyKey.key == key,
            )
            .with_for_update()
        )
        if concurrent is None:
            raise
        if concurrent.request_hash != digest:
            raise HTTPException(
                status_code=409, detail="Idempotency key request conflict"
            ) from error
        raise HTTPException(
            status_code=409, detail="Idempotency request is already pending"
        ) from error
    return record, None


def replay_idempotency_if_present(
    session: Session,
    *,
    principal: Principal,
    scope: str,
    key: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    digest = request_hash(payload)
    record = session.scalar(
        select(IdempotencyKey)
        .where(
            IdempotencyKey.principal_id == str(principal.actor_id),
            IdempotencyKey.scope == scope,
            IdempotencyKey.key == key,
        )
        .with_for_update()
    )
    if record is None:
        return None
    if record.request_hash != digest:
        raise HTTPException(status_code=409, detail="Idempotency key request conflict")
    if record.state == "COMPLETED" and record.response_body is not None:
        body = json.loads(record.response_body)
        if not isinstance(body, dict):
            raise RuntimeError("stored idempotency response is invalid")
        return body
    raise HTTPException(status_code=409, detail="Idempotency request is already pending")


def complete_idempotency(
    record: IdempotencyKey, *, status: int, body: dict[str, Any], resource_ref: str
) -> None:
    record.state = "COMPLETED"
    record.lease_expires_at = None
    record.lease_owner = None
    record.response_status = status
    record.response_body = json.dumps(body, separators=(",", ":"))
    record.resource_ref = resource_ref


def create_intake(
    session: Session,
    *,
    request: IntakeRequest,
    principal: Principal,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    record, replay = reserve_idempotency(
        session, principal=principal, scope="p3.intakes", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return replay
    identity_key, identity_status = LotIdentity(
        policy_version="v1",
        supplier_lot_no=request.supplier_lot_no,
        production_date=None,
        package_mark=None,
    ).key_and_status()
    lot = session.scalar(
        select(MaterialLot).where(
            MaterialLot.supplier_id == request.supplier_id,
            MaterialLot.material_id == request.material_id,
            MaterialLot.identity_policy_version == "v1",
            MaterialLot.identity_key == identity_key,
        )
    )
    if lot is None:
        lot = MaterialLot(
            supplier_id=request.supplier_id,
            material_id=request.material_id,
            identity_policy_version="v1",
            identity_key=identity_key,
            supplier_lot_no_raw=request.supplier_lot_no,
            identity_status=identity_status.value,
        )
        session.add(lot)
        session.flush()
    receipt = session.scalar(
        select(InboundReceipt).where(InboundReceipt.inbound_no == request.inbound_no)
    )
    if receipt is None:
        receipt = InboundReceipt(
            inbound_no=request.inbound_no,
            supplier_id=request.supplier_id,
            receipt_date=request.receipt_date,
            status="RECEIVED",
        )
        session.add(receipt)
        session.flush()
    elif receipt.supplier_id != request.supplier_id or receipt.receipt_date != request.receipt_date:
        raise HTTPException(
            status_code=409, detail="Inbound number conflicts with existing receipt"
        )
    allocation = session.scalar(
        select(ReceiptLotAllocation).where(
            ReceiptLotAllocation.inbound_receipt_id == receipt.id,
            ReceiptLotAllocation.material_lot_id == lot.id,
        )
    )
    if allocation is None:
        allocation = ReceiptLotAllocation(
            inbound_receipt_id=receipt.id,
            material_lot_id=lot.id,
            model_id=request.model_id,
            quantity=request.quantity,
            quantity_unit=request.quantity_unit,
        )
        session.add(allocation)
        session.flush()
    session.add(
        AuditLog(
            entity_type="inbound_receipt",
            entity_id=receipt.id,
            action="P3_INTAKE_CREATED",
            payload={"material_lot_id": str(lot.id), "allocation_id": str(allocation.id)},
        )
    )
    body = {
        "material_lot_id": str(lot.id),
        "inbound_receipt_id": str(receipt.id),
        "allocation_id": str(allocation.id),
        "version": allocation.lock_version,
    }
    complete_idempotency(record, status=201, body=body, resource_ref=str(receipt.id))
    session.commit()
    return body


def confirm_review(
    session: Session,
    *,
    document_id: UUID,
    run_id: UUID,
    request: ReviewRequest,
    expected_version: int,
    principal: Principal,
) -> ExtractionRun:
    document_runs = list(
        session.scalars(
            select(ExtractionRun)
            .where(ExtractionRun.document_id == document_id)
            .order_by(ExtractionRun.id)
            .with_for_update()
        )
    )
    run = next((item for item in document_runs if item.id == run_id), None)
    if run is None:
        raise HTTPException(status_code=404, detail="Extraction run not found")
    if run.status != "REVIEW_REQUIRED":
        raise HTTPException(status_code=409, detail="Extraction review is already confirmed")
    if run.lock_version != expected_version:
        raise HTTPException(status_code=409, detail="Stale extraction review version")
    field_rows = list(
        session.scalars(
            select(ExtractionFieldReview)
            .where(ExtractionFieldReview.extraction_run_id == run.id)
            .with_for_update()
        )
    )
    fields = {field.field_key: field for field in field_rows}
    if len(fields) != len(field_rows):
        raise HTTPException(status_code=422, detail="Duplicate extraction fields")
    submitted = {item.field_key: item for item in request.fields}
    if len(submitted) != len(request.fields) or set(fields) != set(submitted):
        raise HTTPException(
            status_code=422, detail="Every extraction field must be explicitly reviewed"
        )
    allocation = session.get(ReceiptLotAllocation, request.allocation_id, with_for_update=True)
    if allocation is None:
        raise HTTPException(status_code=404, detail="Allocation not found")

    local_ocr = run.provider_name == "local-paddleocr"
    fixture_numeric_field_keys: set[str] = set()
    payload_fields = run.candidate_payload.get("fields", [])
    metadata_by_id: dict[str, dict[str, Any]] = {}
    if local_ocr:
        if not isinstance(payload_fields, list):
            raise HTTPException(status_code=422, detail="Extraction source identity is invalid")
        for metadata in payload_fields:
            if not isinstance(metadata, dict) or not isinstance(metadata.get("field_id"), str):
                raise HTTPException(status_code=422, detail="Extraction source identity is invalid")
            field_id = metadata["field_id"]
            if field_id in metadata_by_id:
                raise HTTPException(status_code=422, detail="Duplicate extraction source ids")
            metadata_by_id[field_id] = metadata
        expected_ids = {str(field.id) for field in field_rows}
        if set(metadata_by_id) != expected_ids:
            raise HTTPException(status_code=422, detail="Extraction source identity is invalid")
        submitted_ids = [str(item.field_id) for item in request.fields if item.field_id]
        if len(submitted_ids) != len(request.fields) or len(submitted_ids) != len(
            set(submitted_ids)
        ):
            raise HTTPException(status_code=422, detail="Unknown or stale source field ids")
        if set(submitted_ids) != expected_ids:
            raise HTTPException(status_code=422, detail="Unknown or stale source field ids")

        version, _profile = _select_spec(session, allocation)
        if request.spec_version_id is None or request.spec_version_id != version.id:
            raise HTTPException(status_code=422, detail="Selected specification is stale")
        allowed_targets = set(
            session.scalars(
                select(StandardTestItem.code)
                .join(SpecItem, SpecItem.standard_test_item_id == StandardTestItem.id)
                .where(SpecItem.spec_version_id == version.id)
            )
        )
        fields_by_id = {field.id: field for field in field_rows}
        mapped_targets: list[str] = []
        for item in request.fields:
            if item.field_id is None or item.field_id not in fields_by_id:
                raise HTTPException(status_code=422, detail="Unknown or stale source field ids")
            field = fields_by_id[item.field_id]
            metadata = metadata_by_id[str(field.id)]
            if metadata.get("source_field_key") != item.field_key:
                raise HTTPException(status_code=422, detail="Unknown or stale source field ids")
            if item.mapping_disposition not in {"MAP", "UNMAPPED"}:
                raise HTTPException(status_code=422, detail="Explicit MAP or UNMAPPED is required")
            if item.mapping_disposition == "UNMAPPED":
                if item.mapped_field_key is not None:
                    raise HTTPException(status_code=422, detail="UNMAPPED forbids a target code")
                continue
            if item.mapped_field_key is None or item.mapped_field_key not in allowed_targets:
                raise HTTPException(
                    status_code=422, detail="Mapped target is outside the current spec"
                )
            if _canonical_finite_decimal(item.final_text) is None:
                raise HTTPException(
                    status_code=422, detail="Mapped value must be a canonical finite decimal string"
                )
            mapped_targets.append(item.mapped_field_key)
        if len(mapped_targets) != len(set(mapped_targets)):
            raise HTTPException(status_code=422, detail="Duplicate mapped target codes")
    else:
        version, _profile = _select_spec(session, allocation)
        if request.spec_version_id is not None and request.spec_version_id != version.id:
            raise HTTPException(status_code=422, detail="Selected specification is stale")
        fixture_numeric_field_keys = set(
            session.scalars(
                select(StandardTestItem.code)
                .join(SpecItem, SpecItem.standard_test_item_id == StandardTestItem.id)
                .where(SpecItem.spec_version_id == version.id)
            )
        )

    for key in fields:
        item = submitted[key]
        if item.source == "MANUAL" and not item.manual_text:
            raise HTTPException(status_code=422, detail="Manual source requires manual text")
        if item.logic_conflict:
            raise HTTPException(
                status_code=422, detail="Logic conflicts remain visible and unresolved"
            )
        if not local_ocr and key in fixture_numeric_field_keys:
            if _canonical_finite_decimal(item.final_text) is None:
                raise HTTPException(
                    status_code=422,
                    detail="Supplier result must fit NUMERIC(24,12)",
                )

    section = session.scalar(
        select(DocumentSection).where(DocumentSection.document_id == document_id).with_for_update()
    )
    confirmed_links = (
        list(
            session.scalars(
                select(DocumentAllocationLink)
                .where(
                    DocumentAllocationLink.document_section_id == section.id,
                    DocumentAllocationLink.match_status == "CONFIRMED",
                )
                .with_for_update()
            )
        )
        if section is not None
        else []
    )
    if len(confirmed_links) > 1 or (
        confirmed_links and confirmed_links[0].receipt_lot_allocation_id != allocation.id
    ):
        raise HTTPException(
            status_code=409,
            detail="Document section already has a confirmed allocation",
        )
    try:
        mapped_codes: list[str] = []
        unmapped_count = 0
        reviewed_payload_fields: list[dict[str, Any]] = []
        for key, field in fields.items():
            item = submitted[key]
            field.manual_text = item.manual_text
            field.final_text = item.final_text
            field.source = item.source
            field.reason = item.reason
            field.logic_conflict = False
            field.status = "CONFIRMED"
            if local_ocr:
                metadata = dict(metadata_by_id[str(field.id)])
                metadata["mapping_disposition"] = item.mapping_disposition
                metadata["mapped_field_key"] = item.mapped_field_key
                reviewed_payload_fields.append(metadata)
                if item.mapping_disposition == "MAP":
                    if item.mapped_field_key is None:
                        raise HTTPException(
                            status_code=422, detail="Mapped field is missing its target code"
                        )
                    field.field_key = item.mapped_field_key
                    mapped_codes.append(item.mapped_field_key)
                else:
                    unmapped_count += 1
        session.flush()
        if section is None:
            section = DocumentSection(
                document_id=document_id,
                section_index=1,
                page_from=1,
                page_to=1,
                status="MATCHED",
            )
            session.add(section)
            session.flush()
        if not confirmed_links:
            session.add(
                DocumentAllocationLink(
                    document_section_id=section.id,
                    receipt_lot_allocation_id=allocation.id,
                    match_status="CONFIRMED",
                )
            )
            session.flush()
        run.status = "CONFIRMED"
        run.conflicts = []
        if local_ocr:
            run.candidate_payload = run.candidate_payload | {
                "fields": reviewed_payload_fields,
                "review": {
                    "spec_version_id": str(request.spec_version_id),
                    "mapped_count": len(mapped_codes),
                    "unmapped_count": unmapped_count,
                    "target_codes": sorted(mapped_codes),
                },
            }
        session.add(
            AuditLog(
                entity_type="extraction_run",
                entity_id=run.id,
                action="P3_EXTRACTION_REVIEW_CONFIRMED",
                payload={
                    "allocation_id": str(allocation.id),
                    "field_count": len(fields),
                    "mapped_count": len(mapped_codes),
                    "unmapped_count": unmapped_count,
                    "target_codes": sorted(mapped_codes),
                },
            )
        )
        session.commit()
    except IntegrityError as error:
        session.rollback()
        diagnostic = getattr(getattr(error, "orig", None), "diag", None)
        if getattr(diagnostic, "constraint_name", None) in (_CONFIRM_REVIEW_CONFLICT_CONSTRAINTS):
            raise HTTPException(
                status_code=409,
                detail="Document section already has a confirmed allocation",
            ) from error
        raise
    session.refresh(run)
    return run


def _select_spec(
    session: Session, allocation: ReceiptLotAllocation
) -> tuple[SpecVersion, SpecProfile]:
    receipt = session.get(InboundReceipt, allocation.inbound_receipt_id)
    lot = session.get(MaterialLot, allocation.material_lot_id)
    if receipt is None or lot is None:
        raise HTTPException(status_code=404, detail="Allocation context is incomplete")
    rows = list(
        session.execute(
            select(SpecVersion, SpecProfile)
            .join(SpecProfile, SpecProfile.id == SpecVersion.spec_profile_id)
            .where(
                SpecVersion.status == "ACTIVE",
                SpecVersion.effective_from <= receipt.receipt_date,
                (SpecVersion.effective_to.is_(None))
                | (SpecVersion.effective_to >= receipt.receipt_date),
                SpecProfile.material_id == lot.material_id,
                (SpecProfile.supplier_id.is_(None)) | (SpecProfile.supplier_id == lot.supplier_id),
                (SpecProfile.model_id.is_(None)) | (SpecProfile.model_id == allocation.model_id),
            )
        )
    )
    rows.sort(
        key=lambda row: (
            int(row[1].supplier_id is not None) + int(row[1].model_id is not None),
            row[0].version,
        ),
        reverse=True,
    )
    if not rows:
        raise HTTPException(status_code=422, detail="No effective specification")
    top = int(rows[0][1].supplier_id is not None) + int(rows[0][1].model_id is not None)
    if (
        len(rows) > 1
        and int(rows[1][1].supplier_id is not None) + int(rows[1][1].model_id is not None) == top
    ):
        raise HTTPException(status_code=422, detail="Ambiguous effective specification")
    selected = rows[0]
    return selected[0], selected[1]


def _spec_snapshot(session: Session, version: SpecVersion, profile: SpecProfile) -> dict[str, Any]:
    items = list(
        session.scalars(
            select(SpecItem).where(SpecItem.spec_version_id == version.id).order_by(SpecItem.id)
        )
    )
    if not items:
        raise HTTPException(status_code=422, detail="Effective specification has no items")
    return {
        "spec_version_id": str(version.id),
        "semantic_version": version.version,
        "profile": {
            "id": str(profile.id),
            "material_id": str(profile.material_id),
            "supplier_id": str(profile.supplier_id),
            "model_id": str(profile.model_id),
        },
        "effective_from": version.effective_from.isoformat(),
        "effective_to": version.effective_to.isoformat() if version.effective_to else None,
        "items": [
            {
                "id": str(item.id),
                "standard_test_item_id": str(item.standard_test_item_id),
                "required": item.required,
                "source_policy": item.source_policy,
                "missing_policy": item.missing_policy,
                "operator": item.operator,
                "lower": format(item.lower_value, "f") if item.lower_value is not None else None,
                "upper": format(item.upper_value, "f") if item.upper_value is not None else None,
                "target": format(item.target_value, "f") if item.target_value is not None else None,
                "tolerance": format(item.tolerance, "f") if item.tolerance is not None else None,
                "allowed": item.allowed_values,
                "unit": item.unit,
                "precision": item.precision,
                "sample_policy": item.sample_policy,
            }
            for item in items
        ],
    }


def create_inspection(
    session: Session,
    *,
    allocation_id: UUID,
    extraction_run_id: UUID,
    principal: Principal,
    idempotency_key: str,
) -> dict[str, Any]:
    payload = {"allocation_id": str(allocation_id), "extraction_run_id": str(extraction_run_id)}
    replay = replay_idempotency_if_present(
        session,
        principal=principal,
        scope="p3.inspections",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return replay
    allocation = session.get(ReceiptLotAllocation, allocation_id)
    run = session.get(ExtractionRun, extraction_run_id)
    if allocation is None or run is None or run.status != "CONFIRMED":
        raise HTTPException(
            status_code=422, detail="Confirmed extraction and allocation are required"
        )
    record, replay = reserve_idempotency(
        session, principal=principal, scope="p3.inspections", key=idempotency_key, payload=payload
    )
    if replay is not None:
        return replay
    linked_allocation_id = session.scalar(
        select(DocumentAllocationLink.receipt_lot_allocation_id)
        .join(
            DocumentSection,
            DocumentSection.id == DocumentAllocationLink.document_section_id,
        )
        .where(
            DocumentSection.document_id == run.document_id,
            DocumentSection.status == "MATCHED",
            DocumentAllocationLink.receipt_lot_allocation_id == allocation.id,
            DocumentAllocationLink.match_status == "CONFIRMED",
        )
        .with_for_update()
        .limit(1)
    )
    if linked_allocation_id is None:
        raise HTTPException(status_code=409, detail="Extraction allocation lineage mismatch")
    version, profile = _select_spec(session, allocation)
    spec_items = list(
        session.scalars(select(SpecItem).where(SpecItem.spec_version_id == version.id))
    )
    standards = {
        item.id: item
        for item in session.scalars(
            select(StandardTestItem).where(
                StandardTestItem.id.in_([item.standard_test_item_id for item in spec_items])
            )
        )
    }
    standards_by_code = {standard.code: standard for standard in standards.values()}
    if len(standards_by_code) != len(standards):
        raise HTTPException(status_code=422, detail="Duplicate current specification codes")
    reviewed_rows = list(
        session.scalars(
            select(ExtractionFieldReview).where(ExtractionFieldReview.extraction_run_id == run.id)
        )
    )
    if not reviewed_rows or any(field.status != "CONFIRMED" for field in reviewed_rows):
        raise HTTPException(status_code=422, detail="Every extraction field must be confirmed")

    reviewed: dict[str, Decimal] = {}
    if run.provider_name == "local-paddleocr":
        review_payload = run.candidate_payload.get("review")
        payload_fields = run.candidate_payload.get("fields")
        if (
            not isinstance(review_payload, dict)
            or review_payload.get("spec_version_id") != str(version.id)
            or not isinstance(payload_fields, list)
        ):
            raise HTTPException(status_code=422, detail="Confirmed mapping specification mismatch")
        metadata_by_id: dict[str, dict[str, Any]] = {}
        for metadata in payload_fields:
            if not isinstance(metadata, dict) or not isinstance(metadata.get("field_id"), str):
                raise HTTPException(status_code=422, detail="Confirmed mapping identity is invalid")
            field_id = metadata["field_id"]
            if field_id in metadata_by_id:
                raise HTTPException(status_code=422, detail="Duplicate confirmed mapping identity")
            metadata_by_id[field_id] = metadata
        if set(metadata_by_id) != {str(field.id) for field in reviewed_rows}:
            raise HTTPException(status_code=422, detail="Confirmed mapping identity is invalid")
        mapped_codes: list[str] = []
        for field in reviewed_rows:
            metadata = metadata_by_id[str(field.id)]
            source_key = metadata.get("source_field_key")
            disposition = metadata.get("mapping_disposition")
            mapped_key = metadata.get("mapped_field_key")
            if not isinstance(source_key, str):
                raise HTTPException(status_code=422, detail="Confirmed mapping identity is invalid")
            if disposition == "UNMAPPED":
                if mapped_key is not None or field.field_key != source_key:
                    raise HTTPException(
                        status_code=422, detail="Confirmed UNMAPPED field is invalid"
                    )
                continue
            if (
                disposition != "MAP"
                or not isinstance(mapped_key, str)
                or mapped_key not in standards_by_code
                or field.field_key != mapped_key
            ):
                raise HTTPException(
                    status_code=422, detail="Confirmed mapping is outside the selected spec"
                )
            value = _canonical_finite_decimal(field.final_text)
            if value is None:
                raise HTTPException(
                    status_code=422,
                    detail="Confirmed supplier result must be a canonical finite decimal string",
                )
            mapped_codes.append(mapped_key)
            reviewed[mapped_key] = value
        if len(mapped_codes) != len(set(mapped_codes)) or set(mapped_codes) != set(reviewed):
            raise HTTPException(status_code=422, detail="Duplicate confirmed supplier result")
        if (
            review_payload.get("mapped_count") != len(mapped_codes)
            or review_payload.get("unmapped_count") != len(reviewed_rows) - len(mapped_codes)
            or review_payload.get("target_codes") != sorted(mapped_codes)
        ):
            raise HTTPException(status_code=422, detail="Confirmed mapping summary is invalid")
    else:
        for field in reviewed_rows:
            if field.field_key not in standards_by_code:
                continue
            if field.field_key in reviewed:
                raise HTTPException(status_code=422, detail="Duplicate confirmed supplier result")
            value = _canonical_finite_decimal(field.final_text)
            if value is None:
                raise HTTPException(
                    status_code=422,
                    detail="Confirmed supplier result must be a canonical finite decimal string",
                )
            reviewed[field.field_key] = value

    case_id = uuid4()
    case = InspectionCase(
        id=case_id,
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=version.id,
        spec_snapshot=_spec_snapshot(session, version, profile),
        status="INTERNAL_TEST_PENDING",
        candidate_decision="ON_HOLD",
        lineage_root_id=case_id,
        round_no=1,
        revision_no=1,
    )
    session.add(case)
    session.flush()
    for item in spec_items:
        standard = standards[item.standard_test_item_id]
        raw = reviewed.get(standard.code)
        if raw is None and item.source_policy != "INTERNAL_ONLY":
            continue
        result = SupplierResult(
            inspection_case_id=case.id,
            standard_test_item_id=standard.id,
            supplier_item_name=standard.name,
            normalized_value=raw,
            mapping_status="MANUAL_CONFIRMED",
            supplier_spec_text="Synthetic supplier reference specification",
            supplier_decision="ACCEPTED" if raw is not None else None,
        )
        session.add(result)
        session.flush()
        if raw is not None:
            session.add(
                SampleMeasurement(supplier_result_id=result.id, sample_index=1, numeric_value=raw)
            )
    session.add(
        AuditLog(
            entity_type="inspection_case",
            entity_id=case.id,
            action="P3_INSPECTION_CREATED",
            payload={"spec_version_id": str(version.id), "extraction_run_id": str(run.id)},
        )
    )
    body = {"inspection_id": str(case.id)}
    complete_idempotency(record, status=201, body=body, resource_ref=str(case.id))
    session.commit()
    return body


def evaluate_inspection(
    session: Session, case: InspectionCase, *, persist: bool = True
) -> dict[str, Any]:
    allocation = session.get(ReceiptLotAllocation, case.receipt_lot_allocation_id)
    receipt = session.get(InboundReceipt, allocation.inbound_receipt_id) if allocation else None
    lot = session.get(MaterialLot, allocation.material_lot_id) if allocation else None
    if allocation is None or receipt is None or lot is None:
        raise HTTPException(status_code=404, detail="Inspection context not found")
    repository = ApprovalRepository()
    version, _profile = repository._effective_spec(
        session, case=case, allocation=allocation, receipt=receipt, lot=lot
    )
    spec_items, supplier_results, internal_results, inputs, evaluations = (
        repository._persisted_inputs(session, case=case, spec_version=version)
    )
    candidate = JudgmentEngine().evaluate_case(inputs)
    standards = {item.id: item for item in session.scalars(select(StandardTestItem))}
    supplier_by_standard = {
        item.standard_test_item_id: item for item in supplier_results if item.standard_test_item_id
    }
    internal_by_spec = {item.spec_item_id: item for item in internal_results}
    blockers: list[str] = []
    judgments: list[dict[str, Any]] = []
    for spec_item, evaluation in zip(spec_items, evaluations, strict=True):
        supplier = supplier_by_standard.get(spec_item.standard_test_item_id)
        internal = internal_by_spec.get(spec_item.id)
        if persist and supplier is not None:
            supplier.hyc_decision = (
                evaluation.hyc_supplier_decision.value if evaluation.hyc_supplier_decision else None
            )
        if persist and internal is not None:
            internal.decision = (
                evaluation.internal_decision.value if evaluation.internal_decision else None
            )
        if evaluation.overall is EngineDecision.ON_HOLD:
            blockers.append(
                "INTERNAL_TEST_PENDING"
                if spec_item.source_policy
                in {"INTERNAL_ONLY", "BOTH_ALL_MUST_PASS", "SUPPLIER_REFERENCE_INTERNAL_FINAL"}
                and internal is None
                else "SUPPLIER_REVIEW_REQUIRED"
            )
        standard = standards[spec_item.standard_test_item_id]
        judgments.append(
            {
                "spec_item_id": str(spec_item.id),
                "item_code": standard.code,
                "supplier_decision": supplier.supplier_decision if supplier else None,
                "hyc_reference_decision": evaluation.hyc_supplier_decision.value
                if evaluation.hyc_supplier_decision
                else None,
                "internal_decision": evaluation.internal_decision.value
                if evaluation.internal_decision
                else None,
                "effective_decision": evaluation.overall.value,
            }
        )
    blockers = sorted(set(blockers))
    if persist and case.final_decision is None:
        case.candidate_decision = candidate.value
        if case.status != "RETURNED":
            case.status = "INTERNAL_TEST_PENDING" if blockers else "READY_FOR_REVIEW"
        session.flush()
    return {
        "inspection_id": str(case.id),
        "material_lot_id": str(lot.id),
        "allocation_id": str(allocation.id),
        "spec_version_id": str(case.spec_version_id),
        "spec_snapshot": case.spec_snapshot,
        "status": case.status,
        "candidate_decision": candidate.value,
        "final_decision": case.final_decision,
        "version": case.lock_version,
        "round_no": case.round_no,
        "revision_no": case.revision_no,
        "blockers": blockers,
        "judgments": judgments,
    }


def put_internal_results(
    session: Session,
    *,
    case: InspectionCase,
    request: InternalResultsRequest,
    expected_version: int,
) -> dict[str, Any]:
    if case.lock_version != expected_version:
        raise HTTPException(status_code=409, detail="Stale inspection version")
    if case.final_decision is not None:
        raise HTTPException(status_code=409, detail="Finalized inspection is immutable")
    submitted_spec_ids = [submitted.spec_item_id for submitted in request.results]
    if len(submitted_spec_ids) != len(set(submitted_spec_ids)):
        raise HTTPException(status_code=422, detail="Internal result spec items must be unique")
    spec_items: dict[UUID, SpecItem] = {}
    for submitted in request.results:
        spec_item = session.get(SpecItem, submitted.spec_item_id)
        if spec_item is None or spec_item.spec_version_id != case.spec_version_id:
            raise HTTPException(status_code=422, detail="Internal result spec item is invalid")
        spec_items[submitted.spec_item_id] = spec_item

    existing_results = {
        result.spec_item_id: result
        for result in session.scalars(
            select(InternalResult).where(InternalResult.inspection_case_id == case.id)
        )
    }
    existing_spec_ids = set(existing_results)
    requested_spec_ids = set(submitted_spec_ids)
    retained_spec_ids = existing_spec_ids & requested_spec_ids
    removed_spec_ids = existing_spec_ids - requested_spec_ids
    deleted_sample_count = 0
    for result in existing_results.values():
        samples = list(
            session.scalars(
                select(SampleMeasurement).where(SampleMeasurement.internal_result_id == result.id)
            )
        )
        deleted_sample_count += len(samples)
        for sample in samples:
            session.delete(sample)
    session.flush()
    for spec_item_id, result in existing_results.items():
        if spec_item_id not in spec_items:
            session.delete(result)
    session.flush()

    for submitted in request.results:
        spec_item = spec_items[submitted.spec_item_id]
        current_result = existing_results.get(spec_item.id)
        if current_result is None:
            current_result = InternalResult(inspection_case_id=case.id, spec_item_id=spec_item.id)
            session.add(current_result)
            session.flush()
        current_result.evaluated_value = submitted.values[0]
        for index, value in enumerate(submitted.values, start=1):
            session.add(
                SampleMeasurement(
                    internal_result_id=current_result.id,
                    sample_index=index,
                    numeric_value=value,
                )
            )
    session.add(
        AuditLog(
            entity_type="inspection_case",
            entity_id=case.id,
            action="P3_INTERNAL_RESULTS_UPDATED",
            payload={
                "result_count": len(request.results),
                "requested_spec_item_ids": sorted(str(spec_id) for spec_id in requested_spec_ids),
                "retained_spec_item_ids": sorted(str(spec_id) for spec_id in retained_spec_ids),
                "removed_spec_item_ids": sorted(str(spec_id) for spec_id in removed_spec_ids),
                "deleted_result_count": len(removed_spec_ids),
                "deleted_sample_count": deleted_sample_count,
            },
        )
    )
    evaluate_inspection(session, case)
    case.updated_at = datetime.now(UTC)
    session.commit()
    session.refresh(case)
    return evaluate_inspection(session, case, persist=False) | {"version": case.lock_version}


def submit_inspection(
    session: Session, *, case: InspectionCase, expected_version: int, principal: Principal
) -> dict[str, Any]:
    if case.lock_version != expected_version:
        raise HTTPException(status_code=409, detail="Stale inspection version")
    if case.final_decision is not None:
        raise HTTPException(status_code=409, detail="Finalized inspection is immutable")
    view = evaluate_inspection(session, case)
    if view["blockers"] or view["candidate_decision"] == "ON_HOLD":
        raise HTTPException(
            status_code=422, detail="Inspection blockers must be cleared before submit"
        )
    case.status = "LEAD_REVIEW"
    case.submitted_by_id = principal.actor_id
    session.add(
        AuditLog(
            entity_type="inspection_case",
            entity_id=case.id,
            action="P3_SUBMITTED",
            payload={"actor_id": str(principal.actor_id)},
        )
    )
    session.commit()
    session.refresh(case)
    return evaluate_inspection(session, case, persist=False) | {"version": case.lock_version}


def approve_inspection(
    session: Session,
    *,
    case_id: UUID,
    expected_version: int,
    principal: Principal,
    action: str,
    reason: str | None,
    fault_at: str | None,
) -> InspectionCase:
    case = session.get(InspectionCase, case_id, with_for_update=True)
    if case is None:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if action == "RETURN":
        if not reason or not reason.strip():
            raise HTTPException(status_code=422, detail="Return requires a reason")
        if case.lock_version != expected_version or case.status != "LEAD_REVIEW":
            raise HTTPException(status_code=409, detail="Stale inspection version/state")
        case.status = "RETURNED"
        session.add(
            AuditLog(
                entity_type="inspection_case",
                entity_id=case.id,
                action="P3_RETURNED",
                reason=reason,
                payload={"actor_id": str(principal.actor_id)},
            )
        )
        session.flush()
        return case
    try:
        finalized = ApprovalRepository().finalize(
            session,
            case_id=case_id,
            expected_version=expected_version,
            actor_id=principal.actor_id,
            actor_role=principal.role,
            final_decision=case.candidate_decision or "ON_HOLD",
            reason=reason,
        )
        if fault_at:
            session.flush()
            raise RuntimeError(f"P3 fault injection: {fault_at}")
        return finalized
    except (ApprovalPrecondition, AuthorizationDenied, OptimisticConflict) as error:
        session.rollback()
        status = (
            403
            if isinstance(error, AuthorizationDenied)
            else 409
            if isinstance(error, OptimisticConflict)
            else 422
        )
        raise HTTPException(status_code=status, detail=str(error)) from error


def clone_lineage(
    session: Session,
    *,
    predecessor: InspectionCase,
    reason: str,
    retest: bool,
    principal: Principal,
) -> InspectionCase:
    if predecessor.final_decision is None:
        raise HTTPException(status_code=422, detail="Only finalized inspections can start lineage")
    root = predecessor.lineage_root_id or predecessor.id
    case = InspectionCase(
        receipt_lot_allocation_id=predecessor.receipt_lot_allocation_id,
        spec_version_id=predecessor.spec_version_id,
        spec_snapshot=predecessor.spec_snapshot,
        status="INTERNAL_TEST_PENDING" if retest else "READY_FOR_REVIEW",
        candidate_decision="ON_HOLD" if retest else predecessor.candidate_decision,
        correction_of_case_id=None if retest else predecessor.id,
        retest_of_case_id=predecessor.id if retest else None,
        lineage_root_id=root,
        round_no=predecessor.round_no + 1 if retest else predecessor.round_no,
        revision_no=1 if retest else predecessor.revision_no + 1,
        lineage_reason=reason,
    )
    session.add(case)
    session.flush()
    for supplier in session.scalars(
        select(SupplierResult).where(SupplierResult.inspection_case_id == predecessor.id)
    ):
        copied = SupplierResult(
            inspection_case_id=case.id,
            standard_test_item_id=supplier.standard_test_item_id,
            supplier_item_name=supplier.supplier_item_name,
            normalized_value=supplier.normalized_value,
            normalized_text=supplier.normalized_text,
            mapping_status=supplier.mapping_status,
            supplier_spec_text=supplier.supplier_spec_text,
            supplier_decision=supplier.supplier_decision,
            hyc_decision=supplier.hyc_decision,
        )
        session.add(copied)
        session.flush()
        for sample in session.scalars(
            select(SampleMeasurement).where(SampleMeasurement.supplier_result_id == supplier.id)
        ):
            session.add(
                SampleMeasurement(
                    supplier_result_id=copied.id,
                    sample_index=sample.sample_index,
                    numeric_value=sample.numeric_value,
                    text_value=sample.text_value,
                )
            )
    if not retest:
        for internal in session.scalars(
            select(InternalResult).where(InternalResult.inspection_case_id == predecessor.id)
        ):
            copied_internal = InternalResult(
                inspection_case_id=case.id,
                spec_item_id=internal.spec_item_id,
                evaluated_value=internal.evaluated_value,
                evaluated_text=internal.evaluated_text,
                decision=internal.decision,
            )
            session.add(copied_internal)
            session.flush()
            for sample in session.scalars(
                select(SampleMeasurement).where(SampleMeasurement.internal_result_id == internal.id)
            ):
                session.add(
                    SampleMeasurement(
                        internal_result_id=copied_internal.id,
                        sample_index=sample.sample_index,
                        numeric_value=sample.numeric_value,
                        text_value=sample.text_value,
                    )
                )
    session.add(
        AuditLog(
            entity_type="inspection_case",
            entity_id=case.id,
            action="P3_RETEST_CREATED" if retest else "P3_REVISION_CREATED",
            reason=reason,
            payload={"predecessor_id": str(predecessor.id), "actor_id": str(principal.actor_id)},
        )
    )
    session.commit()
    return case
