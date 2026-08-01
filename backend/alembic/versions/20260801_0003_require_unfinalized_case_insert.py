"""Require every inspection case to be created without a final decision.

Revision 0002 remains immutable reviewed history. This follow-up adds only the
PostgreSQL INSERT-path workflow-ordering backstop and removes only that backstop
on downgrade.
"""

from __future__ import annotations

from alembic import op

revision = "20260801_0003"
down_revision = "20260731_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION hyc_require_unfinalized_case_insert() RETURNS trigger AS $$
        BEGIN
          IF NEW.final_decision IS NOT NULL THEN
            RAISE EXCEPTION 'inspection case must be created without a final decision';
          END IF;
          RETURN NEW;
        END; $$ LANGUAGE plpgsql;
        CREATE TRIGGER trg_inspection_case_unfinalized_insert
          BEFORE INSERT ON inspection_cases
          FOR EACH ROW EXECUTE FUNCTION hyc_require_unfinalized_case_insert();
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "DROP TRIGGER IF EXISTS trg_inspection_case_unfinalized_insert ON inspection_cases"
    )
    op.execute("DROP FUNCTION IF EXISTS hyc_require_unfinalized_case_insert()")
