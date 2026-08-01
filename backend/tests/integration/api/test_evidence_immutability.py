from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.postgres


def _evidence_rows(connection, inspection_id: str) -> dict[str, object]:
    internal = connection.execute(
        text(
            "SELECT id, spec_item_id FROM internal_results "
            "WHERE inspection_case_id = :case ORDER BY id LIMIT 1"
        ),
        {"case": inspection_id},
    ).one()
    supplier = connection.execute(
        text(
            "SELECT id, standard_test_item_id FROM supplier_results "
            "WHERE inspection_case_id = :case ORDER BY id LIMIT 1"
        ),
        {"case": inspection_id},
    ).one()
    sample = connection.execute(
        text(
            "SELECT id FROM sample_measurements "
            "WHERE internal_result_id = :result ORDER BY id LIMIT 1"
        ),
        {"result": internal.id},
    ).one()
    return {
        "internal_id": internal.id,
        "spec_item_id": internal.spec_item_id,
        "supplier_id": supplier.id,
        "standard_test_item_id": supplier.standard_test_item_id,
        "sample_id": sample.id,
    }


def _counts(connection, inspection_id: str) -> dict[str, int]:
    return {
        "supplier": connection.execute(
            text("SELECT count(*) FROM supplier_results WHERE inspection_case_id = :case"),
            {"case": inspection_id},
        ).scalar_one(),
        "internal": connection.execute(
            text("SELECT count(*) FROM internal_results WHERE inspection_case_id = :case"),
            {"case": inspection_id},
        ).scalar_one(),
        "samples": connection.execute(
            text(
                "SELECT count(*) FROM sample_measurements s "
                "LEFT JOIN internal_results i ON i.id = s.internal_result_id "
                "LEFT JOIN supplier_results r ON r.id = s.supplier_result_id "
                "WHERE i.inspection_case_id = :case OR r.inspection_case_id = :case"
            ),
            {"case": inspection_id},
        ).scalar_one(),
    }


def test_app_role_denies_all_finalized_evidence_mutations_without_residue(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    ready = p3.clear_hold(inspection_id)
    submitted = p3.submit(inspection_id, ready["version"])
    approved = p3.approve(inspection_id, submitted["version"])
    assert approved.status_code == 200, approved.text
    unfinalized = p3.reviewed()
    p3.clear_hold(unfinalized["inspection_id"])

    app_engine = create_engine(p3.app_database_url)
    with app_engine.connect() as connection:
        rows = _evidence_rows(connection, inspection_id)
        unfinalized_rows = _evidence_rows(connection, unfinalized["inspection_id"])
        before = _counts(connection, inspection_id)
        unfinalized_before = _counts(connection, unfinalized["inspection_id"])

    statements = (
        (
            "INSERT INTO supplier_results "
            "(id, inspection_case_id, standard_test_item_id, supplier_item_name, "
            "mapping_status, lock_version, created_at, updated_at) "
            "VALUES (:new_id, :case, :standard, 'blocked', 'MANUAL_CONFIRMED', 1, now(), now())",
            {"standard": rows["standard_test_item_id"]},
        ),
        (
            "INSERT INTO internal_results "
            "(id, inspection_case_id, spec_item_id, evaluated_value, lock_version, "
            "created_at, updated_at) "
            "VALUES (:new_id, :case, :spec, 0.10, 1, now(), now())",
            {"spec": rows["spec_item_id"]},
        ),
        (
            "INSERT INTO sample_measurements "
            "(id, internal_result_id, sample_index, numeric_value, lock_version, "
            "created_at, updated_at) "
            "VALUES (:new_id, :internal, 99, 0.10, 1, now(), now())",
            {"internal": rows["internal_id"]},
        ),
        (
            "UPDATE supplier_results SET supplier_item_name = 'blocked', "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"target": rows["supplier_id"]},
        ),
        (
            "UPDATE internal_results SET evaluated_value = 0.20, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"target": rows["internal_id"]},
        ),
        (
            "UPDATE sample_measurements SET numeric_value = 0.20, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"target": rows["sample_id"]},
        ),
        (
            "UPDATE supplier_results SET inspection_case_id = :new_case, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {
                "new_case": unfinalized["inspection_id"],
                "target": rows["supplier_id"],
            },
        ),
        (
            "UPDATE supplier_results SET inspection_case_id = :new_case, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"new_case": inspection_id, "target": unfinalized_rows["supplier_id"]},
        ),
        (
            "UPDATE internal_results SET inspection_case_id = :new_case, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {
                "new_case": unfinalized["inspection_id"],
                "target": rows["internal_id"],
            },
        ),
        (
            "UPDATE internal_results SET inspection_case_id = :new_case, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"new_case": inspection_id, "target": unfinalized_rows["internal_id"]},
        ),
        (
            "UPDATE sample_measurements SET internal_result_id = :new_parent, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {
                "new_parent": unfinalized_rows["internal_id"],
                "target": rows["sample_id"],
            },
        ),
        (
            "UPDATE sample_measurements SET internal_result_id = :new_parent, "
            "lock_version = lock_version + 1 WHERE id = :target",
            {"new_parent": rows["internal_id"], "target": unfinalized_rows["sample_id"]},
        ),
        ("DELETE FROM supplier_results WHERE id = :target", {"target": rows["supplier_id"]}),
        ("DELETE FROM internal_results WHERE id = :target", {"target": rows["internal_id"]}),
        ("DELETE FROM sample_measurements WHERE id = :target", {"target": rows["sample_id"]}),
    )
    for statement, params in statements:
        with pytest.raises(DatabaseError, match="finalized inspection evidence is immutable"):
            with app_engine.begin() as connection:
                connection.execute(
                    text(statement),
                    {"new_id": uuid4(), "case": inspection_id} | params,
                )

    with app_engine.connect() as connection:
        assert _counts(connection, inspection_id) == before
        assert _counts(connection, unfinalized["inspection_id"]) == unfinalized_before
    app_engine.dispose()


