from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Barrier
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError

from hyc_data.p3_fixture_seed import MOISTURE_SPEC_ITEM_ID, PURITY_SPEC_ITEM_ID

pytestmark = pytest.mark.postgres


def test_full_vertical_slice_rbac_immutability_and_lineage(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    ready = p3.clear_hold(inspection_id)

    stale = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/submit",
        headers=p3.inspector | {"If-Match": "1"},
    )
    assert stale.status_code == 409
    submitted = p3.submit(inspection_id, ready["version"])

    for headers in (p3.inspector, p3.admin):
        denied = p3.client.post(
            f"/api/v1/inspections/{inspection_id}/approvals",
            json={"action": "APPROVE", "reason": None},
            headers=headers
            | {
                "If-Match": str(submitted["version"]),
                "Idempotency-Key": f"denied-{headers['Authorization'][-6:]}",
            },
        )
        assert denied.status_code == 403

    stale_approval = p3.approve(
        inspection_id,
        submitted["version"] - 1,
        key=f"stale-{inspection_id}",
    )
    assert stale_approval.status_code == 409

    approved = p3.approve(inspection_id, submitted["version"])
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "ACCEPTED"

    mutation = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={"results": []},
        headers=p3.inspector | {"If-Match": str(approved.json()["version"])},
    )
    assert mutation.status_code == 409, mutation.text

    engine = create_engine(p3.database_url)
    with engine.begin() as connection:
        with pytest.raises(
            DBAPIError, match="finalized inspection evidence is immutable"
        ):
            connection.execute(
                text(
                    "UPDATE internal_results SET evaluated_value = 9 "
                    "WHERE inspection_case_id = :id"
                ),
                {"id": inspection_id},
            )
    engine.dispose()

    revision = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/revisions",
        json={"reason": "fixture correction"},
        headers=p3.inspector,
    )
    assert revision.status_code == 201, revision.text
    assert revision.json()["round_no"] == 1
    assert revision.json()["revision_no"] == 2
    retest = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/retests",
        json={"reason": "fixture retest"},
        headers=p3.inspector,
    )
    assert retest.status_code == 201, retest.text
    assert retest.json()["round_no"] == 2
    assert retest.json()["revision_no"] == 1


def test_intake_idempotency_replay_and_conflict(p3) -> None:
    marker = "idem-" + __import__("uuid").uuid4().hex
    first = p3.intake(suffix=marker)
    body = {
        "supplier_id": p3.context["supplier_id"],
        "material_id": p3.context["material_id"],
        "model_id": p3.context["model_id"],
        "inbound_no": f"P3-IN-{marker}",
        "receipt_date": "2026-08-01",
        "supplier_lot_no": f"P3-LOT-{marker}",
        "quantity": "100.00",
        "quantity_unit": "kg",
    }
    replay = p3.client.post(
        "/api/v1/intakes",
        json=body,
        headers=p3.inspector | {"Idempotency-Key": f"intake-{marker}"},
    )
    assert replay.status_code == 201
    assert replay.json() == first
    body["quantity"] = "101.00"
    conflict = p3.client.post(
        "/api/v1/intakes",
        json=body,
        headers=p3.inspector | {"Idempotency-Key": f"intake-{marker}"},
    )
    assert conflict.status_code == 409


