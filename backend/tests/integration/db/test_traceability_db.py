from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import (
    BillOfMaterial,
    InboundReceipt,
    Material,
    MaterialLot,
    MaterialLotConsumption,
    ProductionLot,
    ReceiptLotAllocation,
    Supplier,
)

POSTGRES_DSN = os.environ.get("HYC_P3_TEST_POSTGRES_DSN") or os.environ.get(
    "HYC_P2_TEST_POSTGRES_DSN"
)
pytestmark = pytest.mark.postgres

_DOMAIN_INVARIANT_SQLSTATE = "P0001"


@pytest.fixture(scope="module")
def engine() -> Engine:
    if not POSTGRES_DSN:
        pytest.skip("HYC_P3_TEST_POSTGRES_DSN must name a disposable PostgreSQL database")
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


def _sqlstate(error: DBAPIError) -> str | None:
    original = getattr(error, "orig", None)
    return getattr(original, "sqlstate", None) or getattr(original, "pgcode", None)


def _seed_materials(session: Session) -> tuple[Material, Material]:
    m1 = Material(
        id=uuid4(),
        material_code=f"MAT-P7-{uuid4().hex[:8]}",
        name="Parent Resin",
        default_unit="KG",
    )
    m2 = Material(
        id=uuid4(),
        material_code=f"MAT-P7-{uuid4().hex[:8]}",
        name="Additive Component",
        default_unit="KG",
    )
    session.add_all([m1, m2])
    session.commit()
    return m1, m2


def test_self_referencing_bom_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        m1, _ = _seed_materials(session)
        bom = BillOfMaterial(
            id=uuid4(),
            parent_material_id=m1.id,
            component_material_id=m1.id,  # Self reference
            quantity=Decimal("1.5"),
            unit="KG",
        )
        session.add(bom)
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()


def test_duplicate_parent_component_pair_is_rejected(engine: Engine) -> None:
    with Session(engine) as session:
        m1, m2 = _seed_materials(session)
        b1 = BillOfMaterial(
            id=uuid4(),
            parent_material_id=m1.id,
            component_material_id=m2.id,
            quantity=Decimal("2.0"),
            unit="KG",
        )
        session.add(b1)
        session.commit()

        b2 = BillOfMaterial(
            id=uuid4(),
            parent_material_id=m1.id,
            component_material_id=m2.id,  # Duplicate pair
            quantity=Decimal("3.0"),
            unit="KG",
        )
        session.add(b2)
        with pytest.raises(DBAPIError):
            session.commit()
        session.rollback()


def _seed_consumption(session: Session) -> tuple[ProductionLot, MaterialLotConsumption]:
    sup = Supplier(supplier_code=f"SUP-{uuid4().hex[:8]}", name="Supplier P7")
    mat = Material(material_code=f"MAT-{uuid4().hex[:8]}", name="Raw Material P7")
    session.add_all([sup, mat])
    session.flush()

    mlot = MaterialLot(
        supplier_id=sup.id,
        material_id=mat.id,
        identity_policy_version="v1",
        identity_key=f"KEY-{uuid4().hex[:8]}",
        identity_status="CANONICAL",
    )
    receipt = InboundReceipt(
        inbound_no=f"INB-{uuid4().hex[:8]}",
        supplier_id=sup.id,
        receipt_date=date(2026, 8, 13),
        status="RECEIVED",
    )
    session.add_all([mlot, receipt])
    session.flush()

    alloc = ReceiptLotAllocation(
        inbound_receipt_id=receipt.id,
        material_lot_id=mlot.id,
        quantity=Decimal("100.00"),
        quantity_unit="KG",
    )
    prod = ProductionLot(
        production_lot_no=f"PROD-{uuid4().hex[:8]}",
        product_material_id=mat.id,
        produced_on=date(2026, 8, 13),
        quantity=Decimal("80.00"),
        unit="KG",
        status="PRODUCED",
    )
    session.add_all([alloc, prod])
    session.flush()

    consumption = MaterialLotConsumption(
        id=uuid4(),
        receipt_lot_allocation_id=alloc.id,
        production_lot_id=prod.id,
        consumed_quantity=Decimal("20.00"),
        consumed_unit="KG",
    )
    session.add(consumption)
    session.commit()
    return prod, consumption


def test_consumption_update_raises_p0001(engine: Engine) -> None:
    with Session(engine) as session:
        _, consumption = _seed_consumption(session)
        with pytest.raises(DBAPIError) as caught:
            session.execute(
                text(
                    "UPDATE material_lot_consumptions SET consumed_quantity = 50.00 "
                    "WHERE id = :id"
                ),
                {"id": consumption.id},
            )
        session.rollback()
        assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE


def test_consumption_delete_raises_p0001(engine: Engine) -> None:
    with Session(engine) as session:
        _, consumption = _seed_consumption(session)
        with pytest.raises(DBAPIError) as caught:
            session.execute(
                text("DELETE FROM material_lot_consumptions WHERE id = :id"),
                {"id": consumption.id},
            )
        session.rollback()
        assert _sqlstate(caught.value) == _DOMAIN_INVARIANT_SQLSTATE
