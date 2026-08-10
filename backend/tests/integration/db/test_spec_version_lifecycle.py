from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from hyc_api.routes.specs import activate_spec_version, retire_spec_version
from hyc_data.models import Material, SpecProfile, SpecVersion

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


def _profile(session: Session, name: str) -> SpecProfile:
    material = Material(name=f"material-{name}")
    session.add(material)
    session.flush()
    profile = SpecProfile(material_id=material.id, name=f"profile-{name}")
    session.add(profile)
    session.flush()
    return profile


def test_spec_version_check_constraints_and_profile_version_uniqueness(engine: Engine) -> None:
    with Session(engine) as session:
        profile = _profile(session, "constraints")
        session.add(
            SpecVersion(
                spec_profile_id=profile.id,
                version=1,
                status="INVALID",
                effective_from=date(2026, 1, 1),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        profile = _profile(session, "dates")
        session.add(
            SpecVersion(
                spec_profile_id=profile.id,
                version=1,
                status="DRAFT",
                effective_from=date(2026, 2, 1),
                effective_to=date(2026, 1, 1),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        profile = _profile(session, "unique")
        session.add_all(
            (
                SpecVersion(
                    spec_profile_id=profile.id,
                    version=1,
                    status="DRAFT",
                    effective_from=date(2026, 1, 1),
                ),
                SpecVersion(
                    spec_profile_id=profile.id,
                    version=1,
                    status="DRAFT",
                    effective_from=date(2026, 2, 1),
                ),
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


def test_lifecycle_rejects_illegal_transition_and_concurrent_second_activation(
    engine: Engine,
) -> None:
    with Session(engine) as session:
        profile = _profile(session, "lifecycle")
        first = SpecVersion(
            spec_profile_id=profile.id,
            version=1,
            status="DRAFT",
            effective_from=date(2026, 1, 1),
        )
        second = SpecVersion(
            spec_profile_id=profile.id,
            version=2,
            status="DRAFT",
            effective_from=date(2026, 1, 1),
        )
        session.add_all((first, second))
        session.commit()
        first_id, second_id = first.id, second.id

    def activate(version_id):
        with Session(engine) as session:
            try:
                activate_spec_version(session, version_id=version_id, expected_version=1)
            except HTTPException as error:
                session.rollback()
                return error.status_code, error.detail
            return 200, "ACTIVE"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(activate, (first_id, second_id)))

    assert sorted(status for status, _ in outcomes) == [200, 409]
    assert any(detail == "Spec profile already has an active version" for _, detail in outcomes)

    active_id = next(
        version_id
        for version_id, outcome in zip((first_id, second_id), outcomes, strict=True)
        if outcome[0] == 200
    )
    with Session(engine) as session:
        active = session.get(SpecVersion, active_id)
        assert active is not None
        retired = retire_spec_version(
            session, version_id=active.id, expected_version=active.lock_version
        )
        with pytest.raises(HTTPException, match="Illegal spec version transition"):
            activate_spec_version(
                session, version_id=retired.id, expected_version=retired.lock_version
            )
