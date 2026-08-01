from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DatabaseError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import MaterialLot, Supplier
from hyc_data.repositories import LotRepository
from hyc_domain.snapshots import canonical_hash

POSTGRES_DSN = os.environ.get("HYC_P2_TEST_POSTGRES_DSN")
APP_DSN = os.environ.get("HYC_P2_TEST_APP_DSN")
pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine():
    if not POSTGRES_DSN:
        pytest.skip(
            "HYC_P2_TEST_POSTGRES_DSN must explicitly name a disposable PostgreSQL database"
        )
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_DSN)
    command.upgrade(config, "head")
    value = create_engine(POSTGRES_DSN)
    yield value
    command.downgrade(config, "base")
    with value.connect() as connection:
        remaining = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        )
        assert remaining.scalar_one() == 0
    value.dispose()


@pytest.fixture(scope="module")
def app_engine(engine):
    if not APP_DSN:
        pytest.skip("HYC_P2_TEST_APP_DSN must name the disposable synthetic app role")
    value = create_engine(APP_DSN)
    yield value
    value.dispose()


def _snapshot_payload(overall: str = "ACCEPTED") -> dict[str, object]:
    return {
        "spec_version": {"id": "spec-v1", "semantic_version": 1},
        "spec_items": [{"id": "item-1", "operator": "GTE", "lower": "1"}],
        "mapping": [{"status": "MANUAL_CONFIRMED"}],
        "supplier_results": [{"status": "MISSING"}],
        "internal_results": [{"value": "2"}],
        "unit_conversions": {"version": "conversion-v1"},
        "item_decisions": [{"overall": overall}],
        "source_policy": ["INTERNAL_ONLY"],
        "missing_policy": ["HOLD"],
        "overall_decision": overall,
        "document_hashes": ["a" * 64],
        "engine_version": "engine-v1",
        "policy_version": "policy-v1",
        "rounding_version": "round-v1",
        "conversion_version": "conversion-v1",
        "approver": {"actor_id": "lead-1", "role": "LEAD"},
        "sample_policy": ["ALL_SAMPLES_IN_SPEC"],
        "lot_reference": {"lot_id": "lot-1"},
        "allocation_reference": {"allocation_id": "allocation-1"},
        "decision_reasons": {"reason": "engine match"},
    }


def _insert_snapshot(connection, *, case_id: UUID, payload: dict[str, object]) -> UUID:
    snapshot_id = uuid4()
    connection.execute(
        text(
            "INSERT INTO decision_snapshots "
            "(id, inspection_case_id, payload, content_hash, created_at) "
            "VALUES (:id, :case, CAST(:payload AS jsonb), :hash, now())"
        ),
        {
            "id": snapshot_id,
            "case": case_id,
            "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            "hash": canonical_hash(payload),
        },
    )
    return snapshot_id


def _insert_finalization_evidence(
    connection,
    *,
    case_id: UUID,
    inspector_id: UUID,
    candidate: str = "ACCEPTED",
    reason: str | None = None,
) -> None:
    _insert_snapshot(
        connection,
        case_id=case_id,
        payload=_snapshot_payload(candidate),
    )
    lead_id = uuid4()
    assert lead_id != inspector_id
    connection.execute(
        text(
            "INSERT INTO approvals "
            "(id, inspection_case_id, action, actor_id, actor_role, created_at) "
            "VALUES (:id, :case, 'APPROVE', :actor, 'LEAD', now())"
        ),
        {"id": uuid4(), "case": case_id, "actor": lead_id},
    )
    connection.execute(
        text(
            "INSERT INTO audit_logs "
            "(id, entity_type, entity_id, action, reason, payload, created_at) "
            "VALUES (:id, 'inspection_case', :case, 'FINALIZE', :reason, "
            "'{}'::jsonb, now())"
        ),
        {"id": uuid4(), "case": case_id, "reason": reason},
    )
    connection.execute(
        text(
            "INSERT INTO outbox_events (id, topic, payload, created_at) "
            "VALUES (:id, 'inspection.finalized', "
            "jsonb_build_object('inspection_case_id', CAST(:case AS text)), now())"
        ),
        {"id": uuid4(), "case": case_id},
    )


