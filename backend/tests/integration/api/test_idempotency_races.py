from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, text

pytestmark = pytest.mark.postgres


def _race_first_reservations(p3, requests: list[Callable[[], object]]):
    insert_barrier = Barrier(2)
    hit_lock = Lock()
    insert_hits = 0

    def synchronize_idempotency_inserts(
        _connection, _cursor, statement, _parameters, _context, _many
    ) -> None:
        nonlocal insert_hits
        if "INSERT INTO idempotency_keys" not in statement:
            return
        with hit_lock:
            insert_hits += 1
        insert_barrier.wait(timeout=10)

    event.listen(
        p3.client.app.state.engine,
        "before_cursor_execute",
        synchronize_idempotency_inserts,
    )
    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(request) for request in requests]
            responses = [future.result(timeout=30) for future in futures]
    finally:
        event.remove(
            p3.client.app.state.engine,
            "before_cursor_execute",
            synchronize_idempotency_inserts,
        )
    assert insert_hits == 2
    return responses


def _assert_race_contract(responses, *, success_status: int, conflict_message: str):
    assert sorted(response.status_code for response in responses) == sorted([409, success_status])
    winner = next(response for response in responses if response.status_code == success_status)
    loser = next(response for response in responses if response.status_code == 409)
    assert loser.json()["code"] == "HTTP_ERROR"
    assert loser.json()["message"] == conflict_message
    assert all(response.status_code != 500 for response in responses)
    return winner


def _assert_completed_reservation(p3, *, key: str, scope: str, winner) -> None:
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT state, response_status, response_body, resource_ref "
                "FROM idempotency_keys WHERE key = :key AND scope = :scope"
            ),
            {"key": key, "scope": scope},
        ).all()
    engine.dispose()
    assert len(rows) == 1
    assert rows[0].state == "COMPLETED"
    assert rows[0].response_status == winner.status_code
    assert json.loads(rows[0].response_body) == winner.json()
    assert rows[0].resource_ref


def _intake_body(p3, marker: str) -> dict[str, object]:
    return {
        "supplier_id": p3.context["supplier_id"],
        "material_id": p3.context["material_id"],
        "model_id": p3.context["model_id"],
        "inbound_no": f"P3-IDEM-IN-{marker}",
        "receipt_date": "2026-08-01",
        "supplier_lot_no": f"P3-IDEM-LOT-{marker}",
        "quantity": "100.00",
        "quantity_unit": "kg",
    }


