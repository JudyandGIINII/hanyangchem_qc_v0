from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = pytest.mark.postgres


def test_split_receipts_share_canonical_lot_and_trace_is_ordered(p3) -> None:
    marker = uuid4().hex
    shared_lot = f"P3-SPLIT-{marker}"

    def create(receipt: str, quantity: str):
        body = {
            "supplier_id": p3.context["supplier_id"],
            "material_id": p3.context["material_id"],
            "model_id": p3.context["model_id"],
            "inbound_no": receipt,
            "receipt_date": "2026-08-01",
            "supplier_lot_no": shared_lot,
            "quantity": quantity,
            "quantity_unit": "kg",
        }
        response = p3.client.post(
            "/api/v1/intakes",
            json=body,
            headers=p3.inspector | {"Idempotency-Key": receipt},
        )
        assert response.status_code == 201, response.text
        return response.json()

    first = create(f"P3-SPLIT-A-{marker}", "40.00")
    second = create(f"P3-SPLIT-B-{marker}", "60.00")
    assert first["material_lot_id"] == second["material_lot_id"]
    assert first["allocation_id"] != second["allocation_id"]
    trace = p3.client.get(
        f"/api/v1/lots/{first['material_lot_id']}/trace", headers=p3.inspector
    )
    assert trace.status_code == 200, trace.text
    assert [item["quantity"] for item in trace.json()["allocations"]] == [
        "40.000000000000",
        "60.000000000000",
    ]
    assert len(trace.json()["receipts"]) == 2
