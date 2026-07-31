"""P1 contract foundation baseline (intentionally no domain tables)."""

from __future__ import annotations

revision = "20260731_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Reserve a portable Alembic head before P2 creates persistent models."""


def downgrade() -> None:
    """The baseline has no schema objects to remove."""
