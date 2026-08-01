from decimal import Decimal, getcontext, localcontext

import pytest

from hyc_domain.decimals import DecimalValidationError, DecimalValue, Dimension, Unit, UnitRegistry


def test_unit_conversion_preserves_pre_round_and_versions() -> None:
    registry = UnitRegistry(
        (
            Unit("g", Dimension.MASS, Decimal("1"), "units-v1"),
            Unit("kg", Dimension.MASS, Decimal("1000"), "units-v1"),
        )
    )
    converted = registry.convert(
        DecimalValue.parse("1250.555"), "g", "kg", scale=2, rounding_version="round-v1"
    )
    assert converted.pre_round.canonical() == "1.250555"
    assert converted.rounded.canonical() == "1.25"
    assert converted.conversion_version == "units-v1:units-v1"


def test_unit_conversion_rejects_dimension_mismatch() -> None:
    registry = UnitRegistry(
        (
            Unit("g", Dimension.MASS, Decimal("1"), "v1"),
            Unit("mm", Dimension.LENGTH, Decimal("1"), "v1"),
        )
    )
    with pytest.raises(DecimalValidationError):
        registry.convert(DecimalValue.parse("1"), "g", "mm", scale=1, rounding_version="v1")


def test_conversion_is_independent_of_mutated_global_decimal_context() -> None:
    registry = UnitRegistry(
        (
            Unit("a", Dimension.LENGTH, Decimal("1"), "v1"),
            Unit("b", Dimension.LENGTH, Decimal("3"), "v1"),
        )
    )
    baseline = registry.convert(
        DecimalValue.parse("1"),
        "a",
        "b",
        scale=12,
        rounding_version="round-v1",
    )
    with localcontext() as context:
        context.prec = 6
        context.rounding = "ROUND_UP"
        mutated = registry.convert(
            DecimalValue.parse("1"),
            "a",
            "b",
            scale=12,
            rounding_version="round-v1",
        )
    assert mutated == baseline
    assert baseline.pre_round.canonical().startswith("0.333333333333333333333333")
    assert getcontext().prec >= 6


@pytest.mark.parametrize(
    "units",
    (
        (Unit("", Dimension.MASS, Decimal("1"), "v1"),),
        (
            Unit("g", Dimension.MASS, Decimal("1"), "v1"),
            Unit("g", Dimension.MASS, Decimal("1"), "v2"),
        ),
        (Unit("g", Dimension.MASS, Decimal("0"), "v1"),),
        (Unit("g", Dimension.MASS, Decimal("NaN"), "v1"),),
        (Unit("g", Dimension.MASS, Decimal("1"), ""),),
        (Unit(" ", Dimension.MASS, Decimal("1"), "v1"),),
        (Unit("g", Dimension.MASS, Decimal("1"), " "),),
        (Unit("g", "MASS", Decimal("1"), "v1"),),  # type: ignore[arg-type]
    ),
)
def test_registry_rejects_invalid_unit_definitions(units: tuple[Unit, ...]) -> None:
    with pytest.raises(DecimalValidationError):
        UnitRegistry(units)


@pytest.mark.parametrize(
    "scale, rounding_version",
    ((-1, "round-v1"), (100, "round-v1"), (True, "round-v1"), (1, "")),
)
def test_conversion_rejects_invalid_rounding_contract(scale: int, rounding_version: str) -> None:
    registry = UnitRegistry((Unit("g", Dimension.MASS, Decimal("1"), "v1"),))
    with pytest.raises(DecimalValidationError):
        registry.convert(
            DecimalValue.parse("1"), "g", "g", scale=scale, rounding_version=rounding_version
        )
