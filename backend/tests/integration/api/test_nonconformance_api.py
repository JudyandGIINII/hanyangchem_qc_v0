from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hyc_data.models import NonconformanceDisposition

pytestmark = pytest.mark.postgres


def _create_nonconformance(p3, *, disposition_id: str, suffix: str | None = None):
    marker = suffix or uuid4().hex
    inspection = p3.reviewed(suffix=f"ncr-{marker}")
    body = {
        "ncr_number": f"NCR-{marker}",
        "inspection_case_id": inspection["inspection_id"],
        "quantity": "1.00",
        "description": f"synthetic nonconformance {marker}",
        "disposition_id": disposition_id,
    }
    response = p3.client.post("/api/v1/nonconformances", json=body, headers=p3.inspector)
    assert response.status_code == 201, response.text
    return response.json(), body


def _dispositions(p3, *, include_inactive: bool = False) -> list[dict[str, object]]:
    response = p3.client.get(
        "/api/v1/nonconformance-dispositions",
        params={"include_inactive": include_inactive},
        headers=p3.inspector,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_disposition_list_and_snapshot_preserve_historical_master_meaning(p3) -> None:
    disposition = _dispositions(p3)[0]
    created, _ = _create_nonconformance(p3, disposition_id=str(disposition["id"]))
    assert created["disposition_snapshot"] == {
        "code": disposition["code"],
        "name": disposition["name"],
    }

    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            row = session.get(NonconformanceDisposition, UUID(str(disposition["id"])))
            assert row is not None
            row.name = "renamed synthetic disposition"
            row.active = False
            session.commit()
    finally:
        engine.dispose()

    default_ids = {value["id"] for value in _dispositions(p3)}
    all_ids = {value["id"] for value in _dispositions(p3, include_inactive=True)}
    assert disposition["id"] not in default_ids
    assert disposition["id"] in all_ids

    fetched = p3.client.get(f"/api/v1/nonconformances/{created['id']}", headers=p3.inspector)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["disposition_snapshot"] == {
        "code": disposition["code"],
        "name": disposition["name"],
    }


def test_non_lead_is_refused_for_approve_and_reject(p3) -> None:
    disposition = _dispositions(p3, include_inactive=True)[0]
    created, _ = _create_nonconformance(p3, disposition_id=str(disposition["id"]))
    for endpoint, headers in (("approve", p3.admin), ("reject", p3.inspector)):
        response = p3.client.post(
            f"/api/v1/nonconformances/{created['id']}/{endpoint}",
            headers=headers | {"If-Match": str(created["lock_version"])},
        )
        assert response.status_code == 403, response.text


def test_approved_nonconformance_update_is_a_clean_conflict(p3) -> None:
    disposition = _dispositions(p3, include_inactive=True)[0]
    created, body = _create_nonconformance(p3, disposition_id=str(disposition["id"]))
    approved = p3.client.post(
        f"/api/v1/nonconformances/{created['id']}/approve",
        headers=p3.lead | {"If-Match": str(created["lock_version"])},
    )
    assert approved.status_code == 200, approved.text

    current = p3.client.get(f"/api/v1/nonconformances/{created['id']}", headers=p3.inspector)
    assert current.status_code == 200, current.text
    blocked = p3.client.put(
        f"/api/v1/nonconformances/{created['id']}",
        json=body | {"description": "attempted mutation"},
        headers=p3.inspector | {"If-Match": str(current.json()["lock_version"])},
    )
    assert blocked.status_code == 409, blocked.text
    assert blocked.json()["code"] == "HTTP_ERROR"
    assert blocked.json()["message"] == "Nonconformance data conflicts with existing record"


def test_nonconformance_stale_lock_version_returns_conflict(p3) -> None:
    disposition = _dispositions(p3, include_inactive=True)[0]
    created, body = _create_nonconformance(p3, disposition_id=str(disposition["id"]))
    updated_body = body | {"description": "updated synthetic nonconformance"}
    updated = p3.client.put(
        f"/api/v1/nonconformances/{created['id']}",
        json=updated_body,
        headers=p3.inspector | {"If-Match": str(created["lock_version"])},
    )
    assert updated.status_code == 200, updated.text

    stale = p3.client.put(
        f"/api/v1/nonconformances/{created['id']}",
        json=updated_body,
        headers=p3.inspector | {"If-Match": str(created["lock_version"])},
    )
    assert stale.status_code == 409, stale.text
    assert stale.json()["message"] == "Stale nonconformance version"
