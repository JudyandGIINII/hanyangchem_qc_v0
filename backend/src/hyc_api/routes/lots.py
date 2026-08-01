from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import require_principal
from hyc_api.contracts import LotTraceResponse
from hyc_api.dependencies import database_session
from hyc_data.models import (
    Approval,
    AuditLog,
    Document,
    DocumentAllocationLink,
    DocumentSection,
    InboundReceipt,
    InspectionCase,
    MaterialLot,
    ReceiptLotAllocation,
)

router = APIRouter(prefix="/api/v1", tags=["p3-trace"])
DBSession = Annotated[Session, Depends(database_session)]


@router.get("/lots/{material_lot_id}/trace", response_model=LotTraceResponse)
def lot_trace(
    request: Request,
    material_lot_id: UUID,
    session: DBSession,
) -> LotTraceResponse:
    require_principal(request)
    lot = session.get(MaterialLot, material_lot_id)
    if lot is None:
        raise HTTPException(status_code=404, detail="Material LOT not found")
    allocations = list(
        session.scalars(
            select(ReceiptLotAllocation)
            .where(ReceiptLotAllocation.material_lot_id == lot.id)
            .order_by(ReceiptLotAllocation.created_at, ReceiptLotAllocation.id)
        )
    )
    receipts_by_id = (
        {
            receipt.id: receipt
            for receipt in session.scalars(
                select(InboundReceipt)
                .where(InboundReceipt.id.in_([item.inbound_receipt_id for item in allocations]))
                .order_by(InboundReceipt.receipt_date, InboundReceipt.id)
            )
        }
        if allocations
        else {}
    )
    allocation_ids = [item.id for item in allocations]
    documents = (
        list(
            session.execute(
                select(Document, DocumentSection, DocumentAllocationLink)
                .join(DocumentSection, DocumentSection.document_id == Document.id)
                .join(
                    DocumentAllocationLink,
                    DocumentAllocationLink.document_section_id == DocumentSection.id,
                )
                .where(DocumentAllocationLink.receipt_lot_allocation_id.in_(allocation_ids))
                .order_by(
                    Document.checksum_sha256,
                    DocumentSection.section_index,
                    DocumentAllocationLink.id,
                )
            )
        )
        if allocation_ids
        else []
    )
    cases = (
        list(
            session.scalars(
                select(InspectionCase)
                .where(InspectionCase.receipt_lot_allocation_id.in_(allocation_ids))
                .order_by(InspectionCase.round_no, InspectionCase.revision_no, InspectionCase.id)
            )
        )
        if allocation_ids
        else []
    )
    case_ids = [case.id for case in cases]
    approvals = (
        {
            item.inspection_case_id: item
            for item in session.scalars(
                select(Approval).where(Approval.inspection_case_id.in_(case_ids))
            )
        }
        if case_ids
        else {}
    )
    audits = (
        list(
            session.scalars(
                select(AuditLog)
                .where(
                    (AuditLog.entity_id.in_(case_ids))
                    | (AuditLog.entity_id.in_([item.inbound_receipt_id for item in allocations]))
                )
                .order_by(AuditLog.created_at, AuditLog.id)
            )
        )
        if allocations
        else []
    )
    return LotTraceResponse(
        material_lot_id=lot.id,
        identity_key=lot.identity_key or "PROVISIONAL",
        receipts=[
            {
                "id": str(item.id),
                "inbound_no": item.inbound_no,
                "receipt_date": item.receipt_date.isoformat(),
            }
            for item in receipts_by_id.values()
        ],
        allocations=[
            {
                "id": str(item.id),
                "receipt_id": str(item.inbound_receipt_id),
                "quantity": format(item.quantity, "f"),
                "unit": item.quantity_unit,
            }
            for item in allocations
        ],
        documents=[
            {
                "document_id": str(document.id),
                "checksum_sha256": document.checksum_sha256,
                "section_id": str(section.id),
                "allocation_id": str(link.receipt_lot_allocation_id),
                "match_status": link.match_status,
            }
            for document, section, link in documents
        ],
        inspections=[
            {
                "id": str(case.id),
                "allocation_id": str(case.receipt_lot_allocation_id),
                "status": case.status,
                "candidate_decision": case.candidate_decision,
                "final_decision": case.final_decision,
                "spec_version_id": str(case.spec_version_id),
                "spec_snapshot": case.spec_snapshot,
                "round_no": case.round_no,
                "revision_no": case.revision_no,
                "correction_of_case_id": str(case.correction_of_case_id)
                if case.correction_of_case_id
                else None,
                "retest_of_case_id": str(case.retest_of_case_id)
                if case.retest_of_case_id
                else None,
                "approval_id": str(approvals[case.id].id) if case.id in approvals else None,
            }
            for case in cases
        ],
        audits=[
            {
                "id": str(item.id),
                "entity_id": str(item.entity_id),
                "action": item.action,
                "reason": item.reason,
                "created_at": item.created_at.isoformat(),
            }
            for item in audits
        ],
    )