def _insert_finalization_rows(
    connection,
    *,
    case_id: UUID,
    inspector_id: UUID,
    candidate: str = "ACCEPTED",
    final: str = "ACCEPTED",
    reason: str | None = None,
) -> None:
    _insert_finalization_evidence(
        connection,
        case_id=case_id,
        inspector_id=inspector_id,
        candidate=candidate,
        reason=reason,
    )
    connection.execute(
        text(
            "UPDATE inspection_cases SET candidate_decision = :candidate, "
            "final_decision = :final, status = :final, "
            "lock_version = lock_version + 1 WHERE id = :case"
        ),
        {"candidate": candidate, "final": final, "case": case_id},
    )


def _insert_finalized_case_directly(
    connection,
    *,
    case_id: UUID,
    template_case_id: UUID,
    inspector_id: UUID,
) -> None:
    connection.execute(
        text(
            "INSERT INTO inspection_cases "
            "(id, receipt_lot_allocation_id, spec_version_id, status, candidate_decision, "
            "final_decision, submitted_by_id, lock_version, created_at, updated_at) "
            "SELECT :case, receipt_lot_allocation_id, spec_version_id, 'ACCEPTED', "
            "'ACCEPTED', 'ACCEPTED', :inspector, 1, now(), now() "
            "FROM inspection_cases WHERE id = :template"
        ),
        {"case": case_id, "template": template_case_id, "inspector": inspector_id},
    )
    _insert_finalization_evidence(
        connection,
        case_id=case_id,
        inspector_id=inspector_id,
    )


def _seed_case(
    engine,
    *,
    spec_status: str = "DRAFT",
    case_status: str = "DRAFT",
    submitted_by_id: UUID | None = None,
) -> UUID:
    supplier_id, material_id, lot_id, receipt_id, allocation_id = (uuid4() for _ in range(5))
    profile_id, spec_version_id, case_id = (uuid4() for _ in range(3))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO suppliers (id, name, active, lock_version, created_at, updated_at) VALUES (:id, 's', true, 1, now(), now())"
            ),
            {"id": supplier_id},
        )
        connection.execute(
            text(
                "INSERT INTO materials (id, name, active, lock_version, created_at, updated_at) VALUES (:id, 'm', true, 1, now(), now())"
            ),
            {"id": material_id},
        )
        connection.execute(
            text(
                "INSERT INTO material_lots (id, supplier_id, material_id, identity_policy_version, identity_key, identity_status, lock_version, created_at, updated_at) VALUES (:id, :supplier, :material, 'v1', :key, 'CANONICAL', 1, now(), now())"
            ),
            {
                "id": lot_id,
                "supplier": supplier_id,
                "material": material_id,
                "key": f"lot-{lot_id}",
            },
        )
        connection.execute(
            text(
                "INSERT INTO inbound_receipts (id, inbound_no, supplier_id, receipt_date, status, lock_version, created_at, updated_at) VALUES (:id, :inbound, :supplier, :receipt_date, 'DRAFT', 1, now(), now())"
            ),
            {
                "id": receipt_id,
                "inbound": f"IN-{receipt_id}",
                "supplier": supplier_id,
                "receipt_date": date(2026, 1, 1),
            },
        )
        connection.execute(
            text(
                "INSERT INTO receipt_lot_allocations (id, inbound_receipt_id, material_lot_id, quantity, quantity_unit, lock_version, created_at, updated_at) VALUES (:id, :receipt, :lot, 1.0, 'kg', 1, now(), now())"
            ),
            {"id": allocation_id, "receipt": receipt_id, "lot": lot_id},
        )
        connection.execute(
            text(
                "INSERT INTO spec_profiles (id, material_id, name, lock_version, created_at, updated_at) VALUES (:id, :material, 'p', 1, now(), now())"
            ),
            {"id": profile_id, "material": material_id},
        )
        connection.execute(
            text(
                "INSERT INTO spec_versions (id, spec_profile_id, version, status, effective_from, lock_version, created_at, updated_at) VALUES (:id, :profile, 1, :status, :start, 1, now(), now())"
            ),
            {
                "id": spec_version_id,
                "profile": profile_id,
                "status": spec_status,
                "start": date(2026, 1, 1),
            },
        )
        connection.execute(
            text(
                "INSERT INTO inspection_cases (id, receipt_lot_allocation_id, spec_version_id, status, submitted_by_id, lock_version, created_at, updated_at) VALUES (:id, :allocation, :spec, :status, :submitted, 1, now(), now())"
            ),
            {
                "id": case_id,
                "allocation": allocation_id,
                "spec": spec_version_id,
                "status": case_status,
                "submitted": submitted_by_id,
            },
        )
    return case_id


