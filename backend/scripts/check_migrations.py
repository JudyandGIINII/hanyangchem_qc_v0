from __future__ import annotations

import argparse
import sys
import tempfile
from collections.abc import Set as AbstractSet
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

from alembic import command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from hyc_data.models import Base  # noqa: E402

EXPECTED_MIGRATION_HEAD = "20260813_0012"

EXPECTED_P3_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {
        "hyc_deny_finalized_evidence_mutation",
        "hyc_guard_document_allocation_link_mutation",
        "hyc_guard_document_section_mutation",
        "hyc_guard_extraction_review_mutation",
        "hyc_guard_extraction_run_mutation",
    }
)
EXPECTED_P3_TRIGGERS: frozenset[str] = frozenset(
    {
        "trg_document_allocation_links_confirmed_immutable",
        "trg_document_sections_confirmed_immutable",
        "trg_extraction_field_reviews_confirmed_immutable",
        "trg_extraction_runs_confirmed_immutable",
        "trg_internal_results_finalized_immutable",
        "trg_sample_measurements_finalized_immutable",
        "trg_supplier_results_finalized_immutable",
    }
)
EXPECTED_P3_PARTIAL_UNIQUE_INDEXES: frozenset[str] = frozenset(
    {
        "uq_document_one_confirmed_extraction_run",
        "uq_document_section_one_confirmed_allocation",
    }
)

EXPECTED_NCR_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {
        "hyc_deny_approved_nonconformance_mutation",
        "hyc_deny_nonconformance_disposition_delete",
    }
)
EXPECTED_NCR_TRIGGERS: frozenset[str] = frozenset(
    {
        "trg_approved_nonconformance_immutable",
        "trg_nonconformance_disposition_no_delete",
    }
)

EXPECTED_MASTER_IMPORT_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {"hyc_deny_master_import_row_mutation"}
)
EXPECTED_MASTER_IMPORT_TRIGGERS: frozenset[str] = frozenset(
    {"trg_master_import_row_immutable"}
)
EXPECTED_REPORT_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {"hyc_deny_report_artifact_mutation"}
)
EXPECTED_REPORT_TRIGGERS: frozenset[str] = frozenset(
    {"trg_report_artifact_immutable"}
)

EXPECTED_TRACEABILITY_TRIGGER_FUNCTIONS: frozenset[str] = frozenset(
    {"hyc_deny_material_lot_consumption_mutation"}
)
EXPECTED_TRACEABILITY_TRIGGERS: frozenset[str] = frozenset(
    {"trg_material_lot_consumption_immutable"}
)

EXPECTED_P2_TABLES: frozenset[str] = frozenset(
    {
        "approvals",
        "audit_logs",
        "bill_of_materials",
        "decision_snapshots",
        "document_allocation_links",
        "document_sections",
        "documents",
        "extraction_field_reviews",
        "extraction_runs",
        "idempotency_keys",
        "inbound_receipts",
        "ingest_cursors",
        "master_import_batches",
        "master_import_rows",
        "inspection_cases",
        "inspection_return_reasons",
        "internal_results",
        "lot_merge_approvals",
        "material_lots",
        "material_models",
        "material_lot_consumptions",
        "materials",
        "nonconformance_actions",
        "nonconformance_approvals",
        "nonconformance_attachments",
        "nonconformance_dispositions",
        "nonconformances",
        "outbox_events",
        "production_lots",
        "receipt_lot_allocations",
        "report_artifacts",
        "report_jobs",
        "sample_measurements",
        "spec_items",
        "spec_profiles",
        "spec_versions",
        "standard_test_items",
        "standard_test_item_aliases",
        "supplier_results",
        "suppliers",
    }
)


def _table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def _postgres_runtime_objects(connection: Connection) -> tuple[set[str], set[str], set[str]]:
    functions = set(
        connection.execute(
            text(
                "SELECT p.proname FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = current_schema()"
            )
        ).scalars()
    )
    triggers = set(
        connection.execute(
            text("SELECT tgname FROM pg_trigger WHERE NOT tgisinternal")
        ).scalars()
    )
    indexes = set(
        connection.execute(
            text(
                "SELECT indexname FROM pg_indexes "
                "WHERE schemaname = current_schema() AND indexdef LIKE 'CREATE UNIQUE INDEX%'"
            )
        ).scalars()
    )
    return functions, triggers, indexes


