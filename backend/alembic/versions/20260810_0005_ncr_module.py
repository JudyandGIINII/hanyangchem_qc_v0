"""Add the approved P5 nonconformance module schema.

Revision ID: 20260810_0005
Revises: 20260801_0004
"""
# ruff: noqa: E501

from __future__ import annotations

import os
import re
from typing import Any
from uuid import UUID

import sqlalchemy as sa

from alembic import op

revision = "20260810_0005"
down_revision = "20260801_0004"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
_DISPOSITIONS = (
    (UUID("00000000-0000-0000-0000-000000000001"), "반품", "반품", 1),
    (UUID("00000000-0000-0000-0000-000000000002"), "재작업", "재작업", 2),
    (UUID("00000000-0000-0000-0000-000000000003"), "용도변경", "용도변경", 3),
    (UUID("00000000-0000-0000-0000-000000000004"), "폐기", "폐기", 4),
    (UUID("00000000-0000-0000-0000-000000000005"), "선별작업", "선별작업", 5),
    (UUID("00000000-0000-0000-0000-000000000006"), "특채", "특채", 6),
)


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
    op.create_table(
        "nonconformance_dispositions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.UniqueConstraint("code", name="uq_nonconformance_dispositions_code"),
        *_versioned(),
    )
    op.create_table(
        "nonconformances",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("ncr_number", sa.String(64), nullable=False),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("spec_item_id", uuid),
        sa.Column("severity", sa.String(16)),
        sa.Column("quantity", sa.Numeric(24, 12), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("cause", sa.Text()),
        sa.Column("disposition_id", uuid),
        sa.Column("disposition_snapshot", sa.JSON()),
        sa.Column("target_completion_date", sa.Date()),
        sa.Column("completion_date", sa.Date()),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("retest_case_id", uuid),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"],
            ["inspection_cases.id"],
            name="fk_nonconformances_inspection_case",
        ),
        sa.ForeignKeyConstraint(
            ["spec_item_id"], ["spec_items.id"], name="fk_nonconformances_spec_item"
        ),
        sa.ForeignKeyConstraint(
            ["disposition_id"],
            ["nonconformance_dispositions.id"],
            name="fk_nonconformances_disposition",
        ),
        sa.ForeignKeyConstraint(
            ["retest_case_id"],
            ["inspection_cases.id"],
            name="fk_nonconformances_retest_case",
        ),
        sa.UniqueConstraint("ncr_number", name="uq_nonconformances_ncr_number"),
        sa.CheckConstraint(
            "severity IS NULL OR severity IN ('MAJOR','MINOR')",
            name="ck_nonconformances_severity",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_nonconformances_quantity_positive"),
        sa.CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CLOSED')",
            name="ck_nonconformances_status",
        ),
        *_versioned(),
    )
    op.create_table(
        "nonconformance_approvals",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("nonconformance_id", uuid, nullable=False),
        sa.Column("actor_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["nonconformance_id"],
            ["nonconformances.id"],
            name="fk_nonconformance_approvals_nonconformance",
        ),
        sa.CheckConstraint(
            "actor_role = 'LEAD'", name="ck_nonconformance_approvals_actor_role_lead"
        ),
        sa.CheckConstraint(
            "action IN ('APPROVE','REJECT')", name="ck_nonconformance_approvals_action"
        ),
    )
    op.create_table(
        "nonconformance_attachments",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("nonconformance_id", uuid, nullable=False),
        sa.Column("document_id", uuid, nullable=False),
        sa.ForeignKeyConstraint(
            ["nonconformance_id"],
            ["nonconformances.id"],
            name="fk_nonconformance_attachments_nonconformance",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"], ["documents.id"], name="fk_nonconformance_attachments_document"
        ),
        sa.UniqueConstraint(
            "nonconformance_id",
            "document_id",
            name="uq_nonconformance_attachment_document",
        ),
    )
    for disposition_id, code, name, sort_order in _DISPOSITIONS:
        op.execute(
            sa.text(
                "INSERT INTO nonconformance_dispositions "
                "(id, code, name, active, sort_order, lock_version, created_at, updated_at) "
                "VALUES (:id, :code, :name, true, :sort_order, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ).bindparams(
                sa.bindparam("id", value=disposition_id, type_=sa.Uuid()),
                code=code,
                name=name,
                sort_order=sort_order,
            )
        )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION hyc_deny_nonconformance_disposition_delete() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'nonconformance dispositions cannot be deleted; deactivate instead';
            END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_nonconformance_disposition_no_delete
              BEFORE DELETE ON nonconformance_dispositions
              FOR EACH ROW EXECUTE FUNCTION hyc_deny_nonconformance_disposition_delete();

            CREATE FUNCTION hyc_deny_approved_nonconformance_mutation() RETURNS trigger AS $$
            BEGIN
              IF OLD.status = 'APPROVED' THEN
                RAISE EXCEPTION 'approved nonconformance is immutable';
              END IF;
              RETURN NEW;
            END; $$ LANGUAGE plpgsql;
            CREATE TRIGGER trg_approved_nonconformance_immutable
              BEFORE UPDATE OR DELETE ON nonconformances
              FOR EACH ROW EXECUTE FUNCTION hyc_deny_approved_nonconformance_mutation();
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
                GRANT SELECT, INSERT, UPDATE, DELETE
                  ON nonconformance_dispositions, nonconformances,
                    nonconformance_approvals, nonconformance_attachments TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_approved_nonconformance_immutable ON nonconformances"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_nonconformance_disposition_no_delete "
            "ON nonconformance_dispositions"
        )
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_approved_nonconformance_mutation()")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_nonconformance_disposition_delete()")
    op.drop_table("nonconformance_attachments")
    op.drop_table("nonconformance_approvals")
    op.drop_table("nonconformances")
    op.drop_table("nonconformance_dispositions")