def test_postgres_immutable_snapshot_document_audit_and_approval_guards(engine) -> None:
    case_id = _seed_case(engine)
    document_id, approval_id, audit_id = (uuid4() for _ in range(3))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO documents (id, checksum_sha256, document_type, original_filename, immutable, created_at) VALUES (:id, :hash, 'COA', 'fixture.pdf', true, now())"
            ),
            {"id": document_id, "hash": str(document_id).replace("-", "") * 2},
        )
        snapshot_id = _insert_snapshot(
            connection,
            case_id=case_id,
            payload=_snapshot_payload(),
        )
        connection.execute(
            text(
                "INSERT INTO approvals (id, inspection_case_id, action, actor_id, actor_role, created_at) VALUES (:id, :case, 'APPROVE', :actor, 'LEAD', now())"
            ),
            {"id": approval_id, "case": case_id, "actor": uuid4()},
        )
        connection.execute(
            text(
                "INSERT INTO audit_logs (id, entity_type, entity_id, action, payload, created_at) VALUES (:id, 'case', :entity, 'CREATE', '{}'::jsonb, now())"
            ),
            {"id": audit_id, "entity": case_id},
        )
    for table, row_id in (
        ("documents", document_id),
        ("decision_snapshots", snapshot_id),
        ("approvals", approval_id),
        ("audit_logs", audit_id),
    ):
        for statement in (
            f"UPDATE {table} SET id = id WHERE id = :id",
            f"DELETE FROM {table} WHERE id = :id",
        ):
            with pytest.raises(DatabaseError):
                with engine.begin() as connection:
                    connection.execute(text(statement), {"id": row_id})


