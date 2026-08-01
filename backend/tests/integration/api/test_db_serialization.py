from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DatabaseError

from hyc_data.p3_fixture_seed import MOISTURE_SPEC_ITEM_ID, PURITY_SPEC_ITEM_ID

pytestmark = pytest.mark.postgres

_EVIDENCE_MUTATIONS = (
    "supplier_insert",
    "supplier_update",
    "supplier_delete",
    "internal_insert",
    "internal_update",
    "internal_delete",
    "sample_insert",
    "sample_update",
    "sample_delete",
)

_LINEAGE_MUTATIONS = (
    "run_insert",
    "run_update",
    "run_delete",
    "run_reparent",
    "field_insert",
    "field_update",
    "field_delete",
    "field_reparent",
    "section_insert",
    "section_update",
    "section_delete",
    "section_reparent",
    "link_insert",
    "link_update",
    "link_delete",
    "link_reparent",
)


def _wait_for_database_block(database_url: str, pid: int, future: Future[object]) -> None:
    engine = create_engine(database_url)
    deadline = time.monotonic() + 10
    try:
        with engine.connect() as connection:
            while time.monotonic() < deadline:
                if future.done():
                    future.result()
                    pytest.fail("the app-role mutation committed before the terminal lock")
                blockers = connection.execute(
                    text("SELECT pg_blocking_pids(:pid)"), {"pid": pid}
                ).scalar_one()
                if blockers:
                    return
                time.sleep(0.01)
    finally:
        engine.dispose()
    pytest.fail("the app-role mutation never waited on the authoritative parent lock")


def _execute_app_mutation(app_database_url: str, statement: str, params: dict[str, object]):
    engine = create_engine(app_database_url)
    started = Event()
    state: dict[str, int] = {}

    def execute() -> None:
        try:
            with engine.begin() as connection:
                state["pid"] = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
                started.set()
                connection.execute(text(statement), params)
        finally:
            engine.dispose()

    return execute, started, state


def _approval_fixture(p3, mutation: str) -> tuple[dict[str, object], dict[str, object]]:
    flow = p3.reviewed()
    ready = p3.clear_hold(str(flow["inspection_id"]))
    app_engine = create_engine(p3.app_database_url)
    if mutation == "internal_delete":
        with app_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO internal_results "
                    "(id, inspection_case_id, spec_item_id, evaluated_value, lock_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :case, :spec, 99.0, 1, now(), now())"
                ),
                {
                    "id": uuid4(),
                    "case": flow["inspection_id"],
                    "spec": PURITY_SPEC_ITEM_ID,
                },
            )
    submitted = p3.submit(str(flow["inspection_id"]), int(ready["version"]))
    with app_engine.connect() as connection:
        supplier = connection.execute(
            text(
                "SELECT id, standard_test_item_id FROM supplier_results "
                "WHERE inspection_case_id = :case ORDER BY id LIMIT 1"
            ),
            {"case": flow["inspection_id"]},
        ).one()
        internal = connection.execute(
            text(
                "SELECT id FROM internal_results WHERE inspection_case_id = :case "
                "AND spec_item_id = :spec"
            ),
            {"case": flow["inspection_id"], "spec": MOISTURE_SPEC_ITEM_ID},
        ).one()
        extra_internal = connection.execute(
            text(
                "SELECT id FROM internal_results WHERE inspection_case_id = :case "
                "AND spec_item_id = :spec"
            ),
            {"case": flow["inspection_id"], "spec": PURITY_SPEC_ITEM_ID},
        ).one_or_none()
        sample = connection.execute(
            text(
                "SELECT id FROM sample_measurements WHERE internal_result_id = :result "
                "ORDER BY sample_index LIMIT 1"
            ),
            {"result": internal.id},
        ).one()
        purity_standard = connection.execute(
            text("SELECT standard_test_item_id FROM spec_items WHERE id = :spec"),
            {"spec": PURITY_SPEC_ITEM_ID},
        ).scalar_one()
    app_engine.dispose()
    context: dict[str, object] = {
        "case": flow["inspection_id"],
        "supplier": supplier.id,
        "standard": purity_standard,
        "internal": internal.id,
        "extra_internal": extra_internal.id if extra_internal else None,
        "sample": sample.id,
        "spec": PURITY_SPEC_ITEM_ID,
    }
    return flow | submitted, context


