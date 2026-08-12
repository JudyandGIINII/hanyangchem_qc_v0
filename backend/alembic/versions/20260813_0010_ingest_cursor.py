"""Add ingest progress and file stabilization tracking table.

Revision ID: 20260813_0010
Revises: 20260812_0009
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260813_0010"
down_revision = "20260812_0009"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "ingest_cursors",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("source_id", sa.String(128), nullable=False),
        sa.Column("entry_id", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="PENDING_STABILITY",
        ),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("modified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("document_id", uuid, nullable=True),
        sa.Column("checksum_sha256", sa.String(64), nullable=True),
        sa.Column("error_reason", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_ingest_cursors_document",
        ),
        sa.UniqueConstraint("source_id", "entry_id", name="uq_ingest_cursors_source_entry"),
        sa.CheckConstraint(
            "status IN ('PENDING_STABILITY','INGESTED','FAILED','VANISHED')",
            name="ck_ingest_cursors_status",
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
                GRANT SELECT, INSERT, UPDATE ON ingest_cursors TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.drop_table("ingest_cursors")