def test_postgres_app_role_can_append_and_read_but_cannot_mutate_immutable_tables(
    engine, app_engine
) -> None:
    case_id = _seed_case(engine)
    with engine.connect() as connection:
        lot_id = connection.execute(text("SELECT id FROM material_lots LIMIT 1")).scalar_one()
    ids = {
        "audit_logs": uuid4(),
        "documents": uuid4(),
        "decision_snapshots": uuid4(),
        "approvals": uuid4(),
        "lot_merge_approvals": uuid4(),
        "outbox_events": uuid4(),
    }
    payload = _snapshot_payload()
    with app_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO audit_logs (id, entity_type, entity_id, action, payload, created_at) VALUES (:id, 'case', :entity, 'CREATE', '{}'::jsonb, now())"
            ),
            {"id": ids["audit_logs"], "entity": case_id},
        )
        connection.execute(
            text(
                "INSERT INTO documents "
                "(id, checksum_sha256, document_type, original_filename, immutable, created_at) "
                "VALUES (:id, :hash, 'COA', 'app-fixture.pdf', true, now())"
            ),
            {"id": ids["documents"], "hash": "e" * 64},
        )
        connection.execute(
            text(
                "INSERT INTO decision_snapshots "
                "(id, inspection_case_id, payload, content_hash, created_at) "
                "VALUES (:id, :case, CAST(:payload AS jsonb), :hash, now())"
            ),
            {
                "id": ids["decision_snapshots"],
                "case": case_id,
                "payload": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                "hash": canonical_hash(payload),
            },
        )
        connection.execute(
            text(
                "INSERT INTO approvals "
                "(id, inspection_case_id, action, actor_id, actor_role, created_at) "
                "VALUES (:id, :case, 'APPROVE', :actor, 'LEAD', now())"
            ),
            {"id": ids["approvals"], "case": case_id, "actor": uuid4()},
        )
        connection.execute(
            text(
                "INSERT INTO lot_merge_approvals "
                "(id, material_lot_id, role, actor_id, created_at) "
                "VALUES (:id, :lot, 'LEAD', :actor, now())"
            ),
            {"id": ids["lot_merge_approvals"], "lot": lot_id, "actor": uuid4()},
        )
        connection.execute(
            text(
                "INSERT INTO outbox_events (id, topic, payload, created_at) "
                "VALUES (:id, 'test.event', '{}'::jsonb, now())"
            ),
            {"id": ids["outbox_events"]},
        )
        for table, row_id in ids.items():
            assert connection.execute(
                text(f"SELECT id FROM {table} WHERE id = :id"),
                {"id": row_id},
            ).scalar_one() == row_id

        mutable_id = uuid4()
        connection.execute(
            text(
                "INSERT INTO suppliers "
                "(id, name, active, lock_version, created_at, updated_at) "
                "VALUES (:id, 'app-mutable', true, 1, now(), now())"
            ),
            {"id": mutable_id},
        )
        connection.execute(
            text(
                "UPDATE suppliers SET name = 'app-updated', "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": mutable_id},
        )
        connection.execute(text("DELETE FROM suppliers WHERE id = :id"), {"id": mutable_id})

    for table, row_id in ids.items():
        for verb in ("UPDATE", "DELETE"):
            statement = (
                f"UPDATE {table} SET id = id WHERE id = :id"
                if verb == "UPDATE"
                else f"DELETE FROM {table} WHERE id = :id"
            )
            with pytest.raises(DatabaseError):
                with app_engine.begin() as connection:
                    connection.execute(text(statement), {"id": row_id})

    immutable = tuple(ids)
    mutable = (
        "suppliers",
        "materials",
        "material_lots",
        "inspection_cases",
        "idempotency_keys",
    )
    with engine.connect() as connection:
        for table in immutable:
            assert connection.execute(
                text("SELECT has_table_privilege('hyc_app_test', :table, 'INSERT')"),
                {"table": table},
            ).scalar_one()
            assert not connection.execute(
                text("SELECT has_table_privilege('hyc_app_test', :table, 'UPDATE')"),
                {"table": table},
            ).scalar_one()
            assert not connection.execute(
                text("SELECT has_table_privilege('hyc_app_test', :table, 'DELETE')"),
                {"table": table},
            ).scalar_one()
        for table in mutable:
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                assert connection.execute(
                    text(
                        "SELECT has_table_privilege("
                        "'hyc_app_test', :table, :privilege)"
                    ),
                    {"table": table, "privilege": privilege},
                ).scalar_one()


def test_postgres_active_spec_overlap_trigger_serializes_competing_active_inserts(engine) -> None:
    supplier_id, material_id, profile_id = (uuid4() for _ in range(3))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO suppliers (id, name, active, lock_version, created_at, updated_at) VALUES (:id, 's', true, 1, now(), now())"
            ),
            {"id": supplier_id},
        )
        connection.execute(
            text(
                "INSERT INTO materials (id, name, active, lock_version, created_at, updated_at) VALUES (:id, 'm', true, 1, now(), now())"
            ),
            {"id": material_id},
        )
        connection.execute(
            text(
                "INSERT INTO spec_profiles (id, material_id, supplier_id, name, lock_version, created_at, updated_at) VALUES (:id, :material, :supplier, 'p', 1, now(), now())"
            ),
            {"id": profile_id, "material": material_id, "supplier": supplier_id},
        )
    first_inserted = Event()
    release_first = Event()

    def insert_active(version: int, wait: bool) -> str:
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO spec_versions (id, spec_profile_id, version, status, effective_from, lock_version, created_at, updated_at) VALUES (:id, :profile, :version, 'ACTIVE', :start, 1, now(), now())"
                    ),
                    {
                        "id": uuid4(),
                        "profile": profile_id,
                        "version": version,
                        "start": date(2026, 1, 1),
                    },
                )
                first_inserted.set()
                if wait:
                    assert release_first.wait(timeout=5)
            return "inserted"
        except DatabaseError:
            return "rejected"

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(insert_active, 1, True)
        assert first_inserted.wait(timeout=5)
        second = pool.submit(insert_active, 2, False)
        release_first.set()
        assert first.result(timeout=10) == "inserted"
        assert second.result(timeout=10) == "rejected"
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE spec_profiles SET supplier_id = NULL WHERE id = :profile"),
                {"profile": profile_id},
            )


