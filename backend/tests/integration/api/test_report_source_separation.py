from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.reports.sources import (
    ReportSourceUnavailable,
    load_frozen_decision,
    load_reference_information,
)
from hyc_data.models import InspectionCase, Material, MaterialLot, ReceiptLotAllocation

pytestmark = pytest.mark.postgres


def _approved_case(p3) -> UUID:
    flow = p3.reviewed(suffix=f"report-source-{uuid4().hex}")
    cleared = p3.clear_hold(str(flow["inspection_id"]))
    submitted = p3.submit(str(flow["inspection_id"]), int(cleared["version"]))
    approval = p3.approve(
        str(flow["inspection_id"]),
        int(submitted["version"]),
        key=f"report-source-{uuid4().hex}",
    )
    assert approval.status_code == 200, approval.text
    return UUID(str(flow["inspection_id"]))


def _material_for_case(session: Session, case_id: UUID) -> Material:
    material = session.scalar(
        select(Material)
        .join(MaterialLot, MaterialLot.material_id == Material.id)
        .join(ReceiptLotAllocation, ReceiptLotAllocation.material_lot_id == MaterialLot.id)
        .join(InspectionCase, InspectionCase.receipt_lot_allocation_id == ReceiptLotAllocation.id)
        .where(InspectionCase.id == case_id)
    )
    assert material is not None
    return material


def test_frozen_decision_is_read_only_from_the_snapshot(p3, p3_engine_storage) -> None:
    case_id = _approved_case(p3)
    with p3_engine_storage.session_factory() as session:
        before = load_frozen_decision(session, case_id)
        material = _material_for_case(session, case_id)
        original_name = material.name
        try:
            material.name = "변경된 품목명"
            session.commit()
            after = load_frozen_decision(session, case_id)
            assert after.content_hash == before.content_hash
            assert after.payload == before.payload
        finally:
            material.name = original_name
            session.commit()


def test_reference_information_reflects_the_current_database(p3, p3_engine_storage) -> None:
    case_id = _approved_case(p3)
    with p3_engine_storage.session_factory() as session:
        before = load_reference_information(session, case_id)
        material = _material_for_case(session, case_id)
        original_name = material.name
        try:
            material.name = "변경된 품목명"
            session.commit()
            after = load_reference_information(session, case_id)
            assert before.material_name != after.material_name
            assert after.material_name == "변경된 품목명"
        finally:
            material.name = original_name
            session.commit()


def test_nonconformance_created_after_approval_appears_in_lookups(p3, p3_engine_storage) -> None:
    case_id = _approved_case(p3)
    with p3_engine_storage.session_factory() as session:
        assert load_reference_information(session, case_id).nonconformances == []
    response = p3.client.post(
        "/api/v1/nonconformances",
        json={
            "ncr_number": f"REPORT-NCR-{uuid4().hex}",
            "inspection_case_id": str(case_id),
            "quantity": "1.00",
            "description": "입도 미달",
        },
        headers=p3.inspector,
    )
    assert response.status_code == 201, response.text
    with p3_engine_storage.session_factory() as session:
        found = load_reference_information(session, case_id).nonconformances
    assert [item["title"] for item in found] == ["입도 미달"]


def test_missing_snapshot_fails_closed(p3, p3_engine_storage) -> None:
    flow = p3.reviewed(suffix=f"report-source-unapproved-{uuid4().hex}")
    with p3_engine_storage.session_factory() as session:
        with pytest.raises(ReportSourceUnavailable):
            load_frozen_decision(session, UUID(str(flow["inspection_id"])))