def _evidence_statement(mutation: str, context: dict[str, object]) -> tuple[str, dict[str, object]]:
    common = {"new_id": uuid4()} | context
    statements = {
        "supplier_insert": (
            "INSERT INTO supplier_results "
            "(id, inspection_case_id, standard_test_item_id, supplier_item_name, "
            "mapping_status, normalized_value, lock_version, created_at, updated_at) "
            "VALUES (:new_id, :case, :standard, 'racing supplier', "
            "'MANUAL_CONFIRMED', 98.0, 1, now(), now())"
        ),
        "supplier_update": (
            "UPDATE supplier_results SET normalized_value = 98.0, "
            "lock_version = lock_version + 1 WHERE id = :supplier"
        ),
        "supplier_delete": "DELETE FROM supplier_results WHERE id = :supplier",
        "internal_insert": (
            "INSERT INTO internal_results "
            "(id, inspection_case_id, spec_item_id, evaluated_value, lock_version, "
            "created_at, updated_at) VALUES "
            "(:new_id, :case, :spec, 98.0, 1, now(), now())"
        ),
        "internal_update": (
            "UPDATE internal_results SET evaluated_value = 98.0, "
            "lock_version = lock_version + 1 WHERE id = :internal"
        ),
        "internal_delete": "DELETE FROM internal_results WHERE id = :extra_internal",
        "sample_insert": (
            "INSERT INTO sample_measurements "
            "(id, internal_result_id, sample_index, numeric_value, lock_version, "
            "created_at, updated_at) VALUES "
            "(:new_id, :internal, 99, 98.0, 1, now(), now())"
        ),
        "sample_update": (
            "UPDATE sample_measurements SET numeric_value = 98.0, "
            "lock_version = lock_version + 1 WHERE id = :sample"
        ),
        "sample_delete": "DELETE FROM sample_measurements WHERE id = :sample",
    }
    return statements[mutation], common


def _evidence_state(
    database_url: str, case_id: object
) -> tuple[list[tuple], list[tuple], list[tuple]]:
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            supplier = connection.execute(
                text(
                    "SELECT id, normalized_value, lock_version FROM supplier_results "
                    "WHERE inspection_case_id = :case ORDER BY id"
                ),
                {"case": case_id},
            ).all()
            internal = connection.execute(
                text(
                    "SELECT id, evaluated_value, lock_version FROM internal_results "
                    "WHERE inspection_case_id = :case ORDER BY id"
                ),
                {"case": case_id},
            ).all()
            samples = connection.execute(
                text(
                    "SELECT s.id, s.numeric_value, s.lock_version FROM sample_measurements s "
                    "LEFT JOIN supplier_results sr ON sr.id = s.supplier_result_id "
                    "LEFT JOIN internal_results ir ON ir.id = s.internal_result_id "
                    "WHERE sr.inspection_case_id = :case OR ir.inspection_case_id = :case "
                    "ORDER BY s.id"
                ),
                {"case": case_id},
            ).all()
        return supplier, internal, samples
    finally:
        engine.dispose()