def test_postgres_canonical_lot_identity_is_unique_under_concurrent_creation(
    engine,
) -> None:
    supplier_id, material_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO suppliers "
                "(id, name, active, lock_version, created_at, updated_at) "
                "VALUES (:id, 'concurrent-supplier', true, 1, now(), now())"
            ),
            {"id": supplier_id},
        )
        connection.execute(
            text(
                "INSERT INTO materials "
                "(id, name, active, lock_version, created_at, updated_at) "
                "VALUES (:id, 'concurrent-material', true, 1, now(), now())"
            ),
            {"id": material_id},
        )
    barrier = Barrier(2)

    def create_lot() -> UUID:
        barrier.wait(timeout=5)
        with Session(engine) as session, session.begin():
            lot = LotRepository().get_or_create_canonical(
                session,
                MaterialLot(
                    supplier_id=supplier_id,
                    material_id=material_id,
                    identity_policy_version="v1",
                    identity_key="same-key",
                    identity_status="CANONICAL",
                ),
            )
            return lot.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = (pool.submit(create_lot), pool.submit(create_lot))
        canonical_ids = tuple(future.result(timeout=10) for future in futures)
    assert canonical_ids[0] == canonical_ids[1]
    with engine.connect() as connection:
        assert (
            connection.execute(
                text(
                    "SELECT count(*) FROM material_lots WHERE supplier_id = :supplier "
                    "AND material_id = :material AND identity_policy_version = 'v1' "
                    "AND identity_key = 'same-key'"
                ),
                {"supplier": supplier_id, "material": material_id},
            ).scalar_one()
            == 1
        )


def test_postgres_rejects_forged_and_all_null_decision_snapshots(engine) -> None:
    for payload, content_hash in (
        (_snapshot_payload(), "f" * 64),
        (
            {key: None for key in _snapshot_payload()},
            canonical_hash({key: None for key in _snapshot_payload()}),
        ),
    ):
        case_id = _seed_case(engine)
        with pytest.raises(DatabaseError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO decision_snapshots "
                        "(id, inspection_case_id, payload, content_hash, created_at) "
                        "VALUES (:id, :case, CAST(:payload AS jsonb), :hash, now())"
                    ),
                    {
                        "id": uuid4(),
                        "case": case_id,
                        "payload": json.dumps(payload, separators=(",", ":")),
                        "hash": content_hash,
                    },
                )
        with engine.connect() as connection:
            assert connection.execute(
                text(
                    "SELECT count(*) FROM decision_snapshots "
                    "WHERE inspection_case_id = :case"
                ),
                {"case": case_id},
            ).scalar_one() == 0