def run_cycle(database_url: str, *, expected_tables: AbstractSet[str]) -> None:
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")
    if _table_names(database_url) != expected_tables | {"alembic_version"}:
        raise RuntimeError(f"unexpected table set at head: {_table_names(database_url)}")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            revision = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            drift = compare_metadata(
                MigrationContext.configure(
                    connection,
                    opts={"compare_type": True},
                ),
                Base.metadata,
            )
            if revision != EXPECTED_MIGRATION_HEAD:
                raise RuntimeError(f"unexpected migration head: {revision}")
            if drift:
                raise RuntimeError(f"model/migration autogenerate drift is not empty: {drift!r}")
            if connection.dialect.name == "postgresql":
                functions, triggers, indexes = _postgres_runtime_objects(connection)
                if not EXPECTED_P3_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("P3 trigger functions are incomplete at head")
                if not EXPECTED_P3_TRIGGERS.issubset(triggers):
                    raise RuntimeError("P3 mutation triggers are incomplete at head")
                if not EXPECTED_P3_PARTIAL_UNIQUE_INDEXES.issubset(indexes):
                    raise RuntimeError("P3 partial unique indexes are incomplete at head")
                if not EXPECTED_NCR_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("NCR trigger functions are incomplete at head")
                if not EXPECTED_NCR_TRIGGERS.issubset(triggers):
                    raise RuntimeError("NCR mutation triggers are incomplete at head")
                if not EXPECTED_MASTER_IMPORT_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("master import trigger functions are incomplete at head")
                if not EXPECTED_MASTER_IMPORT_TRIGGERS.issubset(triggers):
                    raise RuntimeError("master import mutation triggers are incomplete at head")
                if not EXPECTED_REPORT_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("report trigger functions are incomplete at head")
                if not EXPECTED_REPORT_TRIGGERS.issubset(triggers):
                    raise RuntimeError("report mutation triggers are incomplete at head")
                if not EXPECTED_TRACEABILITY_TRIGGER_FUNCTIONS.issubset(functions):
                    raise RuntimeError("traceability trigger functions are incomplete at head")
                if not EXPECTED_TRACEABILITY_TRIGGERS.issubset(triggers):
                    raise RuntimeError("traceability mutation triggers are incomplete at head")
    finally:
        engine.dispose()
    command.downgrade(config, "base")
    if _table_names(database_url) != {"alembic_version"}:
        raise RuntimeError(
            f"P2 tables remain after downgrade to base: {_table_names(database_url)}"
        )
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                functions, triggers, indexes = _postgres_runtime_objects(connection)
                if EXPECTED_P3_TRIGGER_FUNCTIONS.intersection(functions):
                    raise RuntimeError("P3 trigger functions remain after downgrade")
                if EXPECTED_P3_TRIGGERS.intersection(triggers):
                    raise RuntimeError("P3 triggers remain after downgrade")
                if EXPECTED_P3_PARTIAL_UNIQUE_INDEXES.intersection(indexes):
                    raise RuntimeError("P3 partial unique indexes remain after downgrade")
                if EXPECTED_NCR_TRIGGER_FUNCTIONS.intersection(functions):
                    raise RuntimeError("NCR trigger functions remain after downgrade")
                if EXPECTED_NCR_TRIGGERS.intersection(triggers):
                    raise RuntimeError("NCR triggers remain after downgrade")
                if EXPECTED_REPORT_TRIGGER_FUNCTIONS.intersection(functions):
                    raise RuntimeError("report trigger functions remain after downgrade")
                if EXPECTED_REPORT_TRIGGERS.intersection(triggers):
                    raise RuntimeError("report triggers remain after downgrade")
                if EXPECTED_TRACEABILITY_TRIGGER_FUNCTIONS.intersection(functions):
                    raise RuntimeError("traceability trigger functions remain after downgrade")
                if EXPECTED_TRACEABILITY_TRIGGERS.intersection(triggers):
                    raise RuntimeError("traceability triggers remain after downgrade")
    finally:
        engine.dispose()
    command.upgrade(config, "head")
    if _table_names(database_url) != expected_tables | {"alembic_version"}:
        raise RuntimeError(f"table set was not restored at head: {_table_names(database_url)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--postgres-url")
    parser.add_argument("--expect-tables")
    args = parser.parse_args()
    expected_tables = (
        {name for name in args.expect_tables.split(",") if name}
        if args.expect_tables is not None
        else EXPECTED_P2_TABLES
    )
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "p1-migration-check.sqlite"
        run_cycle(f"sqlite:///{database}", expected_tables=expected_tables)
    if args.postgres_url:
        run_cycle(args.postgres_url, expected_tables=expected_tables)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
