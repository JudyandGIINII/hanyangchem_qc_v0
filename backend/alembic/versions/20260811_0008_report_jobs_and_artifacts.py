"""Add report job and immutable report artifact tables.

Revision ID: 20260811_0008
Revises: 20260810_0007
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260811_0008"
down_revision = "20260810_0007"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    op.create_table(
        "report_jobs",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(32), nullable=False),
        sa.Column("failure_code", sa.String(64)),
        sa.Column("requested_by_id", uuid, nullable=False),
        sa.Column("actor_role", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name="ck_report_job_state_allowlist",
        ),
        sa.CheckConstraint(
            "(state <> 'FAILED') OR (failure_code IS NOT NULL)",
            name="ck_report_job_failure_code_present",
        ),
    )
    op.create_table(
        "report_artifacts",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("report_job_id", uuid, nullable=False, unique=True),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("media_type", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["report_job_id"], ["report_jobs.id"], name="fk_report_artifacts_report_job"
        ),
        sa.CheckConstraint("length(content_digest) = 64", name="ck_report_artifact_digest_length"),
        sa.CheckConstraint(
            "content_digest = lower(content_digest)", name="ck_report_artifact_digest_lowercase"
        ),
        sa.CheckConstraint("byte_size > 0", name="ck_report_artifact_byte_size_positive"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION hyc_deny_report_artifact_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'report artifacts are immutable once written';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_report_artifact_immutable
            BEFORE UPDATE OR DELETE ON report_artifacts
            FOR EACH ROW EXECUTE FUNCTION hyc_deny_report_artifact_mutation();
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
                GRANT SELECT, INSERT, UPDATE ON report_jobs TO {role};
                GRANT SELECT, INSERT ON report_artifacts TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_report_artifact_immutable ON report_artifacts;")
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_report_artifact_mutation();")
    op.drop_table("report_artifacts")
    op.drop_table("report_jobs")
