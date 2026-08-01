from __future__ import annotations

import pytest

pytestmark = pytest.mark.postgres


def test_internal_substitute_hold_blocks_then_clears(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    held = p3.client.get(f"/api/v1/inspections/{inspection_id}", headers=p3.inspector)
    assert held.json()["candidate_decision"] == "ON_HOLD"
    assert "INTERNAL_TEST_PENDING" in held.json()["blockers"]
    blocked = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/submit",
        headers=p3.inspector | {"If-Match": str(held.json()["version"])},
    )
    assert blocked.status_code == 422
    cleared = p3.clear_hold(inspection_id)
    assert cleared["candidate_decision"] == "ACCEPTED"
    assert cleared["blockers"] == []
    assert p3.submit(inspection_id, cleared["version"])["status"] == "LEAD_REVIEW"