def test_create_inspection_requires_exact_document_allocation_lineage(p3) -> None:
    reviewed = p3.reviewed_extraction()
    other = p3.intake()
    key = f"lineage-{uuid4().hex}"
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        before = {
            "cases": connection.execute(text("SELECT count(*) FROM inspection_cases")).scalar_one(),
            "audits": connection.execute(text("SELECT count(*) FROM audit_logs")).scalar_one(),
            "outbox": connection.execute(text("SELECT count(*) FROM outbox_events")).scalar_one(),
            "snapshots": connection.execute(
                text("SELECT count(*) FROM decision_snapshots")
            ).scalar_one(),
        }

    mismatch = p3.client.post(
        "/api/v1/inspections",
        json={
            "allocation_id": other["allocation_id"],
            "extraction_run_id": reviewed["run_id"],
        },
        headers=p3.inspector | {"Idempotency-Key": key},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["code"] == "HTTP_ERROR"
    assert mismatch.json()["message"] == "Extraction allocation lineage mismatch"

    with engine.connect() as connection:
        after = {
            "cases": connection.execute(text("SELECT count(*) FROM inspection_cases")).scalar_one(),
            "audits": connection.execute(text("SELECT count(*) FROM audit_logs")).scalar_one(),
            "outbox": connection.execute(text("SELECT count(*) FROM outbox_events")).scalar_one(),
            "snapshots": connection.execute(
                text("SELECT count(*) FROM decision_snapshots")
            ).scalar_one(),
        }
        assert after == before
        assert connection.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key = :key"), {"key": key}
        ).scalar_one() == 0

    same_allocation = p3.client.post(
        "/api/v1/inspections",
        json={
            "allocation_id": reviewed["allocation_id"],
            "extraction_run_id": reviewed["run_id"],
        },
        headers=p3.inspector | {"Idempotency-Key": key},
    )
    assert same_allocation.status_code == 201, same_allocation.text
    engine.dispose()


def test_confirmed_review_cannot_be_rewritten_or_rebound(p3) -> None:
    reviewed = p3.reviewed_extraction()
    other = p3.intake()
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        version = connection.execute(
            text("SELECT lock_version FROM extraction_runs WHERE id = :run"),
            {"run": reviewed["run_id"]},
        ).scalar_one()
        fields_before = connection.execute(
            text(
                "SELECT field_key, manual_text, final_text, source, reason "
                "FROM extraction_field_reviews WHERE extraction_run_id = :run "
                "ORDER BY field_key"
            ),
            {"run": reviewed["run_id"]},
        ).all()
        links_before = connection.execute(
            text(
                "SELECT dal.receipt_lot_allocation_id "
                "FROM document_allocation_links dal "
                "JOIN document_sections ds ON ds.id = dal.document_section_id "
                "WHERE ds.document_id = :document AND dal.match_status = 'CONFIRMED'"
            ),
            {"document": reviewed["document_id"]},
        ).scalars().all()
    assert [str(link) for link in links_before] == [reviewed["allocation_id"]]

    changed_fields = [
        {
            "field_key": field["field_key"],
            "manual_text": "9.99",
            "final_text": "9.99",
            "source": "MANUAL",
            "reason": "attempted confirmed rewrite",
            "logic_conflict": False,
        }
        for field in reviewed["fields"]
    ]
    review_url = (
        f"/api/v1/documents/{reviewed['document_id']}/reviews/{reviewed['run_id']}"
    )
    for allocation_id in (reviewed["allocation_id"], other["allocation_id"]):
        repeated = p3.client.put(
            review_url,
            json={"fields": changed_fields, "allocation_id": allocation_id},
            headers=p3.inspector | {"If-Match": str(version)},
        )
        assert repeated.status_code == 409, repeated.text

    with engine.connect() as connection:
        fields_after = connection.execute(
            text(
                "SELECT field_key, manual_text, final_text, source, reason "
                "FROM extraction_field_reviews WHERE extraction_run_id = :run "
                "ORDER BY field_key"
            ),
            {"run": reviewed["run_id"]},
        ).all()
        links_after = connection.execute(
            text(
                "SELECT dal.receipt_lot_allocation_id "
                "FROM document_allocation_links dal "
                "JOIN document_sections ds ON ds.id = dal.document_section_id "
                "WHERE ds.document_id = :document AND dal.match_status = 'CONFIRMED'"
            ),
            {"document": reviewed["document_id"]},
        ).scalars().all()
        section_id = connection.execute(
            text("SELECT id FROM document_sections WHERE document_id = :document"),
            {"document": reviewed["document_id"]},
        ).scalar_one()
        before_counts = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM inspection_cases), "
                "(SELECT count(*) FROM audit_logs), "
                "(SELECT count(*) FROM outbox_events), "
                "(SELECT count(*) FROM decision_snapshots)"
            )
        ).one()
    assert fields_after == fields_before
    assert links_after == links_before
    with pytest.raises(DBAPIError, match="confirmed extraction lineage is immutable"):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO document_allocation_links "
                    "(id, document_section_id, receipt_lot_allocation_id, match_status) "
                    "VALUES (:id, :section, :allocation, 'CONFIRMED')"
                ),
                {
                    "id": uuid4(),
                    "section": section_id,
                    "allocation": other["allocation_id"],
                },
            )

    key = f"confirmed-lineage-{uuid4().hex}"
    unrelated = p3.client.post(
        "/api/v1/inspections",
        json={
            "allocation_id": other["allocation_id"],
            "extraction_run_id": reviewed["run_id"],
        },
        headers=p3.inspector | {"Idempotency-Key": key},
    )
    assert unrelated.status_code == 409, unrelated.text
    with engine.connect() as connection:
        after_counts = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM inspection_cases), "
                "(SELECT count(*) FROM audit_logs), "
                "(SELECT count(*) FROM outbox_events), "
                "(SELECT count(*) FROM decision_snapshots)"
            )
        ).one()
        assert after_counts == before_counts
        assert connection.execute(
            text("SELECT count(*) FROM idempotency_keys WHERE key = :key"), {"key": key}
        ).scalar_one() == 0

    original = p3.client.post(
        "/api/v1/inspections",
        json={
            "allocation_id": reviewed["allocation_id"],
            "extraction_run_id": reviewed["run_id"],
        },
        headers=p3.inspector | {"Idempotency-Key": key},
    )
    assert original.status_code == 201, original.text
    engine.dispose()


