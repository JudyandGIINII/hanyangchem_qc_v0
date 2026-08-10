"""Add append-only inspection return reason history.

Revision ID: 20260810_0007
Revises: 20260810_0006
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260810_0007"
down_revision = "20260810_0006"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "inspection_return_reasons",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("inspection_case_id", uuid, nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("target_spec_item_id", uuid),
        sa.Column("returned_by_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["inspection_case_id"],
            ["inspection_cases.id"],
            name="fk_inspection_return_reasons_inspection_case",
        ),
        sa.ForeignKeyConstraint(
            ["target_spec_item_id"],
            ["spec_items.id"],
            name="fk_inspection_return_reasons_target_spec_item",
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
                GRANT SELECT, INSERT ON inspection_return_reasons TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("inspection_return_reasons")
