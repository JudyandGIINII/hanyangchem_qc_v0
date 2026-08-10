from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import (
    InboundReceipt,
    InspectionCase,
    Material,
    MaterialLot,
    Nonconformance,
    NonconformanceDisposition,
    ReceiptLotAllocation,
    SpecProfile,
    SpecVersion,
    Supplier,
)

POSTGRES_DSN = os.environ.get("HYC_P2_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine() -> Engine:
    if not POSTGRES_DSN:
        pytest.skip("HYC_P2_TEST_POSTGRES_DSN must name a disposable PostgreSQL database")
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_DSN)
    command.upgrade(config, "head")
    value = create_engine(POSTGRES_DSN)
    yield value
    command.downgrade(config, "base")
    with value.connect() as connection:
        remaining = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        )
        assert remaining.scalar_one() == 0
    value.dispose()


def _inspection_case(session: Session) -> InspectionCase:
    supplier = Supplier(name="synthetic supplier")
    material = Material(name="synthetic material")
    session.add_all((supplier, material))
    session.flush()
    lot = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="synthetic-v1",
        identity_key=f"LOT-{uuid4()}",
        identity_status="CANONICAL",
    )
    receipt = InboundReceipt(
        inbound_no=f"IN-{uuid4()}",
        supplier_id=supplier.id,
        receipt_date=date(2026, 8, 10),
    )
    session.add_all((lot, receipt))
    session.flush()
    allocation = ReceiptLotAllocation(
        inbound_receipt_id=receipt.id,
        material_lot_id=lot.id,
        quantity=Decimal("1"),
        quantity_unit="kg",
    )
    profile = SpecProfile(material_id=material.id, name="synthetic scope")
    session.add_all((allocation, profile))
    session.flush()
    version = SpecVersion(
        spec_profile_id=profile.id,
        version=1,
        status="DRAFT",
        effective_from=date(2026, 1, 1),
    )
    session.add(version)
    session.flush()
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=version.id,
    )
    session.add(case)
    session.flush()
    return case


def test_seeded_dispositions_cannot_be_deleted_and_deactivation_preserves_references(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        dispositions = session.scalars(
            select(NonconformanceDisposition).order_by(NonconformanceDisposition.sort_order)
        ).all()
        assert [(row.code, row.name) for row in dispositions] == [
            ("반품", "반품"),
            ("재작업", "재작업"),
            ("용도변경", "용도변경"),
            ("폐기", "폐기"),
            ("선별작업", "선별작업"),
            ("특채", "특채"),
        ]
        assert all(row.active for row in dispositions)

        disposition = dispositions[0]
        case = _inspection_case(session)
        nonconformance = Nonconformance(
            ncr_number=f"NCR-{uuid4()}",
            inspection_case_id=case.id,
            quantity=Decimal("1"),
            disposition_id=disposition.id,
            disposition_snapshot={"code": disposition.code, "name": disposition.name},
        )
        session.add(nonconformance)
        session.commit()

        session.delete(disposition)
        with pytest.raises(DatabaseError, match="cannot be deleted; deactivate instead"):
            session.commit()
        session.rollback()

        disposition = session.get(NonconformanceDisposition, disposition.id)
        assert disposition is not None
        disposition.active = False
        session.commit()

        persisted = session.get(Nonconformance, nonconformance.id)
        assert persisted is not None
        assert persisted.disposition_id == disposition.id
        assert persisted.disposition_snapshot == {"code": "반품", "name": "반품"}
        assert disposition.active is False


def test_approved_nonconformance_is_immutable_at_the_database_level(engine: Engine) -> None:
    with Session(engine) as session:
        disposition = session.scalar(
            select(NonconformanceDisposition).where(NonconformanceDisposition.code == "재작업")
        )
        assert disposition is not None
        case = _inspection_case(session)
        nonconformance = Nonconformance(
            ncr_number=f"NCR-{uuid4()}",
            inspection_case_id=case.id,
            quantity=Decimal("1"),
            disposition_id=disposition.id,
            disposition_snapshot={"code": disposition.code, "name": disposition.name},
            status="APPROVED",
        )
        session.add(nonconformance)
        session.commit()

        for statement in (
            "UPDATE nonconformances SET description = 'changed' WHERE id = :id",
            "DELETE FROM nonconformances WHERE id = :id",
        ):
            with pytest.raises(DatabaseError, match="approved nonconformance is immutable"):
                with engine.begin() as connection:
                    connection.execute(text(statement), {"id": nonconformance.id})