def test_postgres_final_decision_requires_snapshot_and_approval_but_accepts_atomic_path(
    engine,
) -> None:
    inspector_id = uuid4()
    missing_snapshot = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE inspection_cases SET candidate_decision = 'ACCEPTED', "
                    "final_decision = 'ACCEPTED', status = 'ACCEPTED', "
                    "lock_version = lock_version + 1 WHERE id = :id"
                ),
                {"id": missing_snapshot},
            )
    missing_approval = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            _insert_snapshot(
                connection,
                case_id=missing_approval,
                payload=_snapshot_payload(),
            )
            connection.execute(
                text(
                    "UPDATE inspection_cases SET candidate_decision = 'ACCEPTED', "
                    "final_decision = 'ACCEPTED', status = 'ACCEPTED', "
                    "lock_version = lock_version + 1 WHERE id = :id"
                ),
                {"id": missing_approval},
            )

    draft = _seed_case(
        engine,
        spec_status="DRAFT",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            _insert_finalization_rows(
                connection,
                case_id=draft,
                inspector_id=inspector_id,
            )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT final_decision FROM inspection_cases WHERE id = :id"),
            {"id": draft},
        ).scalar_one() is None
        assert connection.execute(
            text("SELECT count(*) FROM decision_snapshots WHERE inspection_case_id = :id"),
            {"id": draft},
        ).scalar_one() == 0

    complete = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with engine.begin() as connection:
        _insert_finalization_rows(
            connection,
            case_id=complete,
            inspector_id=inspector_id,
        )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT final_decision FROM inspection_cases WHERE id = :id"), {"id": complete}
            ).scalar_one()
            == "ACCEPTED"
        )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE inspection_cases SET status = 'CLOSED', "
                    "lock_version = lock_version + 1 WHERE id = :id"
                ),
                {"id": complete},
            )
    correction_id = uuid4()
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO inspection_cases "
                    "(id, receipt_lot_allocation_id, spec_version_id, status, "
                    "correction_of_case_id, revision_no, lock_version, created_at, updated_at) "
                    "SELECT :correction, receipt_lot_allocation_id, spec_version_id, 'DRAFT', "
                    "id, 3, 1, now(), now() FROM inspection_cases WHERE id = :id"
                ),
                {"correction": correction_id, "id": complete},
            )
    with engine.begin() as connection:
        correction_id = uuid4()
        connection.execute(
            text(
                "INSERT INTO inspection_cases "
                "(id, receipt_lot_allocation_id, spec_version_id, status, "
                "correction_of_case_id, revision_no, lock_version, created_at, updated_at) "
                "SELECT :correction, receipt_lot_allocation_id, spec_version_id, 'DRAFT', "
                "id, 2, 1, now(), now() FROM inspection_cases WHERE id = :id"
            ),
            {"correction": correction_id, "id": complete},
        )
    with engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT correction_of_case_id FROM inspection_cases WHERE id = :id"),
                {"id": correction_id},
            ).scalar_one()
            == complete
        )


def test_postgres_on_hold_cannot_be_directly_overridden_as_plain_accepted(engine) -> None:
    inspector_id = uuid4()
    denied = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            _insert_finalization_rows(
                connection,
                case_id=denied,
                inspector_id=inspector_id,
                candidate="ON_HOLD",
                final="ACCEPTED",
                reason="attempted fail-closed override",
            )
    with engine.connect() as connection:
        denied_state = connection.execute(
            text(
                "SELECT status, candidate_decision, final_decision, lock_version "
                "FROM inspection_cases WHERE id = :id"
            ),
            {"id": denied},
        ).one()
        assert denied_state == ("LEAD_REVIEW", None, None, 1)
        zero_partial_queries = (
            "SELECT count(*) FROM decision_snapshots WHERE inspection_case_id = :id",
            "SELECT count(*) FROM approvals WHERE inspection_case_id = :id",
            "SELECT count(*) FROM audit_logs "
            "WHERE entity_type = 'inspection_case' AND entity_id = :id",
            "SELECT count(*) FROM outbox_events "
            "WHERE payload::jsonb ->> 'inspection_case_id' = CAST(:id AS text)",
        )
        for query in zero_partial_queries:
            assert connection.execute(
                text(query),
                {"id": denied},
            ).scalar_one() == 0

    ordinary = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with engine.begin() as connection:
        _insert_finalization_rows(
            connection,
            case_id=ordinary,
            inspector_id=inspector_id,
            candidate="ACCEPTED",
            final="ACCEPTED",
        )

    special = _seed_case(
        engine,
        spec_status="ACTIVE",
        case_status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    with engine.begin() as connection:
        _insert_finalization_rows(
            connection,
            case_id=special,
            inspector_id=inspector_id,
            candidate="ON_HOLD",
            final="SPECIAL_ACCEPTED",
            reason="authorized special acceptance of incomplete evidence",
        )
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT final_decision FROM inspection_cases WHERE id = :id"),
            {"id": ordinary},
        ).scalar_one() == "ACCEPTED"
        assert connection.execute(
            text("SELECT final_decision FROM inspection_cases WHERE id = :id"),
            {"id": special},
        ).scalar_one() == "SPECIAL_ACCEPTED"


