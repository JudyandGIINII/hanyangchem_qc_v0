from __future__ import annotations

from datetime import date
from decimal import Decimal

from hyc_domain.traceability import Consumption, ProductionLot, impact_scope, trace_forward


def _production_lot(identifier: str, produced_on: date) -> ProductionLot:
    return ProductionLot(
        production_lot_id=identifier,
        product_material_id=f"product-{identifier}",
        produced_on=produced_on,
    )


def _consumption(allocation_id: str, production_lot_id: str) -> Consumption:
    return Consumption(
        allocation_id=allocation_id,
        production_lot_id=production_lot_id,
        quantity=Decimal("1.25"),
    )


def test_unknown_material_lot_has_an_empty_forward_trace_and_impact_scope() -> None:
    production_lots = [_production_lot("product-lot-1", date(2026, 8, 1))]
    consumptions = [_consumption("allocation-1", "product-lot-1")]

    assert trace_forward("unknown", {"allocation-1": "known"}, consumptions, production_lots) == ()
    assert impact_scope("unknown", {"allocation-1": "known"}, consumptions, production_lots) == ()


def test_trace_forward_returns_every_direct_consumer_in_explicit_order() -> None:
    later = _production_lot("product-lot-later", date(2026, 8, 2))
    earlier = _production_lot("product-lot-earlier", date(2026, 8, 1))

    result = trace_forward(
        "raw-lot",
        {"allocation-b": "raw-lot", "allocation-a": "raw-lot"},
        [
            _consumption("allocation-b", later.production_lot_id),
            _consumption("allocation-a", earlier.production_lot_id),
        ],
        [later, earlier],
    )

    assert result == (earlier, later)


def test_impact_scope_follows_a_chain_of_depth_three() -> None:
    first = _production_lot("lot-1", date(2026, 8, 1))
    second = _production_lot("lot-2", date(2026, 8, 2))
    third = _production_lot("lot-3", date(2026, 8, 3))

    result = impact_scope(
        "raw-lot",
        {
            "allocation-raw": "raw-lot",
            "allocation-first": first.production_lot_id,
            "allocation-second": second.production_lot_id,
        },
        [
            _consumption("allocation-raw", first.production_lot_id),
            _consumption("allocation-first", second.production_lot_id),
            _consumption("allocation-second", third.production_lot_id),
        ],
        [third, first, second],
    )

    assert result == (first, second, third)


def test_cyclic_graph_regression_terminates_without_revisiting_lots() -> None:
    first = _production_lot("lot-1", date(2026, 8, 1))
    second = _production_lot("lot-2", date(2026, 8, 2))

    result = impact_scope(
        "raw-lot",
        {
            "allocation-raw": "raw-lot",
            "allocation-first": first.production_lot_id,
            "allocation-second": second.production_lot_id,
        },
        [
            _consumption("allocation-raw", first.production_lot_id),
            _consumption("allocation-first", second.production_lot_id),
            _consumption("allocation-second", first.production_lot_id),
        ],
        [second, first],
    )

    assert result == (first, second)
