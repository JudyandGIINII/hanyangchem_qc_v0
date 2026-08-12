"""Add append-only master import batch and row history.

Revision ID: 20260813_0011
Revises: 20260813_0010
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260813_0011"
down_revision = "20260813_0010"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "master_import_batches",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("entity", sa.String(32), nullable=False),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("requested_by_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("reverted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "entity IN ('MATERIAL','SUPPLIER','MATERIAL_MODEL')",
            name="ck_master_import_entity",
        ),
        # PREVIEWED is the only state an APPLIED batch may come from: there is no
        # path that applies without a preview having been recorded first, which is
        # what keeps the import from bypassing the optimistic-lock and duplicate-code
        # rules the master tables already enforce.
        sa.CheckConstraint(
            "state IN ('PREVIEWED','APPLIED','REVERTED')",
            name="ck_master_import_state",
        ),
        sa.CheckConstraint(
            "(state <> 'REVERTED') OR (reverted_at IS NOT NULL)",
            name="ck_master_import_reverted_at_present",
        ),
        sa.CheckConstraint(
            "length(source_digest) = 64", name="ck_master_import_digest_length"
        ),
        sa.CheckConstraint(
            "source_digest = lower(source_digest)", name="ck_master_import_digest_lower"
        ),
    )
    op.create_table(
        "master_import_rows",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("batch_id", uuid, nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("code", sa.String(64)),
        sa.Column("name", sa.String(256)),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.Column("target_id", uuid),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["master_import_batches.id"], name="fk_master_import_rows_batch"
        ),
        sa.UniqueConstraint("batch_id", "row_number", name="uq_master_import_row_number"),
        sa.CheckConstraint(
            "action IN ('CREATE','UPDATE','UNCHANGED','REJECT')",
            name="ck_master_import_row_action",
        ),
        sa.CheckConstraint("row_number >= 1", name="ck_master_import_row_number_positive"),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    # Row history is append-only: a preview that could be edited after the fact
    # would make the applied batch unauditable.
    op.execute(
        """
        CREATE FUNCTION hyc_deny_master_import_row_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'master import rows are immutable once recorded';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_master_import_row_immutable
        BEFORE UPDATE OR DELETE ON master_import_rows
        FOR EACH ROW EXECUTE FUNCTION hyc_deny_master_import_row_mutation();
        """
    )
    role = os.environ.get("HYC_APP_ROLE", "hyc_app")
    if not _ROLE.fullmatch(role):
        raise RuntimeError("invalid HYC_APP_ROLE")
    op.execute(
        f"""
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
            GRANT SELECT, INSERT, UPDATE ON master_import_batches TO {role};
            GRANT SELECT, INSERT ON master_import_rows TO {role};
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_master_import_row_immutable ON master_import_rows;"
        )
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_master_import_row_mutation();")
    op.drop_table("master_import_rows")
    op.drop_table("master_import_batches")