@pytest.mark.parametrize("mutation", _EVIDENCE_MUTATIONS)
def test_approval_serializes_every_app_role_evidence_mutation_family(p3, mutation: str) -> None:
    for _cycle in range(2):
        flow, context = _approval_fixture(p3, mutation)
        before = _evidence_state(p3.database_url, context["case"])
        snapshot_ready = Event()
        release_approval = Event()

        def pause_after_snapshot_construction(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _many,
            ready=snapshot_ready,
            release=release_approval,
        ) -> None:
            if "INSERT INTO decision_snapshots" in statement:
                ready.set()
                assert release.wait(timeout=15)

        event.listen(
            p3.client.app.state.engine,
            "before_cursor_execute",
            pause_after_snapshot_construction,
        )
        statement, params = _evidence_statement(mutation, context)
        execute, mutation_started, mutation_state = _execute_app_mutation(
            p3.app_database_url, statement, params
        )
        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                approval = executor.submit(
                    p3.approve,
                    str(flow["inspection_id"]),
                    int(flow["version"]),
                    key=f"serialization-{mutation}-{uuid4().hex}",
                )
                assert snapshot_ready.wait(timeout=15)
                mutation_future = executor.submit(execute)
                assert mutation_started.wait(timeout=10)
                _wait_for_database_block(
                    p3.database_url, mutation_state["pid"], mutation_future
                )
                release_approval.set()
                approval_response = approval.result(timeout=20)
                assert approval_response.status_code == 200, approval_response.text
                assert approval_response.status_code != 500
                with pytest.raises(
                    DatabaseError, match="finalized inspection evidence is immutable"
                ):
                    mutation_future.result(timeout=20)
        finally:
            release_approval.set()
            event.remove(
                p3.client.app.state.engine,
                "before_cursor_execute",
                pause_after_snapshot_construction,
            )

        assert _evidence_state(p3.database_url, context["case"]) == before
        engine = create_engine(p3.database_url)
        with engine.connect() as connection:
            snapshot = connection.execute(
                text(
                    "SELECT payload FROM decision_snapshots "
                    "WHERE inspection_case_id = :case"
                ),
                {"case": context["case"]},
            ).scalar_one()
        engine.dispose()
        assert {UUID(row["id"]) for row in snapshot["supplier_results"]} == {
            row.id for row in before[0]
        }
        assert {UUID(row["id"]) for row in snapshot["internal_results"]} == {
            row.id for row in before[1]
        }


def _pending_review(p3) -> dict[str, object]:
    intake = p3.intake()
    other = p3.intake()
    marker = uuid4().hex
    document = p3.client.post(
        "/api/v1/documents",
        content=f"P3 SERIALIZATION {marker}".encode(),
        headers=p3.inspector
        | {"X-Filename": f"serialization-{marker}.txt", "Content-Type": "text/plain"},
    )
    assert document.status_code == 201, document.text
    extraction = p3.client.post(
        f"/api/v1/documents/{document.json()['document_id']}/extractions",
        headers=p3.inspector,
    )
    assert extraction.status_code == 201, extraction.text
    engine = create_engine(p3.app_database_url)
    section_id, pending_link_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO document_sections "
                "(id, document_id, section_index, page_from, page_to, status, lock_version, "
                "created_at, updated_at) VALUES "
                "(:id, :document, 1, 1, 1, 'MATCHED', 1, now(), now())"
            ),
            {"id": section_id, "document": document.json()["document_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO document_allocation_links "
                "(id, document_section_id, receipt_lot_allocation_id, match_status, "
                "lock_version, created_at, updated_at) VALUES "
                "(:id, :section, :allocation, 'PENDING', 1, now(), now())"
            ),
            {
                "id": pending_link_id,
                "section": section_id,
                "allocation": other["allocation_id"],
            },
        )
    engine.dispose()
    return (
        intake
        | document.json()
        | extraction.json()
        | {
            "section_id": section_id,
            "pending_link_id": pending_link_id,
            "other_allocation_id": other["allocation_id"],
        }
    )


def _review_body(flow: dict[str, object]) -> dict[str, object]:
    return {
        "fields": [
            {
                "field_key": field["field_key"],
                "manual_text": None,
                "final_text": field["ocr_text"],
                "source": "OCR",
                "reason": "DB serialization review",
                "logic_conflict": False,
            }
            for field in flow["fields"]
        ],
        "allocation_id": flow["allocation_id"],
    }


