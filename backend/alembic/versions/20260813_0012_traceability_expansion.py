"""Add P7 traceability expansion schema (BOM, production lots, lot consumptions).

Revision ID: 20260813_0012
Revises: 20260813_0011
"""

from __future__ import annotations

import os
import re

import sqlalchemy as sa

from alembic import op

revision = "20260813_0012"
down_revision = "20260813_0011"
branch_labels = None
depends_on = None

_ROLE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def upgrade() -> None:
    uuid = sa.Uuid()
    numeric_type = sa.Numeric(24, 12)

    op.create_table(
        "bill_of_materials",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("parent_material_id", uuid, nullable=False),
        sa.Column("component_material_id", uuid, nullable=False),
        sa.Column("quantity", numeric_type, nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["parent_material_id"], ["materials.id"], name="fk_bom_parent_material"
        ),
        sa.ForeignKeyConstraint(
            ["component_material_id"], ["materials.id"], name="fk_bom_component_material"
        ),
        sa.UniqueConstraint(
            "parent_material_id",
            "component_material_id",
            name="uq_bill_of_materials_parent_component",
        ),
        sa.CheckConstraint(
            "parent_material_id <> component_material_id",
            name="ck_bill_of_materials_no_self_reference",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_bill_of_materials_quantity_positive"),
    )

    op.create_table(
        "production_lots",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("production_lot_no", sa.String(64), nullable=False),
        sa.Column("product_material_id", uuid, nullable=False),
        sa.Column("produced_on", sa.Date(), nullable=False),
        sa.Column("quantity", numeric_type, nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PRODUCED"),
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
        sa.ForeignKeyConstraint(
            ["product_material_id"], ["materials.id"], name="fk_production_lots_product_material"
        ),
        sa.UniqueConstraint("production_lot_no", name="uq_production_lots_lot_no"),
        sa.CheckConstraint(
            "status IN ('DRAFT','PRODUCED','SHIPPED','CANCELLED')",
            name="ck_production_lots_status",
        ),
        sa.CheckConstraint("quantity > 0", name="ck_production_lots_quantity_positive"),
    )

    op.create_table(
        "material_lot_consumptions",
        sa.Column("id", uuid, primary_key=True),
        sa.Column("receipt_lot_allocation_id", uuid, nullable=False),
        sa.Column("production_lot_id", uuid, nullable=False),
        sa.Column("consumed_quantity", numeric_type, nullable=False),
        sa.Column("consumed_unit", sa.String(32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["receipt_lot_allocation_id"],
            ["receipt_lot_allocations.id"],
            name="fk_consumptions_receipt_lot_allocation",
        ),
        sa.ForeignKeyConstraint(
            ["production_lot_id"],
            ["production_lots.id"],
            name="fk_consumptions_production_lot",
        ),
        sa.UniqueConstraint(
            "receipt_lot_allocation_id",
            "production_lot_id",
            name="uq_material_lot_consumption_allocation_production",
        ),
        sa.CheckConstraint(
            "consumed_quantity > 0",
            name="ck_material_lot_consumptions_quantity_positive",
        ),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION hyc_deny_material_lot_consumption_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION 'material lot consumptions are immutable once recorded';
            END;
            $$ LANGUAGE plpgsql;
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_material_lot_consumption_immutable
            BEFORE UPDATE OR DELETE ON material_lot_consumptions
            FOR EACH ROW EXECUTE FUNCTION hyc_deny_material_lot_consumption_mutation();
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
                GRANT SELECT, INSERT, UPDATE ON bill_of_materials TO {role};
                GRANT SELECT, INSERT, UPDATE ON production_lots TO {role};
                GRANT SELECT, INSERT ON material_lot_consumptions TO {role};
              END IF;
            END $$;
            """
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_material_lot_consumption_immutable "
            "ON material_lot_consumptions;"
        )
        op.execute("DROP FUNCTION IF EXISTS hyc_deny_material_lot_consumption_mutation();")
    op.drop_table("material_lot_consumptions")
    op.drop_table("production_lots")
    op.drop_table("bill_of_materials")
