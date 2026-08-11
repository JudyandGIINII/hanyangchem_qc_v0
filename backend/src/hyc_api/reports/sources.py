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