def _lineage_statement(
    mutation: str, flow: dict[str, object], other: dict[str, object]
) -> tuple[str, dict[str, object]]:
    params = {
        "new_id": uuid4(),
        "run": flow["run_id"],
        "document": flow["document_id"],
        "field": flow["field_id"],
        "section": flow["section_id"],
        "link": flow["pending_link_id"],
        "allocation": flow["allocation_id"],
        "other_allocation": other["allocation_id"],
        "other_run": other["run_id"],
        "other_document": other["document_id"],
        "other_section": other["section_id"],
    }
    statements = {
        "run_insert": (
            "INSERT INTO extraction_runs "
            "(id, document_id, provider_name, status, candidate_payload, conflicts, "
            "lock_version, created_at, updated_at) VALUES "
            "(:new_id, :document, 'direct', 'REVIEW_REQUIRED', '{}', '[]', "
            "1, now(), now())"
        ),
        "run_update": (
            "UPDATE extraction_runs SET provider_name = 'direct-update', "
            "lock_version = lock_version + 1 WHERE id = :run"
        ),
        "run_delete": "DELETE FROM extraction_runs WHERE id = :run",
        "run_reparent": (
            "UPDATE extraction_runs SET document_id = :other_document, "
            "lock_version = lock_version + 1 WHERE id = :run"
        ),
        "field_insert": (
            "INSERT INTO extraction_field_reviews "
            "(id, extraction_run_id, field_key, original_text, ocr_text, confidence, "
            "page_number, bbox, required, logic_conflict, status, lock_version, "
            "created_at, updated_at) VALUES "
            "(:new_id, :run, 'direct-extra', 'x', 'x', 0.9, 1, '{}', true, false, "
            "'REVIEW_REQUIRED', 1, now(), now())"
        ),
        "field_update": (
            "UPDATE extraction_field_reviews SET final_text = 'direct-update', "
            "lock_version = lock_version + 1 WHERE id = :field"
        ),
        "field_delete": "DELETE FROM extraction_field_reviews WHERE id = :field",
        "field_reparent": (
            "UPDATE extraction_field_reviews SET extraction_run_id = :other_run, "
            "lock_version = lock_version + 1 WHERE id = :field"
        ),
        "section_insert": (
            "INSERT INTO document_sections "
            "(id, document_id, section_index, page_from, page_to, status, lock_version, "
            "created_at, updated_at) VALUES "
            "(:new_id, :document, 99, 1, 1, 'UNMATCHED', 1, now(), now())"
        ),
        "section_update": (
            "UPDATE document_sections SET status = 'REVIEW_REQUIRED', "
            "lock_version = lock_version + 1 WHERE id = :section"
        ),
        "section_delete": "DELETE FROM document_sections WHERE id = :section",
        "section_reparent": (
            "UPDATE document_sections SET document_id = :other_document, section_index = 99, "
            "lock_version = lock_version + 1 WHERE id = :section"
        ),
        "link_insert": (
            "INSERT INTO document_allocation_links "
            "(id, document_section_id, receipt_lot_allocation_id, match_status, "
            "lock_version, created_at, updated_at) VALUES "
            "(:new_id, :section, :allocation, 'PENDING', 1, now(), now())"
        ),
        "link_update": (
            "UPDATE document_allocation_links SET receipt_lot_allocation_id = :allocation, "
            "lock_version = lock_version + 1 WHERE id = :link"
        ),
        "link_delete": "DELETE FROM document_allocation_links WHERE id = :link",
        "link_reparent": (
            "UPDATE document_allocation_links SET document_section_id = :other_section, "
            "lock_version = lock_version + 1 WHERE id = :link"
        ),
    }
    return statements[mutation], params


def _hydrate_lineage_context(database_url: str, flow: dict[str, object]) -> dict[str, object]:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        field_id = connection.execute(
            text(
                "SELECT id FROM extraction_field_reviews WHERE extraction_run_id = :run "
                "ORDER BY field_key LIMIT 1"
            ),
            {"run": flow["run_id"]},
        ).scalar_one()
    engine.dispose()
    return flow | {"field_id": field_id}


