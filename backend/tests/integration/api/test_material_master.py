from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hyc_data.models import Material

pytestmark = pytest.mark.postgres


def test_material_master_create_list_get_update_stale_and_soft_delete(p3) -> None:
    marker = uuid4().hex
    body = {
        "material_code": f"MAT-{marker}",
        "name": f"Material {marker}",
        "default_unit": "kg",
        "active": True,
    }
    created = p3.client.post("/api/v1/materials", json=body, headers=p3.admin)
    assert created.status_code == 201, created.text
    material = created.json()
    assert material["lock_version"] == 1

    listed = p3.client.get("/api/v1/materials", headers=p3.admin)
    assert listed.status_code == 200, listed.text
    assert material["id"] in {item["id"] for item in listed.json()}

    fetched = p3.client.get(f"/api/v1/materials/{material['id']}", headers=p3.admin)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json() == material

    changed_body = body | {"name": f"Updated material {marker}", "default_unit": "g"}
    updated = p3.client.put(
        f"/api/v1/materials/{material['id']}",
        json=changed_body,
        headers=p3.admin | {"If-Match": str(material["lock_version"])},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["lock_version"] == 2

    stale = p3.client.put(
        f"/api/v1/materials/{material['id']}",
        json=changed_body,
        headers=p3.admin | {"If-Match": str(material["lock_version"])},
    )
    assert stale.status_code == 409
    assert stale.json()["message"] == "Stale master-data version"

    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            row = session.get(Material, UUID(material["id"]))
            assert row is not None
            row.deleted_at = datetime.now(UTC)
            session.commit()
    finally:
        engine.dispose()

    excluded = p3.client.get("/api/v1/materials", headers=p3.admin)
    assert material["id"] not in {item["id"] for item in excluded.json()}