def test_postgres_direct_finalized_insert_is_denied_and_unfinalized_insert_succeeds(
    engine, app_engine
) -> None:
    inspector_id = uuid4()
    template = _seed_case(
        engine,
        spec_status="ACTIVE",
        submitted_by_id=inspector_id,
    )
    denied = uuid4()
    with pytest.raises(DatabaseError):
        with app_engine.begin() as connection:
            _insert_finalized_case_directly(
                connection,
                case_id=denied,
                template_case_id=template,
                inspector_id=inspector_id,
            )

    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT count(*) FROM inspection_cases WHERE id = :id"),
            {"id": denied},
        ).scalar_one() == 0
        zero_partial_queries = (
            "SELECT count(*) FROM decision_snapshots WHERE inspection_case_id = :id",
            "SELECT count(*) FROM approvals WHERE inspection_case_id = :id",
            "SELECT count(*) FROM audit_logs "
            "WHERE entity_type = 'inspection_case' AND entity_id = :id",
            "SELECT count(*) FROM outbox_events "
            "WHERE payload::jsonb ->> 'inspection_case_id' = CAST(:id AS text)",
        )
        for query in zero_partial_queries:
            assert connection.execute(text(query), {"id": denied}).scalar_one() == 0

    ordinary = uuid4()
    with app_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO inspection_cases "
                "(id, receipt_lot_allocation_id, spec_version_id, status, submitted_by_id, "
                "lock_version, created_at, updated_at) "
                "SELECT :case, receipt_lot_allocation_id, spec_version_id, 'DRAFT', "
                ":inspector, 1, now(), now() FROM inspection_cases WHERE id = :template"
            ),
            {"case": ordinary, "template": template, "inspector": inspector_id},
        )
    with engine.connect() as connection:
        assert connection.execute(
            text(
                "SELECT status, candidate_decision, final_decision, lock_version "
                "FROM inspection_cases WHERE id = :id"
            ),
            {"id": ordinary},
        ).one() == ("DRAFT", None, None, 1)


def test_postgres_optimistic_lock_rejects_stale_direct_update(engine) -> None:
    case_id = _seed_case(engine)
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE inspection_cases SET status = 'MATCH_REVIEW' WHERE id = :id"),
                {"id": case_id},
            )
    with engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE inspection_cases SET status = 'MATCH_REVIEW', "
                "lock_version = lock_version + 1 WHERE id = :id"
            ),
            {"id": case_id},
        )

    with Session(engine) as session, session.begin():
        supplier = Supplier(name=f"versioned-{uuid4()}")
        session.add(supplier)
        session.flush()
        supplier_id = supplier.id
    with Session(engine) as session, session.begin():
        ordinary = session.get(Supplier, supplier_id)
        assert ordinary is not None
        assert ordinary.lock_version == 1
        ordinary.name = "versioned-updated"
    with Session(engine) as session:
        updated = session.get(Supplier, supplier_id)
        assert updated is not None
        assert updated.lock_version == 2


