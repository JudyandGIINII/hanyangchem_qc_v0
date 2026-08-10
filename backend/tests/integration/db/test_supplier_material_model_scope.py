from __future__ import annotations

import os

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from alembic import command
from hyc_api.routes.specs import validate_profile_scope
from hyc_data.models import Material, MaterialModel, SpecProfile, Supplier

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


def test_supplier_material_model_scope_allows_supported_scopes_and_rejects_wrong_model(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        material = Material(name="material")
        other_material = Material(name="other material")
        supplier = Supplier(name="supplier")
        session.add_all((material, other_material, supplier))
        session.flush()
        model = MaterialModel(material_id=material.id, name="model")
        wrong_model = MaterialModel(material_id=other_material.id, name="wrong model")
        session.add_all((model, wrong_model))
        session.flush()

        profiles = (
            SpecProfile(material_id=material.id, name="material only"),
            SpecProfile(
                material_id=material.id,
                supplier_id=supplier.id,
                name="material supplier",
            ),
            SpecProfile(
                material_id=material.id,
                supplier_id=supplier.id,
                model_id=model.id,
                name="material supplier model",
            ),
        )
        session.add_all(profiles)
        session.commit()
        assert [profile.model_id for profile in profiles] == [None, None, model.id]

        with pytest.raises(
            HTTPException, match="Material model does not belong to material"
        ) as caught:
            validate_profile_scope(
                session,
                material_id=material.id,
                supplier_id=None,
                model_id=wrong_model.id,
                lock=False,
            )
        assert caught.value.status_code == 422
