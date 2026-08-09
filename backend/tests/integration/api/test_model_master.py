from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hyc_data.models import MaterialModel

pytestmark = pytest.mark.postgres


def test_model_master_create_list_get_update_stale_and_soft_delete(p3) -> None:
    marker = uuid4().hex
    body = {
        "material_id": p3.context["material_id"],
        "model_code": f"MOD-{marker}",
        "name": f"Model {marker}",
    }
    created = p3.client.post("/api/v1/material-models", json=body, headers=p3.admin)
    assert created.status_code == 201, created.text
    model = created.json()
    assert model["lock_version"] == 1

    listed = p3.client.get("/api/v1/material-models", headers=p3.admin)
    assert listed.status_code == 200, listed.text
    assert model["id"] in {item["id"] for item in listed.json()}

    fetched = p3.client.get(f"/api/v1/material-models/{model['id']}", headers=p3.admin)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == model

    changed_body = body | {"name": f"Updated model {marker}"}
    updated = p3.client.put(
        f"/api/v1/material-models/{model['id']}",
        json=changed_body,
        headers=p3.admin | {"If-Match": str(model["lock_version"])},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["lock_version"] == 2

    stale = p3.client.put(
        f"/api/v1/material-models/{model['id']}",
        json=changed_body,
        headers=p3.admin | {"If-Match": str(model["lock_version"])},
    )
    assert stale.status_code == 409
    assert stale.json()["message"] == "Stale master-data version"

    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            row = session.get(MaterialModel, UUID(model["id"]))
            assert row is not None
            row.deleted_at = datetime.now(UTC)
            session.commit()
    finally:
        engine.dispose()

    excluded = p3.client.get("/api/v1/material-models", headers=p3.admin)
    assert model["id"] not in {item["id"] for item in excluded.json()}