def test_app_role_allows_unfinalized_evidence_insert_update_delete(p3) -> None:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    app_engine = create_engine(p3.app_database_url)
    supplier_id, internal_id, sample_id = uuid4(), uuid4(), uuid4()
    with app_engine.begin() as connection:
        spec_item_id = connection.execute(
            text(
                "SELECT id FROM spec_items WHERE spec_version_id = "
                "(SELECT spec_version_id FROM inspection_cases WHERE id = :case) "
                "ORDER BY id LIMIT 1"
            ),
            {"case": inspection_id},
        ).scalar_one()
        connection.execute(
            text(
                "INSERT INTO supplier_results "
                "(id, inspection_case_id, supplier_item_name, mapping_status, "
                "lock_version, created_at, updated_at) "
                "VALUES (:id, :case, 'positive', 'UNMAPPED', 1, now(), now())"
            ),
            {"id": supplier_id, "case": inspection_id},
        )
        connection.execute(
            text(
                "INSERT INTO internal_results "
                "(id, inspection_case_id, spec_item_id, evaluated_value, lock_version, "
                "created_at, updated_at) "
                "VALUES (:id, :case, :spec, 0.10, 1, now(), now())"
            ),
            {"id": internal_id, "case": inspection_id, "spec": spec_item_id},
        )
        connection.execute(
            text(
                "INSERT INTO sample_measurements "
                "(id, internal_result_id, sample_index, numeric_value, lock_version, "
                "created_at, updated_at) "
                "VALUES (:id, :internal, 1, 0.10, 1, now(), now())"
            ),
            {"id": sample_id, "internal": internal_id},
        )
        connection.execute(
            text(
                "UPDATE supplier_results SET supplier_item_name = 'updated', "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": supplier_id},
        )
        connection.execute(
            text(
                "UPDATE internal_results SET evaluated_value = 0.20, "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": internal_id},
        )
        connection.execute(
            text(
                "UPDATE sample_measurements SET numeric_value = 0.20, "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": sample_id},
        )
        connection.execute(
            text("DELETE FROM sample_measurements WHERE id = :id"), {"id": sample_id}
        )
        connection.execute(text("DELETE FROM internal_results WHERE id = :id"), {"id": internal_id})
        connection.execute(text("DELETE FROM supplier_results WHERE id = :id"), {"id": supplier_id})

    with app_engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT count(*) FROM supplier_results WHERE id = :supplier "
                "OR id = :internal OR id = :sample"
            ),
            {"supplier": supplier_id, "internal": internal_id, "sample": sample_id},
        ).scalar_one() == 0
        assert connection.execute(
            text("SELECT count(*) FROM internal_results WHERE id = :id"), {"id": internal_id}
        ).scalar_one() == 0
        assert connection.execute(
            text("SELECT count(*) FROM sample_measurements WHERE id = :id"), {"id": sample_id}
        ).scalar_one() == 0
    app_engine.dispose()
