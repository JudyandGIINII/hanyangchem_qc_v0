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

from alembic import command

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from hyc_data.models import Base  # noqa: E402

EXPECTED_MIGRATION_HEAD = "20260801_0003"

EXPECTED_P2_TABLES: frozenset[str] = frozenset(
    {
        "approvals",
        "audit_logs",
        "decision_snapshots",
        "document_allocation_links",
        "document_sections",
        "documents",
        "idempotency_keys",
        "inbound_receipts",
        "inspection_cases",
        "internal_results",
        "lot_merge_approvals",
        "material_lots",
        "material_models",
        "materials",
        "outbox_events",
        "receipt_lot_allocations",
        "sample_measurements",
        "spec_items",
        "spec_profiles",
        "spec_versions",
        "standard_test_items",
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
    finally:
        engine.dispose()
    command.downgrade(config, "base")
    if _table_names(database_url) != {"alembic_version"}:
        raise RuntimeError(
            f"P2 tables remain after downgrade to base: {_table_names(database_url)}"
        )
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
