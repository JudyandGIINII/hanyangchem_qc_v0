from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from hyc_data.models import Nonconformance

pytestmark = pytest.mark.postgres


def _create_and_approve_ncr(p3) -> dict[str, object]:
    dispositions = p3.client.get(
        "/api/v1/nonconformance-dispositions", headers=p3.inspector
    ).json()
    disp_id = dispositions[0]["id"]
    marker = uuid4().hex
    inspection = p3.reviewed(suffix=f"ncr-{marker}")
    body = {
        "ncr_number": f"NCR-{marker}",
        "inspection_case_id": inspection["inspection_id"],
        "quantity": "1.00",
        "description": f"synthetic nonconformance {marker}",
        "disposition_id": disp_id,
    }
    res = p3.client.post("/api/v1/nonconformances", json=body, headers=p3.inspector)
    assert res.status_code == 201, res.text
    ncr = res.json()

    # Approve NCR
    app_res = p3.client.post(
        f"/api/v1/nonconformances/{ncr['id']}/approve",
        headers={**p3.lead, "If-Match": str(ncr["lock_version"])},
    )
    assert app_res.status_code == 200, app_res.text

    # Fetch approved NCR
    approved_res = p3.client.get(
        f"/api/v1/nonconformances/{ncr['id']}", headers=p3.inspector
    )
    assert approved_res.status_code == 200
    assert approved_res.json()["status"] == "APPROVED"
    return approved_res.json()


def test_approved_ncr_adding_action_succeeds_and_leaves_ncr_row_unchanged(p3) -> None:
    """CRITICAL REGRESSION: Adding actions to an APPROVED nonconformance MUST succeed
    and MUST leave the nonconformances row byte-identical.
    """
    ncr = _create_and_approve_ncr(p3)
    ncr_id = ncr["id"]

    # Read DB row directly before action
    engine = create_engine(p3.database_url)
    try:
        with Session(engine) as session:
            before_row = session.get(Nonconformance, UUID(str(ncr_id)))
            assert before_row is not None
            assert before_row.status == "APPROVED"
            before_lock_version = before_row.lock_version
            before_updated_at = before_row.updated_at
            before_status = before_row.status
            before_description = before_row.description

        # Post action as INSPECTOR (CORRECTIVE)
        action_body = {
            "action_type": "CORRECTIVE",
            "description": "Cleaned chemical residue and recalibrated feed valve",
            "result": "Flow rate restored to baseline",
        }
        res = p3.client.post(
            f"/api/v1/nonconformances/{ncr_id}/actions",
            json=action_body,
            headers=p3.inspector,
        )
        assert res.status_code == 201, res.text
        created_action = res.json()
        assert created_action["action_type"] == "CORRECTIVE"
        assert created_action["actor_role"] == "INSPECTOR"

        # Post completion action as LEAD (COMPLETION)
        completion_body = {
            "action_type": "COMPLETION",
            "description": "Verified follow-up actions and signed off",
            "result": "Complete",
        }
        comp_res = p3.client.post(
            f"/api/v1/nonconformances/{ncr_id}/actions",
            json=completion_body,
            headers=p3.lead,
        )
        assert comp_res.status_code == 201, comp_res.text

        # Verify nonconformance row remains 100% byte-identical
        with Session(engine) as session:
            after_row = session.get(Nonconformance, UUID(str(ncr_id)))
            assert after_row is not None
            assert after_row.lock_version == before_lock_version
            assert after_row.updated_at == before_updated_at
            assert after_row.status == before_status
            assert after_row.description == before_description
    finally:
        engine.dispose()


def test_empty_description_action_is_rejected(p3) -> None:
    ncr = _create_and_approve_ncr(p3)
    ncr_id = ncr["id"]

    res = p3.client.post(
        f"/api/v1/nonconformances/{ncr_id}/actions",
        json={"action_type": "CORRECTIVE", "description": "   "},
        headers=p3.inspector,
    )
    assert res.status_code == 422


def test_non_lead_completion_action_returns_403(p3) -> None:
    ncr = _create_and_approve_ncr(p3)
    ncr_id = ncr["id"]

    res = p3.client.post(
        f"/api/v1/nonconformances/{ncr_id}/actions",
        json={"action_type": "COMPLETION", "description": "Unauthorized completion attempt"},
        headers=p3.inspector,  # INSPECTOR is not LEAD
    )
    assert res.status_code == 403


def test_action_list_ordering_is_deterministic(p3) -> None:
    ncr = _create_and_approve_ncr(p3)
    ncr_id = ncr["id"]

    act1 = {
        "action_type": "CORRECTIVE",
        "description": "First action",
        "performed_at": "2026-08-12T10:00:00Z",
    }
    act2 = {
        "action_type": "PREVENTIVE",
        "description": "Second action earlier in time",
        "performed_at": "2026-08-12T08:00:00Z",
    }
    act3 = {
        "action_type": "VERIFICATION",
        "description": "Third action middle in time",
        "performed_at": "2026-08-12T09:00:00Z",
    }

    for act in [act1, act2, act3]:
        p3.client.post(
            f"/api/v1/nonconformances/{ncr_id}/actions",
            json=act,
            headers=p3.inspector,
        )

    get_res = p3.client.get(
        f"/api/v1/nonconformances/{ncr_id}/actions",
        headers=p3.inspector,
    )
    assert get_res.status_code == 200
    actions = get_res.json()
    assert len(actions) == 3
    assert actions[0]["description"] == "Second action earlier in time"
    assert actions[1]["description"] == "Third action middle in time"
    assert actions[2]["description"] == "First action"
