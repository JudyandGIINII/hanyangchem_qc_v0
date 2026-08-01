from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class SpecStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class Operator(StrEnum):
    GTE = "GTE"
    GT = "GT"
    LTE = "LTE"
    LT = "LT"
    BETWEEN_INCLUSIVE = "BETWEEN_INCLUSIVE"
    BETWEEN_EXCLUSIVE = "BETWEEN_EXCLUSIVE"
    TARGET_PLUS_MINUS = "TARGET_PLUS_MINUS"
    EQUAL = "EQUAL"
    IN_SET = "IN_SET"
    CONTAINS = "CONTAINS"
    MANUAL_PASS_FAIL = "MANUAL_PASS_FAIL"


@dataclass(frozen=True, slots=True)
class SpecScope:
    material_id: UUID
    supplier_id: UUID | None = None
    model_id: UUID | None = None

    def specificity(self) -> int:
        return int(self.supplier_id is not None) + int(self.model_id is not None)

    def matches(
        self, *, material_id: UUID, supplier_id: UUID | None, model_id: UUID | None
    ) -> bool:
        return (
            self.material_id == material_id
            and (self.supplier_id is None or self.supplier_id == supplier_id)
            and (self.model_id is None or self.model_id == model_id)
        )


@dataclass(frozen=True, slots=True)
class SpecVersion:
    id: UUID
    scope: SpecScope
    version: int
    status: SpecStatus
    effective_from: date
    effective_to: date | None

    def __post_init__(self) -> None:
        if not isinstance(self.version, int) or isinstance(self.version, bool) or self.version <= 0:
            raise ValueError("semantic spec version must be a positive integer")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            raise ValueError("effective end date cannot precede start date")

    def effective_on(self, when: date) -> bool:
        return self.effective_from <= when and (
            self.effective_to is None or when <= self.effective_to
        )


def validate_no_active_overlap(specs: tuple[SpecVersion, ...]) -> None:
    active = [spec for spec in specs if spec.status is SpecStatus.ACTIVE]
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if left.scope != right.scope:
                continue
            if left.effective_from <= (right.effective_to or date.max) and right.effective_from <= (
                left.effective_to or date.max
            ):
                raise ValueError("active spec effective ranges overlap for the same scope")


def select_effective_spec(
    specs: tuple[SpecVersion, ...],
    *,
    material_id: UUID,
    supplier_id: UUID | None,
    model_id: UUID | None,
    when: date,
) -> SpecVersion:
    candidates = [
        spec
        for spec in specs
        if spec.status is SpecStatus.ACTIVE
        and spec.scope.matches(material_id=material_id, supplier_id=supplier_id, model_id=model_id)
        and spec.effective_on(when)
    ]
    if not candidates:
        raise LookupError("no effective active specification")
    candidates.sort(key=lambda spec: (spec.scope.specificity(), spec.version), reverse=True)
    if (
        len(candidates) > 1
        and candidates[0].scope.specificity() == candidates[1].scope.specificity()
    ):
        raise ValueError("ambiguous effective specification")
    return candidates[0]


@dataclass(frozen=True, slots=True)
class Rule:
    operator: Operator
    lower: Decimal | None = None
    upper: Decimal | None = None
    target: Decimal | None = None
    tolerance: Decimal | None = None
    allowed: frozenset[str] = frozenset()

    def validate(self) -> None:
        values = (self.lower, self.upper, self.target, self.tolerance)
        if any(value is not None and not value.is_finite() for value in values):
            raise ValueError("rule Decimal values must be finite")
        numeric_values_present = any(value is not None for value in values)
        if self.operator in {Operator.GTE, Operator.GT, Operator.EQUAL}:
            if (
                self.lower is None
                or any(value is not None for value in (self.upper, self.target, self.tolerance))
                or self.allowed
            ):
                raise ValueError("threshold/equality rule has invalid columns")
        elif self.operator in {Operator.LTE, Operator.LT}:
            if (
                self.upper is None
                or any(value is not None for value in (self.lower, self.target, self.tolerance))
                or self.allowed
            ):
                raise ValueError("threshold rule has invalid columns")
        elif self.operator in {Operator.BETWEEN_INCLUSIVE, Operator.BETWEEN_EXCLUSIVE}:
            if (
                self.lower is None
                or self.upper is None
                or self.lower > self.upper
                or self.target is not None
                or self.tolerance is not None
                or self.allowed
            ):
                raise ValueError("range rule has invalid columns")
        elif self.operator is Operator.TARGET_PLUS_MINUS:
            if (
                self.target is None
                or self.tolerance is None
                or self.tolerance < 0
                or self.lower is not None
                or self.upper is not None
                or self.allowed
            ):
                raise ValueError("tolerance rule has invalid columns")
        elif self.operator in {Operator.IN_SET, Operator.CONTAINS}:
            if not self.allowed or numeric_values_present:
                raise ValueError("set/text rule has invalid columns")
        elif self.operator is Operator.MANUAL_PASS_FAIL:
            if numeric_values_present or self.allowed:
                raise ValueError("manual rule cannot carry calculated columns")
        else:
            raise ValueError("unknown rule operator")
