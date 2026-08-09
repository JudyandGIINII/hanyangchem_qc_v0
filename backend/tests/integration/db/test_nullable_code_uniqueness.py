from __future__ import annotations

import os

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from hyc_data.models import Material, MaterialModel, Supplier

POSTGRES_DSN = os.environ.get("HYC_P2_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.postgres


@pytest.fixture(scope="module")
def engine() -> Engine:
    if not POSTGRES_DSN:
        pytest.skip("HYC_P2_TEST_POSTGRES_DSN must name a disposable PostgreSQL database")
    config = Config("backend/alembic.ini")
    config.set_main_option("sqlalchemy.url", POSTGRES_DSN)
    command.upgrade(config, "head")
    value = create_engine(POSTGRES_DSN)
    yield value
    command.downgrade(config, "base")
    with value.connect() as connection:
        remaining = connection.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'alembic_version'"
            )
        )
        assert remaining.scalar_one() == 0
    value.dispose()


def _master(model_type: type[Supplier] | type[Material] | type[MaterialModel], code: str | None):
    if model_type is Supplier:
        return Supplier(supplier_code=code, name="synthetic supplier")
    if model_type is Material:
        return Material(material_code=code, name="synthetic material")
    return MaterialModel(material_id=None, model_code=code, name="synthetic model")


@pytest.mark.parametrize(
    ("model_type", "code_attribute"),
    (
        (Supplier, "supplier_code"),
        (Material, "material_code"),
        (MaterialModel, "model_code"),
    ),
)
def test_nullable_codes_allow_nulls_but_reject_non_null_insert_and_update_collisions(
    engine: Engine,
    model_type: type[Supplier] | type[Material] | type[MaterialModel],
    code_attribute: str,
) -> None:
    with Session(engine) as session:
        parent = Material(name="synthetic model parent") if model_type is MaterialModel else None
        if parent is not None:
            session.add(parent)
            session.flush()

        first = _master(model_type, None)
        second = _master(model_type, None)
        if parent is not None:
            first.material_id = parent.id
            second.material_id = parent.id
        session.add_all((first, second))
        session.commit()

        duplicate_one = _master(model_type, "DUPLICATE-CODE")
        duplicate_two = _master(model_type, "DUPLICATE-CODE")
        if parent is not None:
            duplicate_one.material_id = parent.id
            duplicate_two.material_id = parent.id
        session.add_all((duplicate_one, duplicate_two))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        update_source = _master(model_type, "SOURCE-CODE")
        update_target = _master(model_type, "TARGET-CODE")
        if parent is not None:
            update_source.material_id = parent.id
            update_target.material_id = parent.id
        session.add_all((update_source, update_target))
        session.commit()

        setattr(update_target, code_attribute, "SOURCE-CODE")
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
