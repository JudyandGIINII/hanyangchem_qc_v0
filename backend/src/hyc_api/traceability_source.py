"""P7 seam: load the traceability graph out of the database for the pure traversal.

This is the only place the ORM and `hyc_domain.traceability` meet.  The traversal
itself stays free of infrastructure so it can be reasoned about and tested without
a database; this module does the reading and nothing else.

Gated off by default.  `traceability_enabled` is false unless an operator turns it
on, and with it off no table is read at all — the same condition the P6 ingestion
seam holds itself to.  Turning it on grants no ERP access: nothing here calls an
external system, and production lots and consumptions are whatever has been
recorded locally.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_data.models import MaterialLotConsumption, ProductionLot, ReceiptLotAllocation
from hyc_domain.traceability import Consumption
from hyc_domain.traceability import ProductionLot as DomainProductionLot


@dataclass(frozen=True, slots=True)
class TraceabilityGraph:
    """Exactly the inputs the pure traversal needs, and nothing more."""

    allocations: dict[str, str]
    consumptions: tuple[Consumption, ...]
    production_lots: tuple[DomainProductionLot, ...]
    enabled: bool


def load_traceability_graph(session: Session, *, enabled: bool) -> TraceabilityGraph:
    if not enabled:
        # Return empty without touching a table: the flag must mean "off", not
        # "on but filtered", or the seam has a live path nobody asked for.
        return TraceabilityGraph({}, (), (), enabled=False)

    allocations = {
        str(allocation_id): str(material_lot_id)
        for allocation_id, material_lot_id in session.execute(
            select(ReceiptLotAllocation.id, ReceiptLotAllocation.material_lot_id).order_by(
                ReceiptLotAllocation.id
            )
        ).tuples()
    }
    consumptions = tuple(
        Consumption(
            allocation_id=str(allocation_id),
            production_lot_id=str(production_lot_id),
            quantity=quantity,
        )
        for allocation_id, production_lot_id, quantity in session.execute(
            select(
                MaterialLotConsumption.receipt_lot_allocation_id,
                MaterialLotConsumption.production_lot_id,
                MaterialLotConsumption.consumed_quantity,
            ).order_by(
                MaterialLotConsumption.production_lot_id,
                MaterialLotConsumption.receipt_lot_allocation_id,
            )
        ).tuples()
    )
    production_lots = tuple(
        DomainProductionLot(
            production_lot_id=str(lot_id),
            product_material_id=str(product_material_id),
            produced_on=produced_on,
        )
        for lot_id, product_material_id, produced_on in session.execute(
            select(
                ProductionLot.id, ProductionLot.product_material_id, ProductionLot.produced_on
            ).order_by(ProductionLot.produced_on, ProductionLot.id)
        ).tuples()
    )
    return TraceabilityGraph(allocations, consumptions, production_lots, enabled=True)
