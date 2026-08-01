"""Persist P3 extraction review and inspection lineage.

Revision ID: 20260801_0004
Revises: 20260801_0003
"""
# ruff: noqa: E501

from __future__ import annotations

import os
import re
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "20260801_0004"
down_revision = "20260801_0003"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def _versioned() -> tuple[sa.Column[Any], ...]:
    return (
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    uuid = sa.Uuid()
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("storage_key", sa.String(512)))
        batch.add_column(sa.Column("media_type", sa.String(128)))
        batch.add_column(sa.Column("size_bytes", sa.Integer()))
        batch.create_unique_constraint("uq_documents_storage_key", ["storage_key"])
    op.create_table(
        "extraction_runs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_id", uuid, nullable=False),
        sa.Column("provider_name", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="REVIEW_REQUIRED"),
        sa.Column("candidate_payload", sa.JSON(), nullable=False),
        sa.Column("conflicts", sa.JSON(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_extraction_runs_document"
        ),
        sa.CheckConstraint(
            "status IN ('REVIEW_REQUIRED','CONFIRMED')", name="ck_extraction_runs_status"
        ),
        *_versioned(),
    )
    op.create_table(
        "extraction_field_reviews",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("extraction_run_id", uuid, nullable=False),
        sa.Column("field_key", sa.String(64), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("ocr_text", sa.Text(), nullable=False),
        sa.Column("manual_text", sa.Text()),
        sa.Column("final_text", sa.Text()),
        sa.Column("source", sa.String(32)),
        sa.Column("reason", sa.Text()),
        sa.Column("confidence", sa.Numeric(24, 12), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("bbox", sa.JSON(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("logic_conflict", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False, server_default="REVIEW_REQUIRED"),
        sa.ForeignKeyConstraint(
            ["extraction_run_id"], ["extraction_runs.id"], name="fk_extraction_reviews_run"
        ),
        sa.UniqueConstraint("extraction_run_id", "field_key", name="uq_extraction_review_field"),
        sa.CheckConstraint(
            "status IN ('REVIEW_REQUIRED','CONFIRMED')", name="ck_extraction_field_reviews_status"
        ),
        sa.CheckConstraint("page_number >= 1", name="ck_extraction_review_page"),
        *_versioned(),
    )
    with op.batch_alter_table("inspection_cases") as batch:
        batch.add_column(sa.Column("retest_of_case_id", uuid))
        batch.add_column(sa.Column("lineage_root_id", uuid))
        batch.add_column(
            sa.Column("round_no", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("lineage_reason", sa.Text()))
        batch.add_column(
            sa.Column("spec_snapshot", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.create_foreign_key(
            "fk_inspection_retest_of",
            "inspection_cases",
            ["retest_of_case_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_inspection_lineage_root",
            "inspection_cases",
            ["lineage_root_id"],
            ["id"],
        )
        batch.create_check_constraint("ck_inspection_round_positive", "round_no > 0")
        batch.create_unique_constraint(
            "uq_inspection_lineage_round_revision",
            ["lineage_root_id", "round_no", "revision_no"],
        )
    with op.batch_alter_table("internal_results") as batch:
        batch.create_unique_constraint(
            "uq_internal_result_case_spec_item",
            ["inspection_case_id", "spec_item_id"],
        )
    with op.batch_alter_table("sample_measurements") as batch:
        batch.create_unique_constraint(
            "uq_sample_supplier_result_index",
            ["supplier_result_id", "sample_index"],
        )
        batch.create_unique_constraint(
            "uq_sample_internal_result_index",
            ["internal_result_id", "sample_index"],
        )
    op.create_index(
        "uq_document_section_one_confirmed_allocation",
        "document_allocation_links",
        ["document_section_id"],
        unique=True,
        postgresql_where=sa.text("match_status = 'CONFIRMED'"),
        sqlite_where=sa.text("match_status = 'CONFIRMED'"),
    )
    op.create_index(
        "uq_document_one_confirmed_extraction_run",
        "extraction_runs",
        ["document_id"],
        unique=True,
        postgresql_where=sa.text("status = 'CONFIRMED'"),
        sqlite_where=sa.text("status = 'CONFIRMED'"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute("""
        CREATE FUNCTION hyc_deny_finalized_evidence_mutation() RETURNS trigger AS $$
        DECLARE
          old_case_id uuid;
          new_case_id uuid;
          case_ids uuid[];
        BEGIN
          IF TG_TABLE_NAME = 'internal_results' THEN
            IF TG_OP <> 'INSERT' THEN old_case_id := OLD.inspection_case_id; END IF;
            IF TG_OP <> 'DELETE' THEN new_case_id := NEW.inspection_case_id; END IF;
          ELSIF TG_TABLE_NAME = 'supplier_results' THEN
            IF TG_OP <> 'INSERT' THEN old_case_id := OLD.inspection_case_id; END IF;
            IF TG_OP <> 'DELETE' THEN new_case_id := NEW.inspection_case_id; END IF;
          ELSE
            IF TG_OP <> 'INSERT' THEN
              old_case_id := COALESCE(
                (SELECT inspection_case_id FROM internal_results WHERE id = OLD.internal_result_id),
                (SELECT inspection_case_id FROM supplier_results WHERE id = OLD.supplier_result_id)
              );
            END IF;
            IF TG_OP <> 'DELETE' THEN
              new_case_id := COALESCE(
                (SELECT inspection_case_id FROM internal_results WHERE id = NEW.internal_result_id),
                (SELECT inspection_case_id FROM supplier_results WHERE id = NEW.supplier_result_id)
              );
            END IF;
          END IF;
          SELECT ARRAY_AGG(case_id ORDER BY case_id) INTO case_ids
          FROM (
            SELECT DISTINCT case_id
            FROM UNNEST(ARRAY[old_case_id, new_case_id]) AS valueset(case_id)
            WHERE case_id IS NOT NULL
          ) AS ordered_cases;
          PERFORM 1 FROM inspection_cases
            WHERE id = ANY(COALESCE(case_ids, ARRAY[]::uuid[]))
            ORDER BY id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM inspection_cases
            WHERE id = ANY(COALESCE(case_ids, ARRAY[]::uuid[]))
              AND final_decision IS NOT NULL
          ) THEN
            RAISE EXCEPTION 'finalized inspection evidence is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_internal_results_finalized_immutable BEFORE INSERT OR UPDATE OR DELETE ON internal_results FOR EACH ROW EXECUTE FUNCTION hyc_deny_finalized_evidence_mutation();
        CREATE TRIGGER trg_supplier_results_finalized_immutable BEFORE INSERT OR UPDATE OR DELETE ON supplier_results FOR EACH ROW EXECUTE FUNCTION hyc_deny_finalized_evidence_mutation();
        CREATE TRIGGER trg_sample_measurements_finalized_immutable BEFORE INSERT OR UPDATE OR DELETE ON sample_measurements FOR EACH ROW EXECUTE FUNCTION hyc_deny_finalized_evidence_mutation();

        CREATE FUNCTION hyc_guard_extraction_run_mutation() RETURNS trigger AS $$
        DECLARE
          old_document_id uuid;
          new_document_id uuid;
          document_ids uuid[];
          terminal_transition boolean := false;
        BEGIN
          IF TG_OP <> 'INSERT' THEN old_document_id := OLD.document_id; END IF;
          IF TG_OP <> 'DELETE' THEN new_document_id := NEW.document_id; END IF;
          IF TG_OP = 'INSERT' AND NEW.status = 'CONFIRMED' THEN
            RAISE EXCEPTION 'confirmed extraction lineage is immutable';
          END IF;
          IF TG_OP = 'UPDATE' THEN
            IF OLD.status = 'CONFIRMED' THEN
              RAISE EXCEPTION 'confirmed extraction lineage is immutable';
            END IF;
            terminal_transition := (
              OLD.status = 'REVIEW_REQUIRED'
              AND NEW.status = 'CONFIRMED'
              AND OLD.document_id = NEW.document_id
            );
          END IF;
          SELECT ARRAY_AGG(document_id ORDER BY document_id) INTO document_ids
          FROM (
            SELECT DISTINCT document_id
            FROM UNNEST(ARRAY[old_document_id, new_document_id]) AS valueset(document_id)
            WHERE document_id IS NOT NULL
          ) AS ordered_documents;
          PERFORM 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
            ORDER BY id FOR UPDATE;
          IF NOT terminal_transition AND EXISTS (
            SELECT 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
              AND status = 'CONFIRMED'
          ) THEN
            RAISE EXCEPTION 'confirmed extraction lineage is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE FUNCTION hyc_guard_extraction_review_mutation() RETURNS trigger AS $$
        DECLARE
          old_run_id uuid;
          new_run_id uuid;
          run_ids uuid[];
        BEGIN
          IF TG_OP <> 'INSERT' THEN old_run_id := OLD.extraction_run_id; END IF;
          IF TG_OP <> 'DELETE' THEN new_run_id := NEW.extraction_run_id; END IF;
          SELECT ARRAY_AGG(run_id ORDER BY run_id) INTO run_ids
          FROM (
            SELECT DISTINCT run_id
            FROM UNNEST(ARRAY[old_run_id, new_run_id]) AS valueset(run_id)
            WHERE run_id IS NOT NULL
          ) AS ordered_runs;
          PERFORM 1 FROM extraction_runs
            WHERE id = ANY(COALESCE(run_ids, ARRAY[]::uuid[]))
            ORDER BY id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM extraction_runs
            WHERE id = ANY(COALESCE(run_ids, ARRAY[]::uuid[]))
              AND status = 'CONFIRMED'
          ) THEN
            RAISE EXCEPTION 'confirmed extraction lineage is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE FUNCTION hyc_guard_document_section_mutation() RETURNS trigger AS $$
        DECLARE
          old_document_id uuid;
          new_document_id uuid;
          document_ids uuid[];
        BEGIN
          IF TG_OP <> 'INSERT' THEN old_document_id := OLD.document_id; END IF;
          IF TG_OP <> 'DELETE' THEN new_document_id := NEW.document_id; END IF;
          SELECT ARRAY_AGG(document_id ORDER BY document_id) INTO document_ids
          FROM (
            SELECT DISTINCT document_id
            FROM UNNEST(ARRAY[old_document_id, new_document_id]) AS valueset(document_id)
            WHERE document_id IS NOT NULL
          ) AS ordered_documents;
          PERFORM 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
            ORDER BY id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
              AND status = 'CONFIRMED'
          ) THEN
            RAISE EXCEPTION 'confirmed extraction lineage is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE FUNCTION hyc_guard_document_allocation_link_mutation() RETURNS trigger AS $$
        DECLARE
          old_document_id uuid;
          new_document_id uuid;
          document_ids uuid[];
        BEGIN
          IF TG_OP <> 'INSERT' THEN
            SELECT document_id INTO old_document_id
            FROM document_sections WHERE id = OLD.document_section_id;
          END IF;
          IF TG_OP <> 'DELETE' THEN
            SELECT document_id INTO new_document_id
            FROM document_sections WHERE id = NEW.document_section_id;
          END IF;
          SELECT ARRAY_AGG(document_id ORDER BY document_id) INTO document_ids
          FROM (
            SELECT DISTINCT document_id
            FROM UNNEST(ARRAY[old_document_id, new_document_id]) AS valueset(document_id)
            WHERE document_id IS NOT NULL
          ) AS ordered_documents;
          PERFORM 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
            ORDER BY id FOR UPDATE;
          IF EXISTS (
            SELECT 1 FROM extraction_runs
            WHERE document_id = ANY(COALESCE(document_ids, ARRAY[]::uuid[]))
              AND status = 'CONFIRMED'
          ) THEN
            RAISE EXCEPTION 'confirmed extraction lineage is immutable';
          END IF;
          IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_extraction_runs_confirmed_immutable BEFORE INSERT OR UPDATE OR DELETE ON extraction_runs FOR EACH ROW EXECUTE FUNCTION hyc_guard_extraction_run_mutation();
        CREATE TRIGGER trg_extraction_field_reviews_confirmed_immutable BEFORE INSERT OR UPDATE OR DELETE ON extraction_field_reviews FOR EACH ROW EXECUTE FUNCTION hyc_guard_extraction_review_mutation();
        CREATE TRIGGER trg_document_sections_confirmed_immutable BEFORE INSERT OR UPDATE OR DELETE ON document_sections FOR EACH ROW EXECUTE FUNCTION hyc_guard_document_section_mutation();
        CREATE TRIGGER trg_document_allocation_links_confirmed_immutable BEFORE INSERT OR UPDATE OR DELETE ON document_allocation_links FOR EACH ROW EXECUTE FUNCTION hyc_guard_document_allocation_link_mutation();
        """)
        role = os.environ.get("HYC_APP_ROLE", "hyc_app")
        if not _ROLE.fullmatch(role):
            raise RuntimeError("invalid HYC_APP_ROLE")
        op.execute(f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE
              ON extraction_runs, extraction_field_reviews TO {role};
          END IF;
        END $$;
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table, trigger in (
            ("document_allocation_links", "trg_document_allocation_links_confirmed_immutable"),
            ("document_sections", "trg_document_sections_confirmed_immutable"),
            ("extraction_field_reviews", "trg_extraction_field_reviews_confirmed_immutable"),
            ("extraction_runs", "trg_extraction_runs_confirmed_immutable"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
        for function in (
            "hyc_guard_document_allocation_link_mutation",
            "hyc_guard_document_section_mutation",
            "hyc_guard_extraction_review_mutation",
            "hyc_guard_extraction_run_mutation",
        ):
            op.execute(f"DROP FUNCTION IF EXISTS {function}()")
        for table in ("sample_measurements", "supplier_results", "internal_results"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_finalized_immutable ON {table}")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_finalized_evidence_mutation()")
    op.drop_index(
        "uq_document_one_confirmed_extraction_run",
        table_name="extraction_runs",
    )
    op.drop_index(
        "uq_document_section_one_confirmed_allocation",
        table_name="document_allocation_links",
    )
    with op.batch_alter_table("sample_measurements") as batch:
        batch.drop_constraint("uq_sample_internal_result_index", type_="unique")
        batch.drop_constraint("uq_sample_supplier_result_index", type_="unique")
    with op.batch_alter_table("internal_results") as batch:
        batch.drop_constraint("uq_internal_result_case_spec_item", type_="unique")
    with op.batch_alter_table("inspection_cases") as batch:
        batch.drop_constraint("uq_inspection_lineage_round_revision", type_="unique")
        batch.drop_constraint("ck_inspection_round_positive", type_="check")
        batch.drop_constraint("fk_inspection_lineage_root", type_="foreignkey")
        batch.drop_constraint("fk_inspection_retest_of", type_="foreignkey")
        for column in (
            "spec_snapshot",
            "lineage_reason",
            "round_no",
            "lineage_root_id",
            "retest_of_case_id",
        ):
            batch.drop_column(column)
    op.drop_table("extraction_field_reviews")
    op.drop_table("extraction_runs")
    with op.batch_alter_table("documents") as batch:
        batch.drop_constraint("uq_documents_storage_key", type_="unique")
        for column in ("size_bytes", "media_type", "storage_key"):
            batch.drop_column(column)
