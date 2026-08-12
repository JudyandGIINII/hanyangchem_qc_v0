"""Add append-only nonconformance actions history table.

Revision ID: 20260812_0009
Revises: 20260811_0008
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260812_0009"
down_revision = "20260811_0008"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "nonconformance_actions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("nonconformance_id", uuid, nullable=False),
        sa.Column("action_type", sa.String(32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("performed_by_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["nonconformance_id"],
            ["nonconformances.id"],
            name="fk_nonconformance_actions_nonconformance",
        ),
        sa.CheckConstraint(
            "action_type IN ('CORRECTIVE','PREVENTIVE','VERIFICATION','COMPLETION')",
            name="ck_nonconformance_actions_type",
        ),
        sa.CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_nonconformance_actions_description_nonempty",
        ),
        sa.CheckConstraint(
            "action_type <> 'COMPLETION' OR actor_role = 'LEAD'",
            name="ck_nonconformance_actions_completion_lead",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        role = os.environ.get("HYC_APP_ROLE", "hyc_app")
        if not _ROLE.fullmatch(role):
            raise RuntimeError("invalid HYC_APP_ROLE")
        op.execute(
            f"""
            DO $$
            BEGIN
              IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                GRANT SELECT, INSERT ON nonconformance_actions TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("nonconformance_actions")