@pytest.mark.parametrize("mutation", _LINEAGE_MUTATIONS)
def test_confirmation_serializes_every_app_role_lineage_mutation(p3, mutation: str) -> None:
    for _cycle in range(2):
        flow = _hydrate_lineage_context(p3.database_url, _pending_review(p3))
        other = _hydrate_lineage_context(p3.database_url, _pending_review(p3))
        confirmation_ready = Event()
        release_confirmation = Event()

        def pause_before_terminal_status(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _many,
            ready=confirmation_ready,
            release=release_confirmation,
        ) -> None:
            if statement.startswith("UPDATE extraction_runs SET status="):
                ready.set()
                assert release.wait(timeout=15)

        event.listen(
            p3.client.app.state.engine,
            "before_cursor_execute",
            pause_before_terminal_status,
        )
        statement, params = _lineage_statement(mutation, flow, other)
        execute, mutation_started, mutation_state = _execute_app_mutation(
            p3.app_database_url, statement, params
        )

        def confirm(current_flow=flow):
            return p3.client.put(
                f"/api/v1/documents/{current_flow['document_id']}/reviews/"
                f"{current_flow['run_id']}",
                json=_review_body(current_flow),
                headers=p3.inspector | {"If-Match": str(current_flow["version"])},
            )

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                confirmation = executor.submit(confirm)
                assert confirmation_ready.wait(timeout=15)
                mutation_future = executor.submit(execute)
                assert mutation_started.wait(timeout=10)
                _wait_for_database_block(
                    p3.database_url, mutation_state["pid"], mutation_future
                )
                release_confirmation.set()
                response = confirmation.result(timeout=20)
                assert response.status_code == 200, response.text
                assert response.status_code != 500
                with pytest.raises(
                    DatabaseError, match="confirmed extraction lineage is immutable"
                ):
                    mutation_future.result(timeout=20)
        finally:
            release_confirmation.set()
            event.remove(
                p3.client.app.state.engine,
                "before_cursor_execute",
                pause_before_terminal_status,
            )

        engine = create_engine(p3.database_url)
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT status FROM extraction_runs WHERE id = :run"),
                {"run": flow["run_id"]},
            ).scalar_one() == "CONFIRMED"
            assert connection.execute(
                text(
                    "SELECT count(*) FROM document_allocation_links "
                    "WHERE document_section_id = :section AND match_status = 'CONFIRMED'"
                ),
                {"section": flow["section_id"]},
            ).scalar_one() == 1
        engine.dispose()


