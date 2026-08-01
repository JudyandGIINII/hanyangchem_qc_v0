from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from hyc_data.models import (
    Material,
    MaterialModel,
    SpecItem,
    SpecProfile,
    SpecVersion,
    StandardTestItem,
    Supplier,
)

SUPPLIER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
MATERIAL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
MODEL_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3")
PROFILE_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4")
SPEC_VERSION_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa5")
PURITY_ITEM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa6")
MOISTURE_ITEM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa7")
PURITY_SPEC_ITEM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa8")
MOISTURE_SPEC_ITEM_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa9")


def seed_p3_fixture(session: Session) -> None:
    if session.get(Supplier, SUPPLIER_ID) is not None:
        return
    session.add_all(
        (
            Supplier(id=SUPPLIER_ID, supplier_code="P3-SYNTH-SUP", name="P3 합성 공급사"),
            Material(
                id=MATERIAL_ID,
                material_code="P3-CACL2-BEAD",
                name="염화칼슘 비드 (합성 fixture)",
                default_unit="kg",
            ),
        )
    )
    session.flush()
    session.add(
        MaterialModel(
            id=MODEL_ID,
            material_id=MATERIAL_ID,
            model_code="P3-BEAD-GENERAL",
            name="비드 일반형",
        )
    )
    session.flush()
    session.add(
        SpecProfile(
            id=PROFILE_ID,
            material_id=MATERIAL_ID,
            supplier_id=SUPPLIER_ID,
            model_id=MODEL_ID,
            name="P3 염화칼슘 비드 합성 기준",
        )
    )
    session.flush()
    session.add_all(
        (
            SpecVersion(
                id=SPEC_VERSION_ID,
                spec_profile_id=PROFILE_ID,
                version=1,
                status="ACTIVE",
                effective_from=date(2026, 1, 1),
            ),
            StandardTestItem(
                id=PURITY_ITEM_ID,
                code="CACL2_PURITY",
                name="염화칼슘 순도",
                data_type="NUMERIC",
                default_unit="%",
            ),
            StandardTestItem(
                id=MOISTURE_ITEM_ID,
                code="MOISTURE",
                name="수분",
                data_type="NUMERIC",
                default_unit="%",
            ),
        )
    )
    session.flush()
    session.add_all(
        (
            SpecItem(
                id=PURITY_SPEC_ITEM_ID,
                spec_version_id=SPEC_VERSION_ID,
                standard_test_item_id=PURITY_ITEM_ID,
                required=True,
                source_policy="SUPPLIER_ONLY",
                missing_policy="HOLD",
                operator="GTE",
                lower_value=Decimal("95.00"),
                unit="%",
                precision=2,
                sample_policy="ALL_SAMPLES_IN_SPEC",
            ),
            SpecItem(
                id=MOISTURE_SPEC_ITEM_ID,
                spec_version_id=SPEC_VERSION_ID,
                standard_test_item_id=MOISTURE_ITEM_ID,
                required=True,
                source_policy="SUPPLIER_REFERENCE_INTERNAL_FINAL",
                missing_policy="INTERNAL_SUBSTITUTE",
                operator="LTE",
                upper_value=Decimal("0.20"),
                unit="%",
                precision=2,
                sample_policy="ALL_SAMPLES_IN_SPEC",
            ),
        )
    )
    session.commit()
