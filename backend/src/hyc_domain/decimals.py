from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import (
    ROUND_HALF_EVEN,
    Clamped,
    Context,
    Decimal,
    DivisionByZero,
    FloatOperation,
    InvalidOperation,
    Overflow,
    Underflow,
    localcontext,
)
from enum import StrEnum

from hyc_domain.errors import CodedDomainError, FailureCode

_CANONICAL = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
DECIMAL_ARITHMETIC_VERSION = "P2_DECIMAL_CONTEXT_V1"
DECIMAL_PRECISION = 96


def arithmetic_context() -> Context:
    """Return the complete v1 arithmetic context, independent of process globals."""
    context = Context(prec=DECIMAL_PRECISION, rounding=ROUND_HALF_EVEN)
    for signal in context.traps:
        context.traps[signal] = False
    for signal in (
        Clamped,
        DivisionByZero,
        FloatOperation,
        InvalidOperation,
        Overflow,
        Underflow,
    ):
        context.traps[signal] = True
    return context


class DecimalValidationError(CodedDomainError):
    """Raised when a boundary value is not an exact canonical Decimal."""

    code = FailureCode.INVALID_DECIMAL


@dataclass(frozen=True, slots=True)
class DecimalValue:
    """Exact numerical boundary value; floats and exponent notation are forbidden."""

    value: Decimal

    @classmethod
    def parse(cls, raw: str | Decimal) -> DecimalValue:
        if isinstance(raw, float) or not isinstance(raw, (str, Decimal)):
            raise DecimalValidationError("decimal values must be strings or Decimal, never float")
        text = str(raw)
        if not _CANONICAL.fullmatch(text):
            raise DecimalValidationError("decimal value must use canonical fixed-point notation")
        value = Decimal(text)
        if not value.is_finite():
            raise DecimalValidationError("decimal value must be finite")
        if value.is_zero() and value.is_signed():
            raise DecimalValidationError("negative zero is not canonical")
        return cls(value)

    def canonical(self) -> str:
        return format(self.value, "f")


class Dimension(StrEnum):
    MASS = "MASS"
    LENGTH = "LENGTH"
    PERCENT = "PERCENT"
    COUNT = "COUNT"


@dataclass(frozen=True, slots=True)
class Unit:
    code: str
    dimension: Dimension
    factor_to_base: Decimal
    conversion_version: str


@dataclass(frozen=True, slots=True)
class ConvertedValue:
    pre_round: DecimalValue
    rounded: DecimalValue
    source_unit: str
    target_unit: str
    conversion_version: str
    rounding_version: str


class UnitRegistry:
    """Versioned conversion table. Values retain their exact pre-round result."""

    def __init__(self, units: tuple[Unit, ...]) -> None:
        self._units: dict[str, Unit] = {}
        for unit in units:
            if (
                not isinstance(unit.code, str)
                or not unit.code.strip()
                or not isinstance(unit.conversion_version, str)
                or not unit.conversion_version.strip()
                or not isinstance(unit.dimension, Dimension)
            ):
                raise DecimalValidationError("unit code and conversion version are required")
            if unit.code in self._units:
                raise DecimalValidationError("unit codes must be unique")
            if (
                not isinstance(unit.factor_to_base, Decimal)
                or not unit.factor_to_base.is_finite()
                or unit.factor_to_base <= 0
            ):
                raise DecimalValidationError("unit factor must be a finite positive Decimal")
            self._units[unit.code] = unit

    def convert(
        self,
        value: DecimalValue,
        source: str,
        target: str,
        *,
        scale: int,
        rounding_version: str,
    ) -> ConvertedValue:
        if isinstance(scale, bool) or scale < 0 or scale > 18:
            raise DecimalValidationError("rounding scale must be between 0 and 18")
        if not rounding_version or not rounding_version.strip():
            raise DecimalValidationError("rounding version is required")
        source_unit = self._units.get(source)
        target_unit = self._units.get(target)
        if source_unit is None or target_unit is None:
            raise DecimalValidationError("unknown unit")
        if source_unit.dimension != target_unit.dimension:
            raise DecimalValidationError("unit dimensions are incompatible")
        try:
            with localcontext(arithmetic_context()):
                pre_round = DecimalValue.parse(
                    format(
                        value.value
                        * source_unit.factor_to_base
                        / target_unit.factor_to_base,
                        "f",
                    )
                )
                quantum = Decimal(1).scaleb(-scale)
                rounded = DecimalValue.parse(
                    format(pre_round.value.quantize(quantum), "f")
                )
        except (ArithmeticError, DecimalValidationError) as error:
            raise DecimalValidationError("decimal conversion failed") from error
        return ConvertedValue(
            pre_round=pre_round,
            rounded=rounded,
            source_unit=source,
            target_unit=target,
            conversion_version=f"{source_unit.conversion_version}:{target_unit.conversion_version}",
            rounding_version=rounding_version,
        )
