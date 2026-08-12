"""Pure, deterministic traversal of material-LOT consumption relationships."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BomEdge:
    parent_material_id: str
    component_material_id: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class Consumption:
    allocation_id: str
    production_lot_id: str
    quantity: Decimal


@dataclass(frozen=True, slots=True)
class ProductionLot:
    production_lot_id: str
    product_material_id: str
    produced_on: date


def _production_lot_key(production_lot: ProductionLot) -> tuple[date, str, str]:
    return (
        production_lot.produced_on,
        production_lot.product_material_id,
        production_lot.production_lot_id,
    )


def _sources(
    allocations: Mapping[str, str],
    consumptions: Sequence[Consumption],
    production_lots: Sequence[ProductionLot],
) -> tuple[dict[str, tuple[str, ...]], dict[str, tuple[ProductionLot, ...]]]:
    allocation_ids_by_lot: dict[str, list[str]] = defaultdict(list)
    for allocation_id, material_lot_id in allocations.items():
        allocation_ids_by_lot[material_lot_id].append(allocation_id)

    lots_by_id: dict[str, ProductionLot] = {}
    for known_lot in sorted(production_lots, key=_production_lot_key):
        lots_by_id.setdefault(known_lot.production_lot_id, known_lot)

    consumed_lots_by_allocation: dict[str, list[ProductionLot]] = defaultdict(list)
    for consumption in consumptions:
        matched_lot = lots_by_id.get(consumption.production_lot_id)
        if matched_lot is not None:
            consumed_lots_by_allocation[consumption.allocation_id].append(matched_lot)

    return (
        {lot_id: tuple(sorted(ids)) for lot_id, ids in allocation_ids_by_lot.items()},
        {
            allocation_id: tuple(sorted(lots, key=_production_lot_key))
            for allocation_id, lots in consumed_lots_by_allocation.items()
        },
    )


def _directly_consumed_lots(
    material_lot_id: str,
    allocation_ids_by_lot: Mapping[str, Sequence[str]],
    consumed_lots_by_allocation: Mapping[str, Sequence[ProductionLot]],
) -> tuple[ProductionLot, ...]:
    lots_by_id: dict[str, ProductionLot] = {}
    for allocation_id in allocation_ids_by_lot.get(material_lot_id, ()):
        for production_lot in consumed_lots_by_allocation.get(allocation_id, ()):
            lots_by_id.setdefault(production_lot.production_lot_id, production_lot)
    return tuple(sorted(lots_by_id.values(), key=_production_lot_key))


def trace_forward(
    material_lot_id: str,
    allocations: Mapping[str, str],
    consumptions: Sequence[Consumption],
    production_lots: Sequence[ProductionLot],
) -> tuple[ProductionLot, ...]:
    """Return, in deterministic order, the production lots directly consuming a LOT."""

    allocation_ids_by_lot, consumed_lots_by_allocation = _sources(
        allocations, consumptions, production_lots
    )
    return _directly_consumed_lots(
        material_lot_id, allocation_ids_by_lot, consumed_lots_by_allocation
    )


def impact_scope(
    material_lot_id: str,
    allocations: Mapping[str, str],
    consumptions: Sequence[Consumption],
    production_lots: Sequence[ProductionLot],
) -> tuple[ProductionLot, ...]:
    """Return all downstream production lots, safely bounded even for cycles.

    A production lot becomes a possible later material-LOT identifier when it
    appears as an allocation target. The visited set is keyed by that LOT ID,
    so a malformed cycle can never recurse or emit a node more than once.
    """

    allocation_ids_by_lot, consumed_lots_by_allocation = _sources(
        allocations, consumptions, production_lots
    )
    visited_lot_ids = {material_lot_id}
    pending_lot_ids: deque[str] = deque([material_lot_id])
    impacted_by_id: dict[str, ProductionLot] = {}

    while pending_lot_ids:
        current_lot_id = pending_lot_ids.popleft()
        for production_lot in _directly_consumed_lots(
            current_lot_id, allocation_ids_by_lot, consumed_lots_by_allocation
        ):
            if production_lot.production_lot_id not in impacted_by_id:
                impacted_by_id[production_lot.production_lot_id] = production_lot
            next_lot_id = production_lot.production_lot_id
            if next_lot_id not in visited_lot_ids:
                visited_lot_ids.add(next_lot_id)
                pending_lot_ids.append(next_lot_id)

    return tuple(sorted(impacted_by_id.values(), key=_production_lot_key))