@pytest.mark.parametrize("_attempt", range(5))
def test_concurrent_first_intake_reservation_same_payload_is_one_effect_and_409(
    p3, _attempt: int
) -> None:
    marker = uuid4().hex
    key = f"intake-race-{marker}"
    body = _intake_body(p3, marker)

    def request():
        return p3.client.post(
            "/api/v1/intakes",
            json=body,
            headers=p3.inspector | {"Idempotency-Key": key},
        )

    responses = _race_first_reservations(p3, [request, request])
    winner = _assert_race_contract(
        responses,
        success_status=201,
        conflict_message="Idempotency request is already pending",
    )
    replay = request()
    assert replay.status_code == 201
    assert replay.content == winner.content
    _assert_completed_reservation(p3, key=key, scope="p3.intakes", winner=winner)

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        receipt_id = connection.execute(
            text("SELECT id FROM inbound_receipts WHERE inbound_no = :inbound_no"),
            {"inbound_no": body["inbound_no"]},
        ).scalar_one()
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM material_lots "
                    "WHERE supplier_lot_no_raw = :supplier_lot_no"
                ),
                {"supplier_lot_no": body["supplier_lot_no"]},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM receipt_lot_allocations "
                    "WHERE inbound_receipt_id = :receipt"
                ),
                {"receipt": receipt_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE entity_id = :receipt AND action = 'P3_INTAKE_CREATED'"
                ),
                {"receipt": receipt_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_concurrent_first_intake_reservation_different_payload_is_one_effect_and_conflict(
    p3,
) -> None:
    marker = uuid4().hex
    key = f"intake-race-conflict-{marker}"
    bodies = [_intake_body(p3, f"{marker}-a"), _intake_body(p3, f"{marker}-b")]

    def request(index: int):
        return p3.client.post(
            "/api/v1/intakes",
            json=bodies[index],
            headers=p3.inspector | {"Idempotency-Key": key},
        )

    responses = _race_first_reservations(p3, [lambda: request(0), lambda: request(1)])
    winner = _assert_race_contract(
        responses,
        success_status=201,
        conflict_message="Idempotency key request conflict",
    )
    winning_index = responses.index(winner)
    replay = request(winning_index)
    assert replay.status_code == 201
    assert replay.content == winner.content
    _assert_completed_reservation(p3, key=key, scope="p3.intakes", winner=winner)

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        receipts = (
            connection.execute(
                text("SELECT id FROM inbound_receipts WHERE inbound_no IN (:first, :second)"),
                {
                    "first": bodies[0]["inbound_no"],
                    "second": bodies[1]["inbound_no"],
                },
            )
            .scalars()
            .all()
        )
        assert len(receipts) == 1
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM material_lots "
                    "WHERE supplier_lot_no_raw IN (:first, :second)"
                ),
                {
                    "first": bodies[0]["supplier_lot_no"],
                    "second": bodies[1]["supplier_lot_no"],
                },
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM receipt_lot_allocations "
                    "WHERE inbound_receipt_id = :receipt"
                ),
                {"receipt": receipts[0]},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE entity_id = :receipt AND action = 'P3_INTAKE_CREATED'"
                ),
                {"receipt": receipts[0]},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def test_unrelated_idempotency_integrity_error_is_not_mapped_or_partially_committed(p3) -> None:
    marker = uuid4().hex
    key = f"intake-unrelated-integrity-{marker}"
    body = _intake_body(p3, marker)
    corrupted_inserts = 0

    def violate_state_allowlist(_connection, _cursor, statement, parameters, _context, _many):
        nonlocal corrupted_inserts
        if "INSERT INTO idempotency_keys" not in statement:
            return statement, parameters
        corrupted_inserts += 1
        changed = dict(parameters)
        changed["state"] = "NOT_AN_ALLOWED_STATE"
        return statement, changed

    event.listen(
        p3.client.app.state.engine,
        "before_cursor_execute",
        violate_state_allowlist,
        retval=True,
    )
    try:
        response = p3.client.post(
            "/api/v1/intakes",
            json=body,
            headers=p3.inspector | {"Idempotency-Key": key},
        )
    finally:
        event.remove(
            p3.client.app.state.engine,
            "before_cursor_execute",
            violate_state_allowlist,
        )

    assert corrupted_inserts == 1
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "constraint" not in response.text.lower()
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM idempotency_keys WHERE key = :key"),
                {"key": key},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM inbound_receipts WHERE inbound_no = :inbound_no"),
                {"inbound_no": body["inbound_no"]},
            ).scalar_one()
            == 0
        )
    engine.dispose()


def _inspection_request(p3, *, reviewed: dict[str, object], key: str):
    return p3.client.post(
        "/api/v1/inspections",
        json={
            "allocation_id": reviewed["allocation_id"],
            "extraction_run_id": reviewed["run_id"],
        },
        headers=p3.inspector | {"Idempotency-Key": key},
    )


@pytest.mark.parametrize("_attempt", range(5))
def test_concurrent_first_inspection_reservation_same_payload_is_one_effect_and_409(
    p3, _attempt: int
) -> None:
    reviewed = p3.reviewed_extraction()
    key = f"inspection-race-{uuid4().hex}"

    def request():
        return _inspection_request(p3, reviewed=reviewed, key=key)

    responses = _race_first_reservations(p3, [request, request])
    winner = _assert_race_contract(
        responses,
        success_status=201,
        conflict_message="Idempotency request is already pending",
    )
    replay = request()
    assert replay.status_code == 201
    assert replay.content == winner.content
    _assert_completed_reservation(p3, key=key, scope="p3.inspections", winner=winner)

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        case_ids = (
            connection.execute(
                text(
                    "SELECT id FROM inspection_cases WHERE receipt_lot_allocation_id = :allocation"
                ),
                {"allocation": reviewed["allocation_id"]},
            )
            .scalars()
            .all()
        )
        assert case_ids == [UUID(winner.json()["inspection_id"])]
        assert (
            connection.execute(
                text("SELECT count(*) FROM supplier_results WHERE inspection_case_id = :case"),
                {"case": case_ids[0]},
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE entity_id = :case AND action = 'P3_INSPECTION_CREATED'"
                ),
                {"case": case_ids[0]},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM decision_snapshots WHERE inspection_case_id = :case"),
                {"case": case_ids[0]},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM approvals WHERE inspection_case_id = :case"),
                {"case": case_ids[0]},
            ).scalar_one()
            == 0
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE payload->>'inspection_case_id' = :case"
                ),
                {"case": str(case_ids[0])},
            ).scalar_one()
            == 0
        )
    engine.dispose()