def test_postgres_lot_merge_requires_distinct_dual_approval_and_audit(engine) -> None:
    supplier_id, material_id, target_id, source_id = (uuid4() for _ in range(4))
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO suppliers "
                "(id, name, active, lock_version, created_at, updated_at) "
                "VALUES (:id, 'merge-supplier', true, 1, now(), now())"
            ),
            {"id": supplier_id},
        )
        connection.execute(
            text(
                "INSERT INTO materials "
                "(id, name, active, lock_version, created_at, updated_at) "
                "VALUES (:id, 'merge-material', true, 1, now(), now())"
            ),
            {"id": material_id},
        )
        connection.execute(
            text(
                "INSERT INTO material_lots "
                "(id, supplier_id, material_id, identity_policy_version, identity_key, "
                "identity_status, lock_version, created_at, updated_at) "
                "VALUES (:target, :supplier, :material, 'v1', 'canonical-target', "
                "'CANONICAL', 1, now(), now()), "
                "(:source, :supplier, :material, 'v1', NULL, "
                "'CONFLICT_REVIEW', 1, now(), now())"
            ),
            {
                "target": target_id,
                "source": source_id,
                "supplier": supplier_id,
                "material": material_id,
            },
        )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE material_lots SET identity_status = 'MERGED', "
                    "merged_into_id = :target, lock_version = lock_version + 1 "
                    "WHERE id = :source"
                ),
                {"target": target_id, "source": source_id},
            )
    same_actor = uuid4()
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO lot_merge_approvals "
                    "(id, material_lot_id, role, actor_id, created_at) VALUES "
                    "(:first, :source, 'LEAD', :actor, now()), "
                    "(:second, :source, 'ADMIN', :actor, now())"
                ),
                {
                    "first": uuid4(),
                    "second": uuid4(),
                    "source": source_id,
                    "actor": same_actor,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO audit_logs "
                    "(id, entity_type, entity_id, action, reason, payload, created_at) "
                    "VALUES (:id, 'material_lot', :source, 'LOT_MERGED', "
                    "'same actor must fail', '{}'::jsonb, now())"
                ),
                {"id": uuid4(), "source": source_id},
            )
            connection.execute(
                text(
                    "UPDATE material_lots SET identity_status = 'MERGED', "
                    "merged_into_id = :target, lock_version = lock_version + 1 "
                    "WHERE id = :source"
                ),
                {"target": target_id, "source": source_id},
            )
    manager_id, admin_id = uuid4(), uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO lot_merge_approvals "
                "(id, material_lot_id, role, actor_id, created_at) VALUES "
                "(:first, :source, 'LEAD', :manager, now()), "
                "(:second, :source, 'ADMIN', :admin, now())"
            ),
            {
                "first": uuid4(),
                "second": uuid4(),
                "source": source_id,
                "manager": manager_id,
                "admin": admin_id,
            },
        )
        connection.execute(
            text(
                "INSERT INTO audit_logs "
                "(id, entity_type, entity_id, action, reason, payload, created_at) "
                "VALUES (:id, 'material_lot', :source, 'LOT_MERGED', "
                "'synthetic dual approval', '{}'::jsonb, now())"
            ),
            {"id": uuid4(), "source": source_id},
        )
        connection.execute(
            text(
                "UPDATE material_lots SET identity_status = 'MERGED', "
                "merged_into_id = :target, lock_version = lock_version + 1 "
                "WHERE id = :source"
            ),
            {"target": target_id, "source": source_id},
        )
    with pytest.raises(DatabaseError):
        with engine.begin() as connection:
            receipt_id = uuid4()
            connection.execute(
                text(
                    "INSERT INTO inbound_receipts "
                    "(id, inbound_no, supplier_id, receipt_date, status, lock_version, "
                    "created_at, updated_at) VALUES "
                    "(:id, :number, :supplier, :received, 'DRAFT', 1, now(), now())"
                ),
                {
                    "id": receipt_id,
                    "number": f"IN-{receipt_id}",
                    "supplier": supplier_id,
                    "received": date(2026, 1, 2),
                },
            )
            connection.execute(
                text(
                    "INSERT INTO receipt_lot_allocations "
                    "(id, inbound_receipt_id, material_lot_id, quantity, quantity_unit, "
                    "lock_version, created_at, updated_at) VALUES "
                    "(:id, :receipt, :lot, 1, 'kg', 1, now(), now())"
                ),
                {"id": uuid4(), "receipt": receipt_id, "lot": source_id},
            )