def test_pending_lineage_mutations_remain_legal_and_confirmation_is_atomic(p3) -> None:
    flow = _hydrate_lineage_context(p3.database_url, _pending_review(p3))
    engine = create_engine(p3.app_database_url)
    temporary_run, temporary_field, temporary_section, temporary_link = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE extraction_runs SET provider_name = 'before-confirm', "
                "lock_version = lock_version + 1 WHERE id = :run"
            ),
            {"run": flow["run_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO extraction_runs "
                "(id, document_id, provider_name, status, candidate_payload, conflicts, "
                "lock_version, created_at, updated_at) VALUES "
                "(:id, :document, 'temporary', 'REVIEW_REQUIRED', '{}', '[]', "
                "1, now(), now())"
            ),
            {"id": temporary_run, "document": flow["document_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO extraction_field_reviews "
                "(id, extraction_run_id, field_key, original_text, ocr_text, confidence, "
                "page_number, bbox, required, logic_conflict, status, lock_version, "
                "created_at, updated_at) VALUES "
                "(:id, :run, 'temporary', 'x', 'x', 0.9, 1, '{}', true, false, "
                "'REVIEW_REQUIRED', 1, now(), now())"
            ),
            {"id": temporary_field, "run": temporary_run},
        )
        connection.execute(
                text(
                    "UPDATE extraction_field_reviews SET ocr_text = 'updated', "
                    "lock_version = lock_version + 1 "
                    "WHERE id = :id"
            ),
            {"id": temporary_field},
        )
        connection.execute(
            text("DELETE FROM extraction_field_reviews WHERE id = :id"),
            {"id": temporary_field},
        )
        connection.execute(
            text("DELETE FROM extraction_runs WHERE id = :id"), {"id": temporary_run}
        )
        connection.execute(
            text(
                "INSERT INTO document_sections "
                "(id, document_id, section_index, page_from, page_to, status, lock_version, "
                "created_at, updated_at) VALUES "
                "(:id, :document, 2, 1, 1, 'UNMATCHED', 1, now(), now())"
            ),
            {"id": temporary_section, "document": flow["document_id"]},
        )
        connection.execute(
            text(
                "INSERT INTO document_allocation_links "
                "(id, document_section_id, receipt_lot_allocation_id, match_status, "
                "lock_version, created_at, updated_at) VALUES "
                "(:id, :section, :allocation, 'PENDING', 1, now(), now())"
            ),
            {
                "id": temporary_link,
                "section": temporary_section,
                "allocation": flow["allocation_id"],
            },
        )
        connection.execute(
                text(
                    "UPDATE document_allocation_links SET match_status = 'REJECTED', "
                    "lock_version = lock_version + 1 "
                    "WHERE id = :id"
            ),
            {"id": temporary_link},
        )
        connection.execute(
            text("DELETE FROM document_allocation_links WHERE id = :id"),
            {"id": temporary_link},
        )
        connection.execute(
            text(
                "UPDATE document_sections SET status = 'REVIEW_REQUIRED', "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": temporary_section},
        )
        connection.execute(
            text("DELETE FROM document_sections WHERE id = :id"),
            {"id": temporary_section},
        )
    engine.dispose()

    stale_version = int(flow["version"])
    current_engine = create_engine(p3.database_url)
    with current_engine.connect() as connection:
        current_version = connection.execute(
            text("SELECT lock_version FROM extraction_runs WHERE id = :run"),
            {"run": flow["run_id"]},
        ).scalar_one()
    current_engine.dispose()
    assert current_version > stale_version
    failed = p3.client.put(
        f"/api/v1/documents/{flow['document_id']}/reviews/{flow['run_id']}",
        json=_review_body(flow) | {"allocation_id": str(uuid4())},
        headers=p3.inspector | {"If-Match": str(current_version)},
    )
    assert failed.status_code == 404

    owner = create_engine(p3.database_url)
    with owner.connect() as connection:
        assert connection.execute(
            text("SELECT status FROM extraction_runs WHERE id = :run"),
            {"run": flow["run_id"]},
        ).scalar_one() == "REVIEW_REQUIRED"
        assert connection.execute(
            text(
                "SELECT count(*) FROM extraction_field_reviews "
                "WHERE extraction_run_id = :run AND status = 'CONFIRMED'"
            ),
            {"run": flow["run_id"]},
        ).scalar_one() == 0
        assert connection.execute(
            text(
                "SELECT count(*) FROM document_allocation_links "
                "WHERE document_section_id = :section AND match_status = 'CONFIRMED'"
            ),
            {"section": flow["section_id"]},
        ).scalar_one() == 0
    owner.dispose()

    confirmed = p3.client.put(
        f"/api/v1/documents/{flow['document_id']}/reviews/{flow['run_id']}",
        json=_review_body(flow),
        headers=p3.inspector | {"If-Match": str(current_version)},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "CONFIRMED"


def test_confirmed_allocation_link_cannot_be_rebound_to_another_lot_by_app_role(p3) -> None:
    confirmed = p3.reviewed_extraction()
    other = p3.intake()
    owner = create_engine(p3.database_url)
    with owner.connect() as connection:
        link = connection.execute(
            text(
                "SELECT dal.id, dal.receipt_lot_allocation_id "
                "FROM document_allocation_links dal "
                "JOIN document_sections ds ON ds.id = dal.document_section_id "
                "WHERE ds.document_id = :document AND dal.match_status = 'CONFIRMED'"
            ),
            {"document": confirmed["document_id"]},
        ).one()
    owner.dispose()

    app = create_engine(p3.app_database_url)
    with pytest.raises(DatabaseError, match="confirmed extraction lineage is immutable"):
        with app.begin() as connection:
            connection.execute(
                text(
                    "UPDATE document_allocation_links "
                    "SET receipt_lot_allocation_id = :allocation, "
                    "lock_version = lock_version + 1 WHERE id = :link"
                ),
                {"allocation": other["allocation_id"], "link": link.id},
            )
    app.dispose()

    owner = create_engine(p3.database_url)
    with owner.connect() as connection:
        assert connection.execute(
            text(
                "SELECT receipt_lot_allocation_id FROM document_allocation_links "
                "WHERE id = :link"
            ),
            {"link": link.id},
        ).scalar_one() == link.receipt_lot_allocation_id
    owner.dispose()
