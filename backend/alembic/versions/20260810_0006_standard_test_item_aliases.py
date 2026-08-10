"""Add scoped standard test item aliases.

Revision ID: 20260810_0006
Revises: 20260810_0005
"""

from __future__ import annotations

import os
import re
from typing import Any

import sqlalchemy as sa

from alembic import op

revision = "20260810_0006"
down_revision = "20260810_0005"
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
    op.create_table(
        "standard_test_item_aliases",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("standard_test_item_id", uuid, nullable=False),
        sa.Column("alias_text", sa.String(256), nullable=False),
        sa.Column("supplier_id", uuid),
        sa.Column("material_id", uuid),
        sa.Column("model_id", uuid),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["standard_test_item_id"],
            ["standard_test_items.id"],
            name="fk_standard_test_item_aliases_standard_item",
        ),
        sa.ForeignKeyConstraint(
            ["supplier_id"], ["suppliers.id"], name="fk_standard_test_item_aliases_supplier"
        ),
        sa.ForeignKeyConstraint(
            ["material_id"], ["materials.id"], name="fk_standard_test_item_aliases_material"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["material_models.id"],
            name="fk_standard_test_item_aliases_model",
        ),
        *_versioned(),
    )
    scope_indexes = (
        (
            "uq_standard_alias_scope_000",
            ["alias_text"],
            "supplier_id IS NULL AND material_id IS NULL AND model_id IS NULL",
        ),
        (
            "uq_standard_alias_scope_100",
            ["alias_text", "supplier_id"],
            "supplier_id IS NOT NULL AND material_id IS NULL AND model_id IS NULL",
        ),
        (
            "uq_standard_alias_scope_010",
            ["alias_text", "material_id"],
            "supplier_id IS NULL AND material_id IS NOT NULL AND model_id IS NULL",
        ),
        (
            "uq_standard_alias_scope_001",
            ["alias_text", "model_id"],
            "supplier_id IS NULL AND material_id IS NULL AND model_id IS NOT NULL",
        ),
        (
            "uq_standard_alias_scope_110",
            ["alias_text", "supplier_id", "material_id"],
            "supplier_id IS NOT NULL AND material_id IS NOT NULL AND model_id IS NULL",
        ),
        (
            "uq_standard_alias_scope_101",
            ["alias_text", "supplier_id", "model_id"],
            "supplier_id IS NOT NULL AND material_id IS NULL AND model_id IS NOT NULL",
        ),
        (
            "uq_standard_alias_scope_011",
            ["alias_text", "material_id", "model_id"],
            "supplier_id IS NULL AND material_id IS NOT NULL AND model_id IS NOT NULL",
        ),
        (
            "uq_standard_alias_scope_111",
            ["alias_text", "supplier_id", "material_id", "model_id"],
            "supplier_id IS NOT NULL AND material_id IS NOT NULL AND model_id IS NOT NULL",
        ),
    )
    for name, columns, predicate in scope_indexes:
        op.create_index(
            name,
            "standard_test_item_aliases",
            columns,
            unique=True,
            postgresql_where=sa.text(predicate),
            sqlite_where=sa.text(predicate),
        )
    op.create_index(
        "ix_standard_test_item_alias_lookup_order",
        "standard_test_item_aliases",
        ["priority", "alias_text"],
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
                GRANT SELECT, INSERT, UPDATE, DELETE ON standard_test_item_aliases TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_index(
        "ix_standard_test_item_alias_lookup_order",
        table_name="standard_test_item_aliases",
    )
    for name in (
        "uq_standard_alias_scope_111",
        "uq_standard_alias_scope_011",
        "uq_standard_alias_scope_101",
        "uq_standard_alias_scope_110",
        "uq_standard_alias_scope_001",
        "uq_standard_alias_scope_010",
        "uq_standard_alias_scope_100",
        "uq_standard_alias_scope_000",
    ):
        op.drop_index(name, table_name="standard_test_item_aliases")
    op.drop_table("standard_test_item_aliases")
