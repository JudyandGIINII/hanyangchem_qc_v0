from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from hyc_data.models import InspectionReturnReason, SupplierResult
from hyc_data.p3_fixture_seed import PURITY_ITEM_ID

pytestmark = pytest.mark.postgres


def _alias_body(p3, *, alias_text: str, priority: int, supplier_id: str | None = None):
    return {
        "standard_test_item_id": str(PURITY_ITEM_ID),
        "alias_text": alias_text,
        "supplier_id": supplier_id,
        "priority": priority,
    }


def _create_alias(p3, body: dict[str, object]) -> dict[str, object]:
    response = p3.client.post("/api/v1/standard-test-item-aliases", json=body, headers=p3.admin)
    assert response.status_code == 201, response.text
    return response.json()


def test_alias_scope_uniqueness_and_lookup_order_are_deterministic(p3) -> None:
    marker = uuid4().hex
    alias_text = f"supplier-purity-{marker}"
    general = _alias_body(p3, alias_text=alias_text, priority=20)
    _create_alias(p3, general)

    duplicate = p3.client.post(
        "/api/v1/standard-test-item-aliases", json=general, headers=p3.admin
    )
    assert duplicate.status_code == 409, duplicate.text

    scoped = _create_alias(
        p3,
        _alias_body(
            p3,
            alias_text=alias_text,
            priority=10,
            supplier_id=str(p3.context["supplier_id"]),
        ),
    )
    assert scoped["supplier_id"] == p3.context["supplier_id"]

    lookup = p3.client.get(
        "/api/v1/standard-test-item-aliases/lookup",
        params={"alias_text": alias_text, "supplier_id": p3.context["supplier_id"]},
        headers=p3.inspector,
    )
    assert lookup.status_code == 200, lookup.text
    assert [value["priority"] for value in lookup.json()] == [10, 20]
    assert len(lookup.json()) == 2


def test_alias_lookup_never_auto_confirms_a_supplier_mapping(p3) -> None:
    marker = uuid4().hex
    alias_text = f"unmapped-alias-{marker}"
    _create_alias(p3, _alias_body(p3, alias_text=alias_text, priority=1))
    inspection = p3.reviewed(suffix=f"alias-{marker}")

    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            result = SupplierResult(
                inspection_case_id=UUID(str(inspection["inspection_id"])),
                standard_test_item_id=None,
                supplier_item_name=alias_text,
                mapping_status="UNMAPPED",
            )
            session.add(result)
            session.commit()
            result_id = result.id

        lookup = p3.client.get(
            "/api/v1/standard-test-item-aliases/lookup",
            params={"alias_text": alias_text},
            headers=p3.inspector,
        )
        assert lookup.status_code == 200, lookup.text
        assert len(lookup.json()) == 1

        with Session(engine) as session:
            persisted = session.get(SupplierResult, result_id)
            assert persisted is not None
            assert persisted.mapping_status == "UNMAPPED"
            assert persisted.standard_test_item_id is None
    finally:
        engine.dispose()


def test_return_requires_reason_and_lead_then_preserves_each_return_history_row(p3) -> None:
    inspection = p3.reviewed(suffix=f"return-{uuid4().hex}")
    cleared = p3.clear_hold(str(inspection["inspection_id"]))
    submitted = p3.submit(str(inspection["inspection_id"]), int(cleared["version"]))
    return_url = f"/api/v1/inspections/{inspection['inspection_id']}/return"

    missing = p3.client.post(
        return_url,
        json={},
        headers=p3.lead | {"If-Match": str(submitted["version"])},
    )
    assert missing.status_code == 422, missing.text

    forbidden = p3.client.post(
        return_url,
        json={"reason": "synthetic correction requested"},
        headers=p3.admin | {"If-Match": str(submitted["version"])},
    )
    assert forbidden.status_code == 403, forbidden.text

    first = p3.client.post(
        return_url,
        json={"reason": "first synthetic correction requested"},
        headers=p3.lead | {"If-Match": str(submitted["version"])},
    )
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "RETURNED"

    resubmitted = p3.submit(str(inspection["inspection_id"]), int(first.json()["version"]))
    second = p3.client.post(
        return_url,
        json={"reason": "second synthetic correction requested"},
        headers=p3.lead | {"If-Match": str(resubmitted["version"])},
    )
    assert second.status_code == 200, second.text
    assert second.json()["status"] == "RETURNED"

    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            history = session.scalars(
                select(InspectionReturnReason)
                .where(
                    InspectionReturnReason.inspection_case_id
                    == UUID(str(inspection["inspection_id"]))
                )
                .order_by(InspectionReturnReason.created_at, InspectionReturnReason.id)
            ).all()
    finally:
        engine.dispose()
    assert [row.reason for row in history] == [
        "first synthetic correction requested",
        "second synthetic correction requested",
    ]
