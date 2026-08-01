from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.postgres


def test_approval_fault_rolls_back_and_replay_has_one_effect(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    ready = p3.clear_hold(inspection_id)
    submitted = p3.submit(inspection_id, ready["version"])
    failed = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/approvals",
        json={"action": "APPROVE", "reason": None},
        headers=p3.lead
        | {
            "If-Match": str(submitted["version"]),
            "Idempotency-Key": f"fault-{inspection_id}",
            "X-P3-Fault-At": "after-outbox",
        },
    )
    assert failed.status_code == 500
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        counts = {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE inspection_case_id = :id"),
                {"id": inspection_id},
            ).scalar_one()
            for table in ("approvals", "decision_snapshots")
        }
        audit = connection.execute(
            text("SELECT count(*) FROM audit_logs WHERE entity_id = :id AND action = 'FINALIZE'"),
            {"id": inspection_id},
        ).scalar_one()
        outbox = connection.execute(
            text("SELECT count(*) FROM outbox_events WHERE payload->>'inspection_case_id' = :id"),
            {"id": inspection_id},
        ).scalar_one()
        idempotency = connection.execute(
            text(
                "SELECT count(*) FROM idempotency_keys "
                "WHERE scope = :scope AND key = :key"
            ),
            {
                "scope": f"p3.inspections.{inspection_id}.approval",
                "key": f"fault-{inspection_id}",
            },
        ).scalar_one()
    assert counts == {"approvals": 0, "decision_snapshots": 0}
    assert (audit, outbox, idempotency) == (0, 0, 0)

    success = p3.approve(inspection_id, submitted["version"], key=f"ok-{inspection_id}")
    assert success.status_code == 200
    replay = p3.approve(inspection_id, submitted["version"], key=f"ok-{inspection_id}")
    assert replay.status_code == 200
    with engine.connect() as connection:
        assert {
            table: connection.execute(
                text(f"SELECT count(*) FROM {table} WHERE inspection_case_id = :id"),
                {"id": inspection_id},
            ).scalar_one()
            for table in ("approvals", "decision_snapshots")
        } == {"approvals": 1, "decision_snapshots": 1}
        assert connection.execute(
            text(
                "SELECT count(*) FROM idempotency_keys "
                "WHERE scope = :scope AND key = :key AND state = 'COMPLETED'"
            ),
            {
                "scope": f"p3.inspections.{inspection_id}.approval",
                "key": f"ok-{inspection_id}",
            },
        ).scalar_one() == 1
    engine.dispose()
