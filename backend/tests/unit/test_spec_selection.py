from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from hyc_domain.specs import (
    Operator,
    Rule,
    SpecScope,
    SpecStatus,
    SpecVersion,
    select_effective_spec,
    validate_no_active_overlap,
)


def _spec(
    scope: SpecScope, version: int = 1, start: date = date(2026, 1, 1), end: date | None = None
) -> SpecVersion:
    return SpecVersion(uuid4(), scope, version, SpecStatus.ACTIVE, start, end)


def test_selects_most_specific_model_supplier_then_common() -> None:
    material, supplier, model = uuid4(), uuid4(), uuid4()
    common = _spec(SpecScope(material))
    supplier_specific = _spec(SpecScope(material, supplier), 2)
    exact = _spec(SpecScope(material, supplier, model), 3)
    assert (
        select_effective_spec(
            (common, supplier_specific, exact),
            material_id=material,
            supplier_id=supplier,
            model_id=model,
            when=date(2026, 2, 1),
        ).id
        == exact.id
    )


def test_active_scope_overlap_and_invalid_rule_fail_closed() -> None:
    scope = SpecScope(uuid4())
    with pytest.raises(ValueError, match="overlap"):
        validate_no_active_overlap((_spec(scope), _spec(scope, 2, date(2026, 1, 15))))
    with pytest.raises(ValueError):
        Rule(Operator.BETWEEN_INCLUSIVE, lower=None, upper=None).validate()


@pytest.mark.parametrize(
    "rule",
    (
        Rule(Operator.BETWEEN_INCLUSIVE, lower=Decimal("2"), upper=Decimal("1")),
        Rule(Operator.TARGET_PLUS_MINUS, target=Decimal("1"), tolerance=Decimal("-1")),
        Rule(Operator.GTE, lower=Decimal("NaN")),
        Rule(Operator.LTE, upper=Decimal("Infinity")),
        Rule(Operator.IN_SET, lower=Decimal("1"), allowed=frozenset({"yes"})),
        Rule(Operator.MANUAL_PASS_FAIL, lower=Decimal("1")),
    ),
)
def test_rule_rejects_invalid_or_irrelevant_columns(rule: Rule) -> None:
    with pytest.raises(ValueError):
        rule.validate()


def test_effective_dates_and_equal_specificity_ambiguity_fail_closed() -> None:
    scope = SpecScope(uuid4())
    with pytest.raises(ValueError, match="end"):
        SpecVersion(uuid4(), scope, 1, SpecStatus.ACTIVE, date(2026, 2, 1), date(2026, 1, 1))
    same_specificity = (_spec(scope, 1), _spec(scope, 2))
    with pytest.raises(ValueError, match="ambiguous"):
        select_effective_spec(
            same_specificity,
            material_id=scope.material_id,
            supplier_id=None,
            model_id=None,
            when=date(2026, 2, 1),
        )


def test_supplier_only_and_model_only_equal_specificity_ambiguity_fails_closed() -> None:
    material, supplier, model = uuid4(), uuid4(), uuid4()
    candidates = (
        _spec(SpecScope(material, supplier_id=supplier)),
        _spec(SpecScope(material, model_id=model)),
    )

    with pytest.raises(ValueError, match="ambiguous"):
        select_effective_spec(
            candidates,
            material_id=material,
            supplier_id=supplier,
            model_id=model,
            when=date(2026, 2, 1),
        )
