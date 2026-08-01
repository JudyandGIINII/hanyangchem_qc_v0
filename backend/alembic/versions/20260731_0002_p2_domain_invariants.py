"""Frozen P2 domain schema and database invariants.

This historical revision deliberately declares every object itself.  It must never
consult ORM metadata, because later model changes must not rewrite P2 history.
"""

from __future__ import annotations

import os
import re
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "20260731_0002"
down_revision = "20260731_0001"
branch_labels = None
depends_on = None

_APP_ROLE_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _versioned_columns() -> list[sa.Column[Any]]:
    return [
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _lower_hex_check(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression},'{character}','')"
    return f"{column} = lower({column}) AND length({expression}) = 0"


def _postgres_guards() -> None:
    op.execute(
        """
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE FUNCTION hyc_prevent_active_spec_overlap() RETURNS trigger AS $$
        DECLARE scope_key text;
        BEGIN
          IF NEW.status <> 'ACTIVE' THEN RETURN NEW; END IF;
          SELECT concat_ws('|', material_id::text, coalesce(supplier_id::text, ''), coalesce(model_id::text, ''))
          INTO scope_key FROM spec_profiles WHERE id = NEW.spec_profile_id;
          PERFORM pg_advisory_xact_lock(hashtextextended(scope_key, 0));
          IF EXISTS (
            SELECT 1 FROM spec_versions other
            JOIN spec_profiles p ON p.id = other.spec_profile_id
            JOIN spec_profiles current_scope ON current_scope.id = NEW.spec_profile_id
            WHERE other.id <> NEW.id AND other.status = 'ACTIVE'
              AND p.material_id = current_scope.material_id
              AND p.supplier_id IS NOT DISTINCT FROM current_scope.supplier_id
              AND p.model_id IS NOT DISTINCT FROM current_scope.model_id
              AND other.effective_from <= coalesce(NEW.effective_to, 'infinity'::date)
              AND NEW.effective_from <= coalesce(other.effective_to, 'infinity'::date)
          ) THEN RAISE EXCEPTION 'active spec effective range overlaps its scope'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_active_spec_overlap BEFORE INSERT OR UPDATE OF status, effective_from, effective_to, spec_profile_id
          ON spec_versions FOR EACH ROW EXECUTE FUNCTION hyc_prevent_active_spec_overlap();

        CREATE FUNCTION hyc_prevent_bound_spec_scope_mutation() RETURNS trigger AS $$
        BEGIN
          IF (
            OLD.material_id IS DISTINCT FROM NEW.material_id
            OR OLD.supplier_id IS DISTINCT FROM NEW.supplier_id
            OR OLD.model_id IS DISTINCT FROM NEW.model_id
          ) AND EXISTS (
            SELECT 1 FROM spec_versions WHERE spec_profile_id = OLD.id
          ) THEN
            RAISE EXCEPTION 'bound specification scope is immutable';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_bound_spec_scope_immutable
          BEFORE UPDATE OF material_id, supplier_id, model_id ON spec_profiles
          FOR EACH ROW EXECUTE FUNCTION hyc_prevent_bound_spec_scope_mutation();

        CREATE FUNCTION hyc_deny_immutable_mutation() RETURNS trigger AS $$
        BEGIN RAISE EXCEPTION 'immutable P2 record cannot be modified or deleted'; END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_documents_immutable BEFORE UPDATE OR DELETE ON documents
          FOR EACH ROW WHEN (OLD.immutable) EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_snapshot_immutable BEFORE UPDATE OR DELETE ON decision_snapshots
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_audit_append_only BEFORE UPDATE OR DELETE ON audit_logs
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_approval_append_only BEFORE UPDATE OR DELETE ON approvals
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_lot_merge_approval_append_only
          BEFORE UPDATE OR DELETE ON lot_merge_approvals
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_outbox_append_only BEFORE UPDATE OR DELETE ON outbox_events
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();
        CREATE TRIGGER trg_material_lot_no_delete
          BEFORE DELETE ON material_lots
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_immutable_mutation();

        CREATE FUNCTION hyc_require_lock_version_increment() RETURNS trigger AS $$
        BEGIN
          IF NEW.lock_version <> OLD.lock_version + 1 THEN
            RAISE EXCEPTION 'stale or invalid optimistic lock version';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_inspection_case_optimistic_lock
          BEFORE UPDATE ON inspection_cases
          FOR EACH ROW EXECUTE FUNCTION hyc_require_lock_version_increment();
        CREATE TRIGGER trg_material_lot_optimistic_lock
          BEFORE UPDATE ON material_lots
          FOR EACH ROW EXECUTE FUNCTION hyc_require_lock_version_increment();
        CREATE TRIGGER trg_spec_version_optimistic_lock
          BEFORE UPDATE ON spec_versions
          FOR EACH ROW EXECUTE FUNCTION hyc_require_lock_version_increment();

        CREATE FUNCTION hyc_require_live_allocation_lot() RETURNS trigger AS $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM material_lots
            WHERE id = NEW.material_lot_id
              AND identity_status <> 'MERGED'
              AND merged_into_id IS NULL
              AND deleted_at IS NULL
          ) THEN
            RAISE EXCEPTION 'receipt allocation requires a live non-merged LOT';
          END IF;
          IF NEW.model_id IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM material_models model
            JOIN material_lots lot ON lot.id = NEW.material_lot_id
            WHERE model.id = NEW.model_id
              AND model.material_id = lot.material_id
              AND model.deleted_at IS NULL
          ) THEN
            RAISE EXCEPTION 'receipt allocation model must belong to its LOT material';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_allocation_live_lot
          BEFORE INSERT OR UPDATE OF material_lot_id, model_id ON receipt_lot_allocations
          FOR EACH ROW EXECUTE FUNCTION hyc_require_live_allocation_lot();

        CREATE FUNCTION hyc_require_correction_revision_increment() RETURNS trigger AS $$
        DECLARE parent_revision integer;
        BEGIN
          IF NEW.correction_of_case_id IS NULL THEN RETURN NEW; END IF;
          SELECT revision_no INTO parent_revision
          FROM inspection_cases WHERE id = NEW.correction_of_case_id;
          IF parent_revision IS NULL OR NEW.revision_no <> parent_revision + 1 THEN
            RAISE EXCEPTION 'correction revision must increment its parent exactly once';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_correction_revision_increment
          BEFORE INSERT OR UPDATE OF correction_of_case_id, revision_no ON inspection_cases
          FOR EACH ROW EXECUTE FUNCTION hyc_require_correction_revision_increment();

        CREATE FUNCTION hyc_deny_finalized_case_mutation() RETURNS trigger AS $$
        BEGIN
          IF OLD.final_decision IS NOT NULL THEN
            RAISE EXCEPTION 'finalized case is immutable; create a correction revision';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_finalized_case_immutable
          BEFORE UPDATE OR DELETE ON inspection_cases
          FOR EACH ROW EXECUTE FUNCTION hyc_deny_finalized_case_mutation();

        CREATE FUNCTION hyc_merged_lot_requires_dual_approval() RETURNS trigger AS $$
        BEGIN
          IF NEW.identity_status = 'MERGED' AND OLD.identity_status <> 'MERGED' AND (
            (SELECT count(*) FROM lot_merge_approvals
              WHERE material_lot_id = NEW.id
                AND role IN ('LEAD','ADMIN')) <> 2
            OR (SELECT count(DISTINCT actor_id) FROM lot_merge_approvals
              WHERE material_lot_id = NEW.id
                AND role IN ('LEAD','ADMIN')) <> 2
            OR NOT EXISTS (
              SELECT 1 FROM audit_logs
              WHERE entity_type = 'material_lot'
                AND entity_id = NEW.id
                AND action = 'LOT_MERGED'
                AND reason IS NOT NULL
                AND btrim(reason) <> ''
            )
          ) THEN
            RAISE EXCEPTION 'LOT merge requires distinct dual approvals and append-only audit';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER trg_merged_lot_requires_dual_approval
          AFTER UPDATE OF identity_status ON material_lots
          DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
          EXECUTE FUNCTION hyc_merged_lot_requires_dual_approval();

        CREATE FUNCTION hyc_canonical_json(payload jsonb) RETURNS text AS $$
        DECLARE rendered text;
        BEGIN
          CASE jsonb_typeof(payload)
            WHEN 'object' THEN
              SELECT '{' || coalesce(
                string_agg(to_jsonb(key)::text || ':' || hyc_canonical_json(value), ',' ORDER BY key),
                ''
              ) || '}' INTO rendered FROM jsonb_each(payload);
            WHEN 'array' THEN
              SELECT '[' || coalesce(
                string_agg(hyc_canonical_json(value), ',' ORDER BY ordinality),
                ''
              ) || ']' INTO rendered
              FROM jsonb_array_elements(payload) WITH ORDINALITY AS items(value, ordinality);
            ELSE RETURN payload::text;
          END CASE;
          RETURN rendered;
        END; $$ LANGUAGE plpgsql IMMUTABLE STRICT;

        CREATE FUNCTION hyc_jsonb_required_nonempty(payload jsonb, key_name text)
        RETURNS boolean AS $$
        DECLARE value jsonb;
        BEGIN
          value := payload -> key_name;
          IF value IS NULL OR jsonb_typeof(value) = 'null' THEN RETURN false; END IF;
          IF jsonb_typeof(value) = 'string' THEN
            RETURN btrim(payload ->> key_name) <> '';
          END IF;
          IF jsonb_typeof(value) = 'array' THEN RETURN jsonb_array_length(value) > 0; END IF;
          IF jsonb_typeof(value) = 'object' THEN RETURN value <> '{}'::jsonb; END IF;
          RETURN true;
        END; $$ LANGUAGE plpgsql IMMUTABLE STRICT;

        CREATE FUNCTION hyc_validate_decision_snapshot() RETURNS trigger AS $$
        DECLARE required_key text;
        DECLARE recomputed text;
        BEGIN
          FOREACH required_key IN ARRAY ARRAY[
            'spec_version','spec_items','mapping','supplier_results','internal_results',
            'unit_conversions','item_decisions','source_policy','missing_policy',
            'overall_decision','document_hashes','engine_version','policy_version',
            'rounding_version','conversion_version','approver','sample_policy',
            'lot_reference','allocation_reference','decision_reasons'
          ] LOOP
            IF NOT hyc_jsonb_required_nonempty(NEW.payload::jsonb, required_key) THEN
              RAISE EXCEPTION 'decision snapshot required value is null or empty: %', required_key;
            END IF;
          END LOOP;
          IF NEW.payload::jsonb ->> 'overall_decision'
             NOT IN ('ACCEPTED','REJECTED','ON_HOLD') THEN
            RAISE EXCEPTION 'snapshot overall decision is invalid';
          END IF;
          recomputed := encode(
            digest(convert_to(hyc_canonical_json(NEW.payload::jsonb), 'UTF8'), 'sha256'),
            'hex'
          );
          IF NEW.content_hash <> recomputed THEN
            RAISE EXCEPTION 'snapshot canonical hash mismatch';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_snapshot_validate
          BEFORE INSERT ON decision_snapshots
          FOR EACH ROW EXECUTE FUNCTION hyc_validate_decision_snapshot();

        CREATE FUNCTION hyc_final_requires_snapshot_approval() RETURNS trigger AS $$
        BEGIN
          IF NEW.final_decision IS NOT NULL AND (
            OLD.final_decision IS NOT NULL
            OR OLD.status <> 'LEAD_REVIEW'
            OR NEW.status <> NEW.final_decision
            OR NEW.candidate_decision IS NULL
            OR NEW.submitted_by_id IS NULL
            OR NOT EXISTS (
              SELECT 1 FROM decision_snapshots
              WHERE inspection_case_id = NEW.id
                AND payload::jsonb ->> 'overall_decision' = NEW.candidate_decision
                AND content_hash = encode(
                  digest(convert_to(hyc_canonical_json(payload::jsonb), 'UTF8'), 'sha256'),
                  'hex'
                )
            )
            OR NOT EXISTS (
              SELECT 1 FROM approvals
              WHERE inspection_case_id = NEW.id
                AND action = 'APPROVE'
                AND actor_role = 'LEAD'
                AND actor_id <> NEW.submitted_by_id
            )
            OR (
              NEW.candidate_decision IN ('REJECTED','ON_HOLD')
              AND NEW.final_decision = 'ACCEPTED'
            )
            OR (
              NEW.final_decision <> NEW.candidate_decision
              AND NOT EXISTS (
                SELECT 1 FROM audit_logs
                WHERE entity_type = 'inspection_case'
                  AND entity_id = NEW.id
                  AND action = 'FINALIZE'
                  AND reason IS NOT NULL
                  AND btrim(reason) <> ''
              )
            )
            OR NOT EXISTS (
              SELECT 1
              FROM spec_versions sv
              JOIN spec_profiles sp ON sp.id = sv.spec_profile_id
              JOIN receipt_lot_allocations allocation
                ON allocation.id = NEW.receipt_lot_allocation_id
              JOIN inbound_receipts receipt ON receipt.id = allocation.inbound_receipt_id
              JOIN material_lots lot ON lot.id = allocation.material_lot_id
              WHERE sv.id = NEW.spec_version_id
                AND sv.status = 'ACTIVE'
                AND sv.effective_from <= receipt.receipt_date
                AND (sv.effective_to IS NULL OR sv.effective_to >= receipt.receipt_date)
                AND sp.material_id = lot.material_id
                AND (sp.supplier_id IS NULL OR sp.supplier_id = lot.supplier_id)
                AND (sp.model_id IS NULL OR sp.model_id = allocation.model_id)
                AND lot.identity_status = 'CANONICAL'
                AND lot.merged_into_id IS NULL
                AND NOT EXISTS (
                  SELECT 1
                  FROM spec_versions preferred
                  JOIN spec_profiles preferred_scope
                    ON preferred_scope.id = preferred.spec_profile_id
                  WHERE preferred.id <> sv.id
                    AND preferred.status = 'ACTIVE'
                    AND preferred.effective_from <= receipt.receipt_date
                    AND (
                      preferred.effective_to IS NULL
                      OR preferred.effective_to >= receipt.receipt_date
                    )
                    AND preferred_scope.material_id = lot.material_id
                    AND (
                      preferred_scope.supplier_id IS NULL
                      OR preferred_scope.supplier_id = lot.supplier_id
                    )
                    AND (
                      preferred_scope.model_id IS NULL
                      OR preferred_scope.model_id = allocation.model_id
                    )
                    AND (
                      (CASE WHEN preferred_scope.supplier_id IS NULL THEN 0 ELSE 1 END)
                      + (CASE WHEN preferred_scope.model_id IS NULL THEN 0 ELSE 1 END)
                      > (CASE WHEN sp.supplier_id IS NULL THEN 0 ELSE 1 END)
                      + (CASE WHEN sp.model_id IS NULL THEN 0 ELSE 1 END)
                      OR (
                        (CASE WHEN preferred_scope.supplier_id IS NULL THEN 0 ELSE 1 END)
                        + (CASE WHEN preferred_scope.model_id IS NULL THEN 0 ELSE 1 END)
                        = (CASE WHEN sp.supplier_id IS NULL THEN 0 ELSE 1 END)
                        + (CASE WHEN sp.model_id IS NULL THEN 0 ELSE 1 END)
                      )
                    )
                )
            )
            OR NOT EXISTS (
              SELECT 1 FROM audit_logs
              WHERE entity_type = 'inspection_case'
                AND entity_id = NEW.id
                AND action = 'FINALIZE'
            )
            OR NOT EXISTS (
              SELECT 1 FROM outbox_events
              WHERE topic = 'inspection.finalized'
                AND payload::jsonb ->> 'inspection_case_id' = NEW.id::text
            )
          ) THEN RAISE EXCEPTION 'final decision requires approval and immutable snapshot'; END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER trg_final_requires_snapshot_approval
          AFTER INSERT OR UPDATE OF final_decision ON inspection_cases DEFERRABLE INITIALLY DEFERRED
          FOR EACH ROW EXECUTE FUNCTION hyc_final_requires_snapshot_approval();
        """
    )
    versioned_tables = (
        "suppliers",
        "materials",
        "material_models",
        "spec_profiles",
        "standard_test_items",
        "spec_items",
        "inbound_receipts",
        "receipt_lot_allocations",
        "document_sections",
        "document_allocation_links",
        "supplier_results",
        "internal_results",
        "sample_measurements",
    )
    for table in versioned_tables:
        op.execute(
            f"CREATE TRIGGER trg_{table}_optimistic_lock BEFORE UPDATE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION hyc_require_lock_version_increment()"
        )
    app_role = os.environ.get("HYC_APP_ROLE", "hyc_app")
    if not _APP_ROLE_PATTERN.fullmatch(app_role):
        raise ValueError("HYC_APP_ROLE must be a conventional SQL identifier")
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
            EXECUTE 'GRANT USAGE ON SCHEMA public TO {app_role}';
            EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {app_role}';
            EXECUTE 'GRANT SELECT ON ALL TABLES IN SCHEMA public TO {app_role}';
            EXECUTE 'GRANT INSERT, UPDATE, DELETE ON suppliers, materials, material_models, spec_profiles, spec_versions, standard_test_items, spec_items, material_lots, inbound_receipts, receipt_lot_allocations, document_sections, document_allocation_links, inspection_cases, supplier_results, internal_results, sample_measurements, idempotency_keys TO {app_role}';
            EXECUTE 'GRANT INSERT ON decision_snapshots, audit_logs, documents, approvals, lot_merge_approvals, outbox_events TO {app_role}';
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "suppliers",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("supplier_code", sa.String(64), unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_versioned_columns(),
    )
    op.create_table(
        "materials",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("material_code", sa.String(64), unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("default_unit", sa.String(32)),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_versioned_columns(),
    )
    op.create_table(
        "material_models",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("material_id", uuid, nullable=False),
        sa.Column("model_code", sa.String(64), unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name="fk_material_models_material"
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "spec_profiles",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("material_id", uuid, nullable=False),
        sa.Column("supplier_id", uuid),
        sa.Column("model_id", uuid),
        sa.Column("name", sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name="fk_spec_profiles_material"
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name="fk_spec_profiles_supplier"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["material_models.id"], name="fk_spec_profiles_model"
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "spec_versions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("spec_profile_id", uuid, nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date()),
        sa.Column("revision_reason", sa.Text()),
        sa.ForeignKeyConstraint(
            ["spec_profile_id"], ["spec_profiles.id"], name="fk_spec_versions_profile"
        ),
        sa.UniqueConstraint("spec_profile_id", "version", name="uq_spec_versions_profile_version"),
        sa.CheckConstraint("version > 0", name="ck_spec_versions_semantic_version"),
        sa.CheckConstraint(
            "status IN ('DRAFT','ACTIVE','RETIRED')",
            name="ck_spec_versions_status",
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_spec_versions_effective_dates",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "standard_test_items",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("data_type", sa.String(32), nullable=False),
        sa.Column("default_unit", sa.String(32)),
        sa.CheckConstraint(
            "data_type IN ('NUMERIC','TEXT','PASS_FAIL')",
            name="ck_standard_test_item_data_type",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "spec_items",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("spec_version_id", uuid, nullable=False),
        sa.Column("standard_test_item_id", uuid, nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_policy", sa.String(48), nullable=False),
        sa.Column("missing_policy", sa.String(32), nullable=False, server_default="HOLD"),
        sa.Column("operator", sa.String(32), nullable=False),
        sa.Column("lower_value", sa.Numeric(24, 12)),
        sa.Column("upper_value", sa.Numeric(24, 12)),
        sa.Column("target_value", sa.Numeric(24, 12)),
        sa.Column("tolerance", sa.Numeric(24, 12)),
        sa.Column("allowed_values", sa.JSON()),
        sa.Column("unit", sa.String(32)),
        sa.Column("precision", sa.Integer(), nullable=False, server_default="4"),
        sa.Column("sample_policy", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.ForeignKeyConstraint(
            ["spec_version_id"], ["spec_versions.id"], name="fk_spec_items_version"
        ),
        sa.ForeignKeyConstraint(
            ["standard_test_item_id"],
            ["standard_test_items.id"],
            name="fk_spec_items_standard_item",
        ),
        sa.CheckConstraint(
            "operator IN ('GTE','GT','LTE','LT','BETWEEN_INCLUSIVE','BETWEEN_EXCLUSIVE','TARGET_PLUS_MINUS','EQUAL','IN_SET','CONTAINS','MANUAL_PASS_FAIL')",
            name="ck_spec_item_operator_allowlist",
        ),
        sa.CheckConstraint(
            "(operator IN ('GTE','GT','EQUAL') AND lower_value IS NOT NULL AND upper_value IS NULL AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL) OR (operator IN ('LTE','LT') AND lower_value IS NULL AND upper_value IS NOT NULL AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL) OR (operator IN ('BETWEEN_INCLUSIVE','BETWEEN_EXCLUSIVE') AND lower_value IS NOT NULL AND upper_value IS NOT NULL AND lower_value <= upper_value AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL) OR (operator = 'TARGET_PLUS_MINUS' AND lower_value IS NULL AND upper_value IS NULL AND target_value IS NOT NULL AND tolerance IS NOT NULL AND tolerance >= 0 AND allowed_values IS NULL) OR (operator IN ('IN_SET','CONTAINS') AND lower_value IS NULL AND upper_value IS NULL AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NOT NULL) OR (operator = 'MANUAL_PASS_FAIL' AND lower_value IS NULL AND upper_value IS NULL AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL)",
            name="ck_spec_item_operator_columns",
        ),
        sa.CheckConstraint(
            "source_policy IN ('SUPPLIER_ONLY','INTERNAL_ONLY','BOTH_INTERNAL_PRIORITY',"
            "'BOTH_ALL_MUST_PASS','SUPPLIER_REFERENCE_INTERNAL_FINAL')",
            name="ck_spec_item_source_policy",
        ),
        sa.CheckConstraint(
            "missing_policy IN ('REQUEST_SUPPLEMENT','INTERNAL_SUBSTITUTE',"
            "'SPECIAL_ACCEPTANCE','HOLD','REJECT')",
            name="ck_spec_item_missing_policy",
        ),
        sa.CheckConstraint(
            "sample_policy IN ('ALL_SAMPLES_IN_SPEC','AVERAGE_IN_SPEC',"
            "'WORST_CASE_IN_SPEC','MIN_IN_SPEC','MAX_IN_SPEC','MANUAL')",
            name="ck_spec_item_sample_policy",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "material_lots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("supplier_id", uuid, nullable=False),
        sa.Column("material_id", uuid, nullable=False),
        sa.Column("identity_policy_version", sa.String(32), nullable=False),
        sa.Column("identity_key", sa.String(512)),
        sa.Column("supplier_lot_no_raw", sa.String(512)),
        sa.Column("production_date_evidence", sa.String(64)),
        sa.Column("package_mark_evidence", sa.String(256)),
        sa.Column("identity_status", sa.String(32), nullable=False),
        sa.Column("merged_into_id", uuid),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name="fk_material_lots_supplier"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name="fk_material_lots_material"
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"], ["material_lots.id"], name="fk_material_lots_merged_into"
        ),
        sa.UniqueConstraint(
            "supplier_id",
            "material_id",
            "identity_policy_version",
            "identity_key",
            name="uq_material_lot_canonical_key",
        ),
        sa.CheckConstraint(
            "(identity_status IN ('PROVISIONAL','CONFLICT_REVIEW') AND merged_into_id IS NULL) OR (identity_status = 'CANONICAL' AND identity_key IS NOT NULL AND merged_into_id IS NULL) OR (identity_status = 'MERGED' AND merged_into_id IS NOT NULL)",
            name="ck_material_lot_identity_status",
        ),
        sa.CheckConstraint(
            "merged_into_id IS NULL OR merged_into_id <> id", name="ck_material_lot_no_self_merge"
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "inbound_receipts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inbound_no", sa.String(64), nullable=False, unique=True),
        sa.Column("supplier_id", uuid, nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name="fk_inbound_receipts_supplier"
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','RECEIVED','CLOSED','CANCELLED')",
            name="ck_inbound_receipt_status",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "receipt_lot_allocations",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inbound_receipt_id", uuid, nullable=False),
        sa.Column("material_lot_id", uuid, nullable=False),
        sa.Column("model_id", uuid),
        sa.Column("quantity", sa.Numeric(24, 12), nullable=False),
        sa.Column("quantity_unit", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["inbound_receipt_id"], ["inbound_receipts.id"], name="fk_allocations_receipt"
        ),
        sa.ForeignKeyConstraint(
            ["material_lot_id"], ["material_lots.id"], name="fk_allocations_lot"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["material_models.id"], name="fk_allocations_model"
        ),
        sa.UniqueConstraint(
            "inbound_receipt_id", "material_lot_id", name="uq_receipt_lot_allocation"
        ),
        sa.CheckConstraint(
            "quantity > 0",
            name="ck_receipt_lot_allocation_quantity_positive",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "documents",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("document_type", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(512), nullable=False),
        sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_documents_sha256_length",
        ),
        sa.CheckConstraint(
            _lower_hex_check("checksum_sha256"),
            name="ck_documents_sha256_lowercase",
        ),
        sa.CheckConstraint("immutable", name="ck_documents_always_immutable"),
    )
    op.create_table(
        "document_sections",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_id", uuid, nullable=False),
        sa.Column("section_index", sa.Integer(), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=False),
        sa.Column("page_to", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="UNMATCHED"),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_document_sections_document"
        ),
        sa.UniqueConstraint("document_id", "section_index", name="uq_document_section_index"),
        sa.CheckConstraint(
            "page_from >= 1 AND page_to >= page_from",
            name="ck_document_section_page_range",
        ),
        sa.CheckConstraint(
            "status IN ('UNMATCHED','MATCHED','REVIEW_REQUIRED')",
            name="ck_document_section_status",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "document_allocation_links",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("document_section_id", uuid, nullable=False),
        sa.Column("receipt_lot_allocation_id", uuid, nullable=False),
        sa.Column("match_status", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_section_id"], ["document_sections.id"], name="fk_document_links_section"
        ),
        sa.ForeignKeyConstraint(
            ["receipt_lot_allocation_id"],
            ["receipt_lot_allocations.id"],
            name="fk_document_links_allocation",
        ),
        sa.UniqueConstraint(
            "document_section_id", "receipt_lot_allocation_id", name="uq_document_allocation_link"
        ),
        sa.CheckConstraint(
            "match_status IN ('PENDING','CONFIRMED','REJECTED')",
            name="ck_document_allocation_match_status",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "inspection_cases",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("receipt_lot_allocation_id", uuid, nullable=False),
        sa.Column("spec_version_id", uuid, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("candidate_decision", sa.String(16)),
        sa.Column("final_decision", sa.String(16)),
        sa.Column("submitted_by_id", uuid),
        sa.Column("correction_of_case_id", uuid),
        sa.Column("revision_no", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["receipt_lot_allocation_id"],
            ["receipt_lot_allocations.id"],
            name="fk_inspection_cases_allocation",
        ),
        sa.ForeignKeyConstraint(
            ["spec_version_id"], ["spec_versions.id"], name="fk_inspection_cases_spec_version"
        ),
        sa.ForeignKeyConstraint(
            ["correction_of_case_id"],
            ["inspection_cases.id"],
            name="fk_inspection_cases_correction_of",
        ),
        sa.UniqueConstraint(
            "correction_of_case_id",
            "revision_no",
            name="uq_inspection_correction_revision",
        ),
        sa.CheckConstraint(
            "candidate_decision IS NULL OR candidate_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_inspection_candidate_decision",
        ),
        sa.CheckConstraint(
            "final_decision IS NULL OR final_decision IN ('ACCEPTED','REJECTED','ON_HOLD','RETEST','SPECIAL_ACCEPTED')",
            name="ck_inspection_final_decision",
        ),
        sa.CheckConstraint(
            "(correction_of_case_id IS NULL AND revision_no = 1) OR "
            "(correction_of_case_id IS NOT NULL AND revision_no > 1)",
            name="ck_inspection_correction_revision",
        ),
        sa.CheckConstraint(
            "status IN ('DRAFT','DOCUMENT_PENDING','MATCH_REVIEW','SUPPLIER_REVIEW',"
            "'INTERNAL_TEST_PENDING','READY_FOR_REVIEW','LEAD_REVIEW','RETURNED',"
            "'ACCEPTED','REJECTED','RETEST','SPECIAL_ACCEPTED','ON_HOLD','CLOSED',"
            "'CANCELLED')",
            name="ck_inspection_status",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "supplier_results",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("standard_test_item_id", uuid),
        sa.Column("supplier_item_name", sa.String(256), nullable=False),
        sa.Column("normalized_value", sa.Numeric(24, 12)),
        sa.Column("normalized_text", sa.Text()),
        sa.Column("mapping_status", sa.String(32), nullable=False),
        sa.Column("supplier_spec_text", sa.Text()),
        sa.Column("supplier_decision", sa.String(16)),
        sa.Column("hyc_decision", sa.String(16)),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"], ["inspection_cases.id"], name="fk_supplier_results_case"
        ),
        sa.ForeignKeyConstraint(
            ["standard_test_item_id"], ["standard_test_items.id"], name="fk_supplier_results_item"
        ),
        sa.CheckConstraint(
            "mapping_status IN ('UNMAPPED','ALIAS_MATCHED','MANUAL_CONFIRMED')",
            name="ck_supplier_result_mapping_status",
        ),
        sa.CheckConstraint(
            "(mapping_status = 'UNMAPPED' AND standard_test_item_id IS NULL) OR "
            "(mapping_status IN ('ALIAS_MATCHED','MANUAL_CONFIRMED') "
            "AND standard_test_item_id IS NOT NULL)",
            name="ck_supplier_result_mapping_target",
        ),
        sa.CheckConstraint(
            "supplier_decision IS NULL OR supplier_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_supplier_result_supplier_decision",
        ),
        sa.CheckConstraint(
            "hyc_decision IS NULL OR hyc_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_supplier_result_hyc_decision",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "internal_results",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("spec_item_id", uuid, nullable=False),
        sa.Column("evaluated_value", sa.Numeric(24, 12)),
        sa.Column("evaluated_text", sa.Text()),
        sa.Column("decision", sa.String(16)),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"], ["inspection_cases.id"], name="fk_internal_results_case"
        ),
        sa.ForeignKeyConstraint(
            ["spec_item_id"], ["spec_items.id"], name="fk_internal_results_spec_item"
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_internal_result_decision",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "sample_measurements",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("supplier_result_id", uuid),
        sa.Column("internal_result_id", uuid),
        sa.Column("sample_index", sa.Integer(), nullable=False),
        sa.Column("numeric_value", sa.Numeric(24, 12)),
        sa.Column("text_value", sa.Text()),
        sa.ForeignKeyConstraint(
            ["supplier_result_id"], ["supplier_results.id"], name="fk_samples_supplier_result"
        ),
        sa.ForeignKeyConstraint(
            ["internal_result_id"], ["internal_results.id"], name="fk_samples_internal_result"
        ),
        sa.CheckConstraint(
            "(supplier_result_id IS NOT NULL AND internal_result_id IS NULL) OR (supplier_result_id IS NULL AND internal_result_id IS NOT NULL)",
            name="ck_sample_exactly_one_result",
        ),
        *_versioned_columns(),
    )
    op.create_table(
        "decision_snapshots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"], ["inspection_cases.id"], name="fk_snapshots_case"
        ),
        sa.UniqueConstraint("inspection_case_id", name="uq_snapshots_case"),
        sa.CheckConstraint(
            "length(content_hash) = 64",
            name="ck_decision_snapshot_hash_length",
        ),
        sa.CheckConstraint(
            _lower_hex_check("content_hash"),
            name="ck_decision_snapshot_hash_lowercase",
        ),
    )
    op.create_table(
        "approvals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"], ["inspection_cases.id"], name="fk_approvals_case"
        ),
        sa.CheckConstraint(
            "actor_role = 'LEAD'",
            name="ck_approval_actor_role_lead",
        ),
        sa.CheckConstraint(
            "action = 'APPROVE'",
            name="ck_approval_action",
        ),
    )
    op.create_table(
        "lot_merge_approvals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("material_lot_id", uuid, nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["material_lot_id"],
            ["material_lots.id"],
            name="fk_lot_merge_approvals_lot",
        ),
        sa.UniqueConstraint(
            "material_lot_id",
            "role",
            name="uq_lot_merge_approvals_role",
        ),
        sa.CheckConstraint(
            "role IN ('LEAD','ADMIN')",
            name="ck_lot_merge_approvals_role",
        ),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", uuid, nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_table(
        "outbox_events",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "idempotency_keys",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("principal_id", sa.String(256), nullable=False),
        sa.Column("scope", sa.String(128), nullable=False),
        sa.Column("key", sa.String(256), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_owner", sa.String(256)),
        sa.Column("response_status", sa.Integer()),
        sa.Column("response_body", sa.Text()),
        sa.Column("resource_ref", sa.String(512)),
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
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "principal_id", "scope", "key", name="uq_idempotency_principal_scope_key"
        ),
        sa.CheckConstraint(
            "state IN ('PENDING','COMPLETED','FAILED_RETRYABLE')",
            name="ck_idempotency_state_allowlist",
        ),
    )
    op.create_index("ix_documents_checksum_sha256", "documents", ["checksum_sha256"])
    op.create_index("ix_decision_snapshots_content_hash", "decision_snapshots", ["content_hash"])
    if op.get_bind().dialect.name == "postgresql":
        _postgres_guards()


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for table in (
            "suppliers",
            "materials",
            "material_models",
            "spec_profiles",
            "standard_test_items",
            "spec_items",
            "inbound_receipts",
            "receipt_lot_allocations",
            "document_sections",
            "document_allocation_links",
            "supplier_results",
            "internal_results",
            "sample_measurements",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_optimistic_lock ON {table}")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_final_requires_snapshot_approval ON inspection_cases"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_approval_append_only ON approvals")
        op.execute("DROP TRIGGER IF EXISTS trg_outbox_append_only ON outbox_events")
        op.execute(
            "DROP TRIGGER IF EXISTS trg_lot_merge_approval_append_only ON lot_merge_approvals"
        )
        op.execute("DROP TRIGGER IF EXISTS trg_material_lot_no_delete ON material_lots")
        op.execute("DROP TRIGGER IF EXISTS trg_merged_lot_requires_dual_approval ON material_lots")
        op.execute("DROP TRIGGER IF EXISTS trg_finalized_case_immutable ON inspection_cases")
        op.execute("DROP TRIGGER IF EXISTS trg_inspection_case_optimistic_lock ON inspection_cases")
        op.execute("DROP TRIGGER IF EXISTS trg_material_lot_optimistic_lock ON material_lots")
        op.execute("DROP TRIGGER IF EXISTS trg_spec_version_optimistic_lock ON spec_versions")
        op.execute("DROP TRIGGER IF EXISTS trg_allocation_live_lot ON receipt_lot_allocations")
        op.execute("DROP TRIGGER IF EXISTS trg_correction_revision_increment ON inspection_cases")
        op.execute("DROP TRIGGER IF EXISTS trg_snapshot_validate ON decision_snapshots")
        op.execute("DROP TRIGGER IF EXISTS trg_audit_append_only ON audit_logs")
        op.execute("DROP TRIGGER IF EXISTS trg_snapshot_immutable ON decision_snapshots")
        op.execute("DROP TRIGGER IF EXISTS trg_documents_immutable ON documents")
        op.execute("DROP TRIGGER IF EXISTS trg_active_spec_overlap ON spec_versions")
        op.execute("DROP TRIGGER IF EXISTS trg_bound_spec_scope_immutable ON spec_profiles")
        op.execute("DROP FUNCTION IF EXISTS hyc_final_requires_snapshot_approval()")
        op.execute("DROP FUNCTION IF EXISTS hyc_validate_decision_snapshot()")
        op.execute("DROP FUNCTION IF EXISTS hyc_jsonb_required_nonempty(jsonb, text)")
        op.execute("DROP FUNCTION IF EXISTS hyc_canonical_json(jsonb)")
        op.execute("DROP FUNCTION IF EXISTS hyc_merged_lot_requires_dual_approval()")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_finalized_case_mutation()")
        op.execute("DROP FUNCTION IF EXISTS hyc_require_lock_version_increment()")
        op.execute("DROP FUNCTION IF EXISTS hyc_require_live_allocation_lot()")
        op.execute("DROP FUNCTION IF EXISTS hyc_require_correction_revision_increment()")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_immutable_mutation()")
        op.execute("DROP FUNCTION IF EXISTS hyc_prevent_active_spec_overlap()")
        op.execute("DROP FUNCTION IF EXISTS hyc_prevent_bound_spec_scope_mutation()")
    op.drop_index("ix_decision_snapshots_content_hash", table_name="decision_snapshots")
    op.drop_index("ix_documents_checksum_sha256", table_name="documents")
    op.drop_table("idempotency_keys")
    op.drop_table("outbox_events")
    op.drop_table("audit_logs")
    op.drop_table("lot_merge_approvals")
    op.drop_table("approvals")
    op.drop_table("decision_snapshots")
    op.drop_table("sample_measurements")
    op.drop_table("internal_results")
    op.drop_table("supplier_results")
    op.drop_table("inspection_cases")
    op.drop_table("document_allocation_links")
    op.drop_table("document_sections")
    op.drop_table("documents")
    op.drop_table("receipt_lot_allocations")
    op.drop_table("inbound_receipts")
    op.drop_table("material_lots")
    op.drop_table("spec_items")
    op.drop_table("standard_test_items")
    op.drop_table("spec_versions")
    op.drop_table("spec_profiles")
    op.drop_table("material_models")
    op.drop_table("materials")
    op.drop_table("suppliers")