@pytest.mark.parametrize("_race_attempt", range(5))
def test_concurrent_first_confirmations_map_unique_loser_to_stable_409(
    p3, _race_attempt: int
) -> None:
    first = p3.intake()
    second = p3.intake()
    marker = uuid4().hex
    document = p3.client.post(
        "/api/v1/documents",
        content=f"P3 SYNTHETIC CONCURRENT COA {marker}".encode(),
        headers=p3.inspector
        | {"X-Filename": f"concurrent-{marker}.txt", "Content-Type": "text/plain"},
    )
    assert document.status_code == 201, document.text
    document_id = document.json()["document_id"]
    runs = [
        p3.client.post(
            f"/api/v1/documents/{document_id}/extractions", headers=p3.inspector
        ).json()
        for _ in range(2)
    ]
    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM document_sections WHERE document_id = :document"),
            {"document": document_id},
        ).scalar_one() == 0
        lineage_before = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM material_lots), "
                "(SELECT count(*) FROM inbound_receipts), "
                "(SELECT count(*) FROM receipt_lot_allocations), "
                "(SELECT count(*) FROM inspection_cases), "
                "(SELECT count(*) FROM lot_merge_approvals), "
                "(SELECT count(*) FROM decision_snapshots), "
                "(SELECT count(*) FROM outbox_events), "
                "(SELECT count(*) FROM idempotency_keys)"
            )
        ).one()

    parent_lock_barrier = Barrier(2)

    def synchronize_competing_parent_locks(
        _connection, _cursor, statement, _parameters, _context, _many
    ) -> None:
        if "FROM extraction_runs" in statement and "FOR UPDATE" in statement:
            parent_lock_barrier.wait(timeout=10)

    event.listen(
        p3.client.app.state.engine,
        "before_cursor_execute",
        synchronize_competing_parent_locks,
    )

    def confirm(run, allocation_id):
        fields = [
            {
                "field_key": field["field_key"],
                "manual_text": None,
                "final_text": field["ocr_text"],
                "source": "OCR",
                "reason": "synthetic concurrent confirmation",
                "logic_conflict": False,
            }
            for field in run["fields"]
        ]
        return p3.client.put(
            f"/api/v1/documents/{document_id}/reviews/{run['run_id']}",
            json={"fields": fields, "allocation_id": allocation_id},
            headers=p3.inspector | {"If-Match": str(run["version"])},
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(confirm, runs[0], first["allocation_id"]),
                executor.submit(confirm, runs[1], second["allocation_id"]),
            ]
            responses = [future.result(timeout=20) for future in futures]
    finally:
        event.remove(
            p3.client.app.state.engine,
            "before_cursor_execute",
            synchronize_competing_parent_locks,
        )

    assert sorted(response.status_code for response in responses) == [200, 409]
    loser_response = next(response for response in responses if response.status_code == 409)
    assert loser_response.json()["code"] == "HTTP_ERROR"
    assert (
        loser_response.json()["message"]
        == "Document section already has a confirmed allocation"
    )
    loser_index = responses.index(loser_response)
    losing_run_id = runs[loser_index]["run_id"]
    winning_run_id = runs[1 - loser_index]["run_id"]

    with engine.connect() as connection:
        sections = connection.execute(
            text(
                "SELECT id FROM document_sections "
                "WHERE document_id = :document AND section_index = 1"
            ),
            {"document": document_id},
        ).scalars().all()
        assert len(sections) == 1
        links = connection.execute(
            text(
                "SELECT dal.document_section_id, dal.receipt_lot_allocation_id "
                "FROM document_allocation_links dal "
                "JOIN document_sections ds ON ds.id = dal.document_section_id "
                "WHERE ds.document_id = :document AND dal.match_status = 'CONFIRMED'"
            ),
            {"document": document_id},
        ).all()
        assert len(links) == 1
        assert links[0].document_section_id == sections[0]
        assert str(links[0].receipt_lot_allocation_id) in {
            first["allocation_id"],
            second["allocation_id"],
        }
        states = {
            row.id: (row.status, row.lock_version, row.conflicts)
            for row in connection.execute(
                text(
                    "SELECT id, status, lock_version, conflicts FROM extraction_runs "
                    "WHERE id IN (:winner, :loser)"
                ),
                {"winner": winning_run_id, "loser": losing_run_id},
            )
        }
        assert states[UUID(winning_run_id)][0] == "CONFIRMED"
        assert states[UUID(losing_run_id)] == (
            "REVIEW_REQUIRED",
            runs[loser_index]["version"],
            [{"code": "REVIEW_REQUIRED", "visible": True}],
        )
        losing_fields = connection.execute(
            text(
                "SELECT manual_text, final_text, source, reason, logic_conflict, status, "
                "lock_version "
                "FROM extraction_field_reviews WHERE extraction_run_id = :run "
                "ORDER BY field_key"
            ),
            {"run": losing_run_id},
        ).all()
        assert losing_fields == [
            (None, None, None, None, False, "REVIEW_REQUIRED", 1) for _ in range(3)
        ]
        assert connection.execute(
            text(
                "SELECT count(*) FROM audit_logs "
                "WHERE entity_id = :run AND action = 'P3_EXTRACTION_REVIEW_CONFIRMED'"
            ),
            {"run": losing_run_id},
        ).scalar_one() == 0
        lineage_after = connection.execute(
            text(
                "SELECT (SELECT count(*) FROM material_lots), "
                "(SELECT count(*) FROM inbound_receipts), "
                "(SELECT count(*) FROM receipt_lot_allocations), "
                "(SELECT count(*) FROM inspection_cases), "
                "(SELECT count(*) FROM lot_merge_approvals), "
                "(SELECT count(*) FROM decision_snapshots), "
                "(SELECT count(*) FROM outbox_events), "
                "(SELECT count(*) FROM idempotency_keys)"
            )
        ).one()
        assert lineage_after == lineage_before
    engine.dispose()