def test_concurrent_first_inspection_reservation_different_payload_is_one_effect_and_conflict(
    p3,
) -> None:
    reviewed = [p3.reviewed_extraction(), p3.reviewed_extraction()]
    key = f"inspection-race-conflict-{uuid4().hex}"

    def request(index: int):
        return _inspection_request(p3, reviewed=reviewed[index], key=key)

    responses = _race_first_reservations(p3, [lambda: request(0), lambda: request(1)])
    winner = _assert_race_contract(
        responses,
        success_status=201,
        conflict_message="Idempotency key request conflict",
    )
    winning_index = responses.index(winner)
    replay = request(winning_index)
    assert replay.status_code == 201
    assert replay.content == winner.content
    _assert_completed_reservation(p3, key=key, scope="p3.inspections", winner=winner)

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        cases = connection.execute(
            text(
                "SELECT id, receipt_lot_allocation_id FROM inspection_cases "
                "WHERE receipt_lot_allocation_id IN (:first, :second)"
            ),
            {
                "first": reviewed[0]["allocation_id"],
                "second": reviewed[1]["allocation_id"],
            },
        ).all()
        assert len(cases) == 1
        assert str(cases[0].receipt_lot_allocation_id) == reviewed[winning_index]["allocation_id"]
        assert (
            connection.execute(
                text("SELECT count(*) FROM supplier_results WHERE inspection_case_id = :case"),
                {"case": cases[0].id},
            ).scalar_one()
            == 2
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE entity_id = :case AND action = 'P3_INSPECTION_CREATED'"
                ),
                {"case": cases[0].id},
            ).scalar_one()
            == 1
        )
    engine.dispose()


def _approval_request(p3, *, inspection_id: str, version: int, key: str, reason: str | None):
    return p3.client.post(
        f"/api/v1/inspections/{inspection_id}/approvals",
        json={"action": "APPROVE", "reason": reason},
        headers=p3.lead | {"If-Match": str(version), "Idempotency-Key": key},
    )


def _approval_ready(p3) -> tuple[str, int]:
    flow = p3.reviewed()
    ready = p3.clear_hold(flow["inspection_id"])
    submitted = p3.submit(flow["inspection_id"], ready["version"])
    return str(flow["inspection_id"]), int(submitted["version"])


@pytest.mark.parametrize("_attempt", range(5))
def test_concurrent_first_approval_reservation_same_payload_is_one_effect_and_409(
    p3, _attempt: int
) -> None:
    inspection_id, version = _approval_ready(p3)
    key = f"approval-race-{uuid4().hex}"

    def request():
        return _approval_request(
            p3,
            inspection_id=inspection_id,
            version=version,
            key=key,
            reason=None,
        )

    responses = _race_first_reservations(p3, [request, request])
    winner = _assert_race_contract(
        responses,
        success_status=200,
        conflict_message="Idempotency request is already pending",
    )
    replay = request()
    assert replay.status_code == 200
    assert replay.content == winner.content
    scope = f"p3.inspections.{inspection_id}.approval"
    _assert_completed_reservation(p3, key=key, scope=scope, winner=winner)
    _assert_one_finalization(p3, inspection_id)


def test_concurrent_first_approval_reservation_different_payload_is_one_effect_and_conflict(
    p3,
) -> None:
    inspection_id, version = _approval_ready(p3)
    key = f"approval-race-conflict-{uuid4().hex}"
    reasons = ["concurrent reason a", "concurrent reason b"]

    def request(index: int):
        return _approval_request(
            p3,
            inspection_id=inspection_id,
            version=version,
            key=key,
            reason=reasons[index],
        )

    responses = _race_first_reservations(p3, [lambda: request(0), lambda: request(1)])
    winner = _assert_race_contract(
        responses,
        success_status=200,
        conflict_message="Idempotency key request conflict",
    )
    winning_index = responses.index(winner)
    replay = request(winning_index)
    assert replay.status_code == 200
    assert replay.content == winner.content
    scope = f"p3.inspections.{inspection_id}.approval"
    _assert_completed_reservation(p3, key=key, scope=scope, winner=winner)
    _assert_one_finalization(p3, inspection_id)


def _assert_one_finalization(p3, inspection_id: str) -> None:
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM approvals WHERE inspection_case_id = :case"),
                {"case": inspection_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text("SELECT count(*) FROM decision_snapshots WHERE inspection_case_id = :case"),
                {"case": inspection_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM audit_logs "
                    "WHERE entity_id = :case AND action = 'FINALIZE'"
                ),
                {"case": inspection_id},
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM outbox_events "
                    "WHERE payload->>'inspection_case_id' = :case"
                ),
                {"case": inspection_id},
            ).scalar_one()
            == 1
        )
    engine.dispose()
