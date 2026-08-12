from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from hyc_data.models import (
    DecisionSnapshotRow,
    Document,
    DocumentAllocationLink,
    DocumentSection,
    InboundReceipt,
    InspectionCase,
    Material,
    MaterialLot,
    MaterialModel,
    Nonconformance,
    NonconformanceAttachment,
    ReceiptLotAllocation,
    Supplier,
)


class ReportSourceUnavailable(Exception):
    """Raised when a report input does not exist; reporting must fail closed."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class FrozenDecisionSource:
    """Values fixed at approval time.

    These are never reconciled against current rows.  Reporting reads every
    judgment value from here so that a later master-data edit cannot restate
    what was decided.
    """

    payload: dict[str, Any]
    content_hash: str


@dataclass(frozen=True, slots=True)
class LookedUpReferenceSource:
    """Values read at report time, which may differ between two renders.

    Names, document metadata, nonconformances and attachments are not in the
    approval snapshot.  A nonconformance in particular is raised *after*
    approval, so it cannot be frozen into one.
    """

    material_name: str
    supplier_name: str
    model_name: str
    documents: list[tuple[str, str]]
    nonconformances: list[dict[str, str]]
    attachments: list[str]
    observed_at: datetime


def load_frozen_decision(session: Session, case_id: UUID) -> FrozenDecisionSource:
    row = session.scalar(
        select(DecisionSnapshotRow).where(DecisionSnapshotRow.inspection_case_id == case_id)
    )
    if row is None:
        raise ReportSourceUnavailable("APPROVAL_SNAPSHOT_MISSING")
    return FrozenDecisionSource(payload=dict(row.payload), content_hash=row.content_hash)


def load_reference_information(session: Session, case_id: UUID) -> LookedUpReferenceSource:
    reference = session.execute(
        select(
            Material.name,
            Supplier.name,
            func.coalesce(MaterialModel.name, ""),
            ReceiptLotAllocation.id,
        )
        .select_from(InspectionCase)
        .join(
            ReceiptLotAllocation,
            InspectionCase.receipt_lot_allocation_id == ReceiptLotAllocation.id,
        )
        .join(MaterialLot, ReceiptLotAllocation.material_lot_id == MaterialLot.id)
        .join(Material, MaterialLot.material_id == Material.id)
        .join(Supplier, MaterialLot.supplier_id == Supplier.id)
        .outerjoin(MaterialModel, ReceiptLotAllocation.model_id == MaterialModel.id)
        .where(InspectionCase.id == case_id)
    ).one_or_none()
    if reference is None:
        raise ReportSourceUnavailable("INSPECTION_CASE_REFERENCE_MISSING")
    material_name, supplier_name, model_name, allocation_id = reference

    documents = [
        (str(filename), str(checksum))
        for filename, checksum in session.execute(
            select(Document.original_filename, Document.checksum_sha256)
            .select_from(DocumentAllocationLink)
            .join(DocumentSection, DocumentAllocationLink.document_section_id == DocumentSection.id)
            .join(Document, DocumentSection.document_id == Document.id)
            .where(
                DocumentAllocationLink.receipt_lot_allocation_id == allocation_id,
                Document.deleted_at.is_(None),
            )
            .distinct()
            .order_by(Document.original_filename, Document.checksum_sha256)
        )
    ]
    nonconformances = [
        {
            "id": str(nonconformance_id),
            "ncr_number": str(ncr_number),
            "title": str(description or ncr_number),
            "severity": str(severity or ""),
            "description": str(description or ""),
            "status": str(status),
        }
        for nonconformance_id, ncr_number, severity, description, status in session.execute(
            select(
                Nonconformance.id,
                Nonconformance.ncr_number,
                Nonconformance.severity,
                Nonconformance.description,
                Nonconformance.status,
            )
            .where(
                Nonconformance.inspection_case_id == case_id,
                Nonconformance.deleted_at.is_(None),
            )
            .order_by(Nonconformance.ncr_number, Nonconformance.id)
        )
    ]
    attachments = list(
        session.scalars(
            select(Document.original_filename)
            .select_from(NonconformanceAttachment)
            .join(
                Nonconformance,
                NonconformanceAttachment.nonconformance_id == Nonconformance.id,
            )
            .join(Document, NonconformanceAttachment.document_id == Document.id)
            .where(
                Nonconformance.inspection_case_id == case_id,
                Nonconformance.deleted_at.is_(None),
                Document.deleted_at.is_(None),
            )
            .distinct()
            .order_by(Document.original_filename)
        )
    )
    return LookedUpReferenceSource(
        material_name=material_name,
        supplier_name=supplier_name,
        model_name=model_name,
        documents=documents,
        nonconformances=nonconformances,
        attachments=attachments,
        observed_at=datetime.now(UTC),
    )


@dataclass(frozen=True, slots=True)
class LotTraceAllocation:
    allocation_id: str
    inbound_no: str
    receipt_date: str
    model_name: str
    quantity: str
    quantity_unit: str
    status: str


@dataclass(frozen=True, slots=True)
class LotTraceCasePair:
    frozen: FrozenDecisionSource
    reference: LookedUpReferenceSource


@dataclass(frozen=True, slots=True)
class LotTraceSources:
    material_lot_id: str
    supplier_lot_no_raw: str
    identity_key: str
    identity_status: str
    production_date_evidence: str
    merged_into_id: str
    supplier_name: str
    material_name: str
    model_name: str
    allocations: list[LotTraceAllocation]
    case_pairs: list[LotTraceCasePair]
    observed_at: datetime


def load_lot_trace_sources(
    session: Session, material_lot_id: UUID | str
) -> LotTraceSources:
    lot_uuid = (
        UUID(str(material_lot_id))
        if isinstance(material_lot_id, str)
        else material_lot_id
    )
    lot = session.scalar(
        select(MaterialLot).where(
            MaterialLot.id == lot_uuid,
            MaterialLot.deleted_at.is_(None),
        )
    )
    if lot is None:
        raise ReportSourceUnavailable("LOT_NOT_FOUND")

    supplier = session.scalar(
        select(Supplier).where(
            Supplier.id == lot.supplier_id,
            Supplier.deleted_at.is_(None),
        )
    )
    supplier_name = str(supplier.name or "") if supplier else ""

    material = session.scalar(
        select(Material).where(
            Material.id == lot.material_id,
            Material.deleted_at.is_(None),
        )
    )
    material_name = str(material.name or "") if material else ""

    alloc_stmt = (
        select(ReceiptLotAllocation, InboundReceipt, MaterialModel)
        .join(
            InboundReceipt,
            ReceiptLotAllocation.inbound_receipt_id == InboundReceipt.id,
        )
        .outerjoin(
            MaterialModel,
            ReceiptLotAllocation.model_id == MaterialModel.id,
        )
        .where(
            ReceiptLotAllocation.material_lot_id == lot.id,
            ReceiptLotAllocation.deleted_at.is_(None),
            InboundReceipt.deleted_at.is_(None),
        )
        .order_by(
            InboundReceipt.receipt_date,
            InboundReceipt.inbound_no,
            ReceiptLotAllocation.id,
        )
    )

    alloc_rows = session.execute(alloc_stmt).all()
    allocations: list[LotTraceAllocation] = []
    alloc_ids: list[UUID] = []
    primary_model_name = ""

    for alloc, receipt, model in alloc_rows:
        alloc_ids.append(alloc.id)
        mod_name = str(model.name or "") if model else ""
        if not primary_model_name and mod_name:
            primary_model_name = mod_name
        allocations.append(
            LotTraceAllocation(
                allocation_id=str(alloc.id),
                inbound_no=str(receipt.inbound_no or ""),
                receipt_date=str(receipt.receipt_date or ""),
                model_name=mod_name,
                quantity=str(alloc.quantity),
                quantity_unit=str(alloc.quantity_unit or ""),
                status=str(receipt.status or ""),
            )
        )

    case_pairs: list[LotTraceCasePair] = []
    if alloc_ids:
        case_stmt = (
            select(InspectionCase, DecisionSnapshotRow)
            .join(
                DecisionSnapshotRow,
                DecisionSnapshotRow.inspection_case_id == InspectionCase.id,
            )
            .where(
                InspectionCase.receipt_lot_allocation_id.in_(alloc_ids),
                InspectionCase.deleted_at.is_(None),
                InspectionCase.status != "CANCELLED",
            )
            .order_by(
                DecisionSnapshotRow.created_at,
                InspectionCase.id,
            )
        )
        case_rows = session.execute(case_stmt).tuples().all()
        for case, _snapshot in case_rows:
            frozen = load_frozen_decision(session, case.id)
            ref = load_reference_information(session, case.id)
            case_pairs.append(LotTraceCasePair(frozen=frozen, reference=ref))

    return LotTraceSources(
        material_lot_id=str(lot.id),
        supplier_lot_no_raw=str(lot.supplier_lot_no_raw or ""),
        identity_key=str(lot.identity_key or ""),
        identity_status=str(lot.identity_status or ""),
        production_date_evidence=str(lot.production_date_evidence or ""),
        merged_into_id=str(lot.merged_into_id or ""),
        supplier_name=supplier_name,
        material_name=material_name,
        model_name=primary_model_name,
        allocations=allocations,
        case_pairs=case_pairs,
        observed_at=datetime.now(UTC),
    )