def test_repeated_internal_results_put_replaces_samples_and_versions(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    first = p3.clear_hold(inspection_id)
    replacement = {
        "results": [
            {
                "spec_item_id": str(MOISTURE_SPEC_ITEM_ID),
                "values": ["0.20", "0.22"],
            }
        ]
    }
    second = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json=replacement,
        headers=p3.inspector | {"If-Match": str(first["version"])},
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] > first["version"]

    stale = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json=replacement,
        headers=p3.inspector | {"If-Match": str(first["version"])},
    )
    assert stale.status_code == 409

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        result_rows = connection.execute(
            text(
                "SELECT id, evaluated_value FROM internal_results "
                "WHERE inspection_case_id = :case AND spec_item_id = :spec"
            ),
            {"case": inspection_id, "spec": MOISTURE_SPEC_ITEM_ID},
        ).all()
        assert len(result_rows) == 1
        assert result_rows[0].evaluated_value == Decimal("0.20")
        samples = connection.execute(
            text(
                "SELECT sample_index, numeric_value FROM sample_measurements "
                "WHERE internal_result_id = :result ORDER BY sample_index"
            ),
            {"result": result_rows[0].id},
        ).all()
        assert samples == [(1, Decimal("0.20")), (2, Decimal("0.22"))]
        audit = connection.execute(
            text(
                "SELECT payload FROM audit_logs "
                "WHERE entity_id = :case AND action = 'P3_INTERNAL_RESULTS_UPDATED' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"case": inspection_id},
        ).scalar_one()
        expected_id = str(MOISTURE_SPEC_ITEM_ID)
        assert audit == {
            "result_count": 1,
            "requested_spec_item_ids": [expected_id],
            "retained_spec_item_ids": [expected_id],
            "removed_spec_item_ids": [],
            "deleted_result_count": 0,
            "deleted_sample_count": 3,
        }
    engine.dispose()


def test_internal_results_put_replaces_the_whole_collection_and_allows_clear(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    current = p3.client.get(
        f"/api/v1/inspections/{inspection_id}", headers=p3.inspector
    ).json()
    duplicate = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={
            "results": [
                {"spec_item_id": str(MOISTURE_SPEC_ITEM_ID), "values": ["0.10"]},
                {"spec_item_id": str(MOISTURE_SPEC_ITEM_ID), "values": ["0.11"]},
            ]
        },
        headers=p3.inspector | {"If-Match": str(current["version"])},
    )
    assert duplicate.status_code == 422, duplicate.text
    moisture = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={
            "results": [
                {"spec_item_id": str(MOISTURE_SPEC_ITEM_ID), "values": ["0.10", "0.12"]}
            ]
        },
        headers=p3.inspector | {"If-Match": str(current["version"])},
    )
    assert moisture.status_code == 200, moisture.text

    purity_payload = {
        "results": [
            {"spec_item_id": str(PURITY_SPEC_ITEM_ID), "values": ["10.00"]}
        ]
    }
    purity = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json=purity_payload,
        headers=p3.inspector | {"If-Match": str(moisture.json()["version"])},
    )
    assert purity.status_code == 200, purity.text

    engine = create_engine(p3.database_url)
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT spec_item_id FROM internal_results "
                "WHERE inspection_case_id = :case"
            ),
            {"case": inspection_id},
        ).scalars().all() == [PURITY_SPEC_ITEM_ID]
        assert connection.execute(
            text(
                "SELECT sm.sample_index, sm.numeric_value FROM sample_measurements sm "
                "JOIN internal_results ir ON ir.id = sm.internal_result_id "
                "WHERE ir.inspection_case_id = :case"
            ),
            {"case": inspection_id},
        ).all() == [(1, Decimal("10.00"))]
        replacement_audit = connection.execute(
            text(
                "SELECT payload FROM audit_logs "
                "WHERE entity_id = :case AND action = 'P3_INTERNAL_RESULTS_UPDATED' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"case": inspection_id},
        ).scalar_one()
        assert replacement_audit == {
            "result_count": 1,
            "requested_spec_item_ids": [str(PURITY_SPEC_ITEM_ID)],
            "retained_spec_item_ids": [],
            "removed_spec_item_ids": [str(MOISTURE_SPEC_ITEM_ID)],
            "deleted_result_count": 1,
            "deleted_sample_count": 2,
        }

    stale = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json=purity_payload,
        headers=p3.inspector | {"If-Match": str(moisture.json()["version"])},
    )
    assert stale.status_code == 409, stale.text

    corrected = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={
            "results": [
                {"spec_item_id": str(MOISTURE_SPEC_ITEM_ID), "values": ["0.11"]}
            ]
        },
        headers=p3.inspector | {"If-Match": str(purity.json()["version"])},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["candidate_decision"] == "ACCEPTED"
    assert corrected.json()["blockers"] == []

    cleared = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={"results": []},
        headers=p3.inspector | {"If-Match": str(corrected.json()["version"])},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["candidate_decision"] == "ON_HOLD"
    assert "INTERNAL_TEST_PENDING" in cleared.json()["blockers"]
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM internal_results WHERE inspection_case_id = :case"),
            {"case": inspection_id},
        ).scalar_one() == 0
        clear_audit = connection.execute(
            text(
                "SELECT payload FROM audit_logs "
                "WHERE entity_id = :case AND action = 'P3_INTERNAL_RESULTS_UPDATED' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"case": inspection_id},
        ).scalar_one()
        assert clear_audit == {
            "result_count": 0,
            "requested_spec_item_ids": [],
            "retained_spec_item_ids": [],
            "removed_spec_item_ids": [str(MOISTURE_SPEC_ITEM_ID)],
            "deleted_result_count": 1,
            "deleted_sample_count": 1,
        }
        assert connection.execute(
            text(
                "SELECT count(*) FROM sample_measurements sm JOIN internal_results ir "
                "ON ir.id = sm.internal_result_id WHERE ir.inspection_case_id = :case"
            ),
            {"case": inspection_id},
        ).scalar_one() == 0

    blocked = p3.client.post(
        f"/api/v1/inspections/{inspection_id}/submit",
        headers=p3.inspector | {"If-Match": str(cleared.json()["version"])},
    )
    assert blocked.status_code == 422, blocked.text
    engine.dispose()


def test_internal_result_change_revokes_lead_review_eligibility(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    ready = p3.clear_hold(inspection_id)
    submitted = p3.submit(inspection_id, ready["version"])

    replaced = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={
            "results": [
                {"spec_item_id": str(MOISTURE_SPEC_ITEM_ID), "values": ["0.09"]}
            ]
        },
        headers=p3.inspector | {"If-Match": str(submitted["version"])},
    )
    assert replaced.status_code == 200, replaced.text
    assert replaced.json()["status"] == "READY_FOR_REVIEW"
    denied_after_replace = p3.approve(
        inspection_id,
        replaced.json()["version"],
        key=f"replaced-{inspection_id}",
    )
    assert denied_after_replace.status_code == 422, denied_after_replace.text
    assert p3.client.get(
        f"/api/v1/inspections/{inspection_id}", headers=p3.inspector
    ).json()["final_decision"] is None

    resubmitted = p3.submit(inspection_id, replaced.json()["version"])
    cleared = p3.client.put(
        f"/api/v1/inspections/{inspection_id}/internal-results",
        json={"results": []},
        headers=p3.inspector | {"If-Match": str(resubmitted["version"])},
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["status"] == "INTERNAL_TEST_PENDING"
    assert cleared.json()["candidate_decision"] == "ON_HOLD"
    denied_after_clear = p3.approve(
        inspection_id,
        cleared.json()["version"],
        key=f"cleared-{inspection_id}",
    )
    assert denied_after_clear.status_code == 422, denied_after_clear.text
    assert p3.client.get(
        f"/api/v1/inspections/{inspection_id}", headers=p3.inspector
    ).json()["final_decision"] is None


def test_get_inspection_does_not_flush_derived_state(p3) -> None:
    flow = p3.reviewed()
    mutations: list[str] = []

    def track_mutations(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            mutations.append(statement)

    event.listen(p3.client.app.state.engine, "before_cursor_execute", track_mutations)
    try:
        response = p3.client.get(
            f"/api/v1/inspections/{flow['inspection_id']}", headers=p3.inspector
        )
    finally:
        event.remove(p3.client.app.state.engine, "before_cursor_execute", track_mutations)
    assert response.status_code == 200, response.text
    assert mutations == []
