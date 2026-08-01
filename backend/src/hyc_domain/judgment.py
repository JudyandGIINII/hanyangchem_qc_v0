from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import StrEnum
from typing import Any

from hyc_domain.decimals import (
    DECIMAL_ARITHMETIC_VERSION,
    DecimalValidationError,
    DecimalValue,
    UnitRegistry,
    arithmetic_context,
)
from hyc_domain.errors import FailureCode
from hyc_domain.specs import Operator, Rule


class EngineDecision(StrEnum):
    """The only three deterministic candidate decisions emitted by the engine."""

    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    ON_HOLD = "ON_HOLD"


class WorkflowState(StrEnum):
    """Business workflow states; RETEST/SPECIAL_ACCEPTED are never engine outputs."""

    DRAFT = "DRAFT"
    DOCUMENT_PENDING = "DOCUMENT_PENDING"
    MATCH_REVIEW = "MATCH_REVIEW"
    SUPPLIER_REVIEW = "SUPPLIER_REVIEW"
    INTERNAL_TEST_PENDING = "INTERNAL_TEST_PENDING"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    LEAD_REVIEW = "LEAD_REVIEW"
    RETURNED = "RETURNED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    RETEST = "RETEST"
    SPECIAL_ACCEPTED = "SPECIAL_ACCEPTED"
    ON_HOLD = "ON_HOLD"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class MappingStatus(StrEnum):
    UNMAPPED = "UNMAPPED"
    ALIAS_MATCHED = "ALIAS_MATCHED"
    MANUAL_CONFIRMED = "MANUAL_CONFIRMED"

    @property
    def confirmed(self) -> bool:
        return self in {MappingStatus.ALIAS_MATCHED, MappingStatus.MANUAL_CONFIRMED}


class SourcePolicy(StrEnum):
    SUPPLIER_ONLY = "SUPPLIER_ONLY"
    INTERNAL_ONLY = "INTERNAL_ONLY"
    BOTH_INTERNAL_PRIORITY = "BOTH_INTERNAL_PRIORITY"
    BOTH_ALL_MUST_PASS = "BOTH_ALL_MUST_PASS"
    SUPPLIER_REFERENCE_INTERNAL_FINAL = "SUPPLIER_REFERENCE_INTERNAL_FINAL"


class MissingPolicy(StrEnum):
    REQUEST_SUPPLEMENT = "REQUEST_SUPPLEMENT"
    INTERNAL_SUBSTITUTE = "INTERNAL_SUBSTITUTE"
    SPECIAL_ACCEPTANCE = "SPECIAL_ACCEPTANCE"
    HOLD = "HOLD"
    REJECT = "REJECT"


class SamplePolicy(StrEnum):
    ALL_SAMPLES_IN_SPEC = "ALL_SAMPLES_IN_SPEC"
    AVERAGE_IN_SPEC = "AVERAGE_IN_SPEC"
    WORST_CASE_IN_SPEC = "WORST_CASE_IN_SPEC"
    MIN_IN_SPEC = "MIN_IN_SPEC"
    MAX_IN_SPEC = "MAX_IN_SPEC"
    MANUAL = "MANUAL"


@dataclass(frozen=True, slots=True)
class ItemInput:
    """Value-complete input for the ordered, fail-closed judgment pipeline.

    The rule is always the HYC rule. The optional supplier_rule is evaluated
    separately and never substitutes for the HYC rule.
    """

    rule: Rule
    source_policy: SourcePolicy
    missing_policy: MissingPolicy
    sample_policy: SamplePolicy
    supplier_values: tuple[Decimal, ...] = ()
    internal_values: tuple[Decimal, ...] = ()
    supplier_rule: Rule | None = None
    mapping_status: MappingStatus = MappingStatus.ALIAS_MATCHED
    mapped: bool = True
    source_confident: bool = True
    internal_required: bool = False
    raw_supplier_values: tuple[Any, ...] = ()
    raw_internal_values: tuple[Any, ...] = ()
    supplier_unit: str | None = None
    internal_unit: str | None = None
    target_unit: str | None = None
    unit_registry: UnitRegistry | None = None
    rounding_scale: int = 12
    rounding_version: str = "P2_HALF_EVEN_V1"


@dataclass(frozen=True, slots=True)
class ItemEvaluation:
    supplier_decision: EngineDecision | None
    hyc_supplier_decision: EngineDecision | None
    internal_decision: EngineDecision | None
    overall: EngineDecision
    completed_stages: tuple[str, ...]
    aggregations: tuple[SampleAggregation, ...] = ()
    failure_codes: tuple[FailureCode, ...] = ()


@dataclass(frozen=True, slots=True)
class SampleAggregation:
    source: str
    policy: SamplePolicy
    pre_round: Decimal | None
    result: Decimal | None
    rounding_scale: int
    rounding_version: str
    arithmetic_version: str = DECIMAL_ARITHMETIC_VERSION


def _evaluate_rule(rule: Rule, value: Decimal) -> EngineDecision:
    rule.validate()
    if rule.operator is Operator.GTE:
        accepted = value >= rule.lower  # type: ignore[operator]
    elif rule.operator is Operator.GT:
        accepted = value > rule.lower  # type: ignore[operator]
    elif rule.operator is Operator.LTE:
        accepted = value <= rule.upper  # type: ignore[operator]
    elif rule.operator is Operator.LT:
        accepted = value < rule.upper  # type: ignore[operator]
    elif rule.operator is Operator.BETWEEN_INCLUSIVE:
        accepted = rule.lower <= value <= rule.upper  # type: ignore[operator]
    elif rule.operator is Operator.BETWEEN_EXCLUSIVE:
        accepted = rule.lower < value < rule.upper  # type: ignore[operator]
    elif rule.operator is Operator.TARGET_PLUS_MINUS:
        accepted = abs(value - rule.target) <= rule.tolerance  # type: ignore[operator]
    elif rule.operator is Operator.EQUAL:
        accepted = value == rule.lower
    else:
        return EngineDecision.ON_HOLD
    return EngineDecision.ACCEPTED if accepted else EngineDecision.REJECTED


class JudgmentEngine:
    """Pure pipeline: mapping -> parse/type -> unit -> sample -> decisions -> policy."""

    def evaluate_item(self, item: ItemInput) -> EngineDecision:
        return self.evaluate_item_details(item).overall

    def evaluate_item_details(self, item: ItemInput) -> ItemEvaluation:
        stages: list[str] = []
        if not item.mapped or not item.mapping_status.confirmed:
            return self._held(stages)
        stages.append("mapping")
        if not item.source_confident:
            return self._held(stages)

        supplier = self._normalise_values(
            item.raw_supplier_values or item.supplier_values,
            source_unit=item.supplier_unit,
            item=item,
        )
        internal = self._normalise_values(
            item.raw_internal_values or item.internal_values,
            source_unit=item.internal_unit,
            item=item,
        )
        if supplier is None or internal is None:
            return self._held(stages)
        stages.extend(("parse_type", "unit"))
        if item.sample_policy is SamplePolicy.MANUAL:
            return self._held(stages)

        try:
            supplier_decision, supplier_aggregation = (
                self._aggregate(
                    supplier,
                    item.sample_policy,
                    item.supplier_rule,
                    source="supplier_spec",
                    scale=item.rounding_scale,
                    rounding_version=item.rounding_version,
                )
                if item.supplier_rule is not None
                else (None, None)
            )
            hyc_supplier_decision, hyc_supplier_aggregation = self._aggregate(
                supplier,
                item.sample_policy,
                item.rule,
                source="supplier_result_hyc_spec",
                scale=item.rounding_scale,
                rounding_version=item.rounding_version,
            )
            internal_decision, internal_aggregation = self._aggregate(
                internal,
                item.sample_policy,
                item.rule,
                source="internal_result_hyc_spec",
                scale=item.rounding_scale,
                rounding_version=item.rounding_version,
            )
        except (ArithmeticError, DecimalValidationError, ValueError):
            return self._held(stages, FailureCode.INVALID_RULE)
        aggregations = tuple(
            aggregation
            for aggregation in (
                supplier_aggregation,
                hyc_supplier_aggregation,
                internal_aggregation,
            )
            if aggregation is not None
        )
        stages.extend(("sample", "supplier_hyc_internal_decisions"))

        if item.internal_required and internal_decision is None:
            return ItemEvaluation(
                supplier_decision,
                hyc_supplier_decision,
                internal_decision,
                EngineDecision.ON_HOLD,
                tuple(stages),
                aggregations,
            )
        if item.source_policy not in set(SourcePolicy):
            return self._held(stages)
        supplier_expected = item.source_policy is not SourcePolicy.INTERNAL_ONLY
        if supplier_expected and hyc_supplier_decision is None:
            if item.source_policy is SourcePolicy.BOTH_ALL_MUST_PASS:
                overall = EngineDecision.ON_HOLD
            else:
                overall = self._evaluate_supplier_missing(
                    item.missing_policy,
                    internal_decision,
                )
            stages.extend(("source_policy", "missing_policy", "overall"))
            return ItemEvaluation(
                supplier_decision,
                hyc_supplier_decision,
                internal_decision,
                overall,
                tuple(stages),
                aggregations,
            )

        chosen: tuple[EngineDecision | None, ...]
        if item.source_policy is SourcePolicy.SUPPLIER_ONLY:
            chosen = (hyc_supplier_decision,)
        elif item.source_policy in {
            SourcePolicy.INTERNAL_ONLY,
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
        }:
            chosen = (internal_decision,)
        elif item.source_policy is SourcePolicy.BOTH_INTERNAL_PRIORITY:
            chosen = (
                internal_decision if internal_decision is not None else hyc_supplier_decision,
            )
        elif item.source_policy is SourcePolicy.BOTH_ALL_MUST_PASS:
            chosen = (hyc_supplier_decision, internal_decision)
        else:
            return self._held(stages)
        stages.extend(("source_policy", "missing_policy"))
        overall = self._combine(chosen)
        stages.append("overall")
        return ItemEvaluation(
            supplier_decision,
            hyc_supplier_decision,
            internal_decision,
            overall,
            tuple(stages),
            aggregations,
        )

    @staticmethod
    def _held(
        stages: list[str],
        failure_code: FailureCode = FailureCode.UNMAPPED_RESULT,
    ) -> ItemEvaluation:
        return ItemEvaluation(
            None,
            None,
            None,
            EngineDecision.ON_HOLD,
            tuple(stages),
            failure_codes=(failure_code,),
        )

    def _normalise_values(
        self,
        values: tuple[Any, ...],
        *,
        source_unit: str | None,
        item: ItemInput,
    ) -> tuple[Decimal, ...] | None:
        normalised: list[Decimal] = []
        for raw in values:
            try:
                parsed = DecimalValue.parse(raw)
                if source_unit is not None or item.target_unit is not None:
                    if (
                        item.unit_registry is None
                        or source_unit is None
                        or item.target_unit is None
                    ):
                        return None
                    parsed = item.unit_registry.convert(
                        parsed,
                        source_unit,
                        item.target_unit,
                        scale=item.rounding_scale,
                        rounding_version=item.rounding_version,
                    ).rounded
                normalised.append(parsed.value)
            except (ArithmeticError, DecimalValidationError, ValueError):
                return None
        return tuple(normalised)

    @staticmethod
    def _evaluate_supplier_missing(
        missing_policy: MissingPolicy, internal: EngineDecision | None
    ) -> EngineDecision:
        if missing_policy is MissingPolicy.REJECT:
            return EngineDecision.REJECTED
        if missing_policy is MissingPolicy.INTERNAL_SUBSTITUTE:
            return EngineDecision.ON_HOLD if internal is None else internal
        return EngineDecision.ON_HOLD

    def evaluate_case(self, items: tuple[ItemInput, ...]) -> EngineDecision:
        if not items:
            return EngineDecision.ON_HOLD
        return self._combine(tuple(self.evaluate_item(item) for item in items))

    @staticmethod
    def _combine(values: tuple[EngineDecision | None, ...]) -> EngineDecision:
        if any(value is None or value is EngineDecision.ON_HOLD for value in values):
            return EngineDecision.ON_HOLD
        if any(value is EngineDecision.REJECTED for value in values):
            return EngineDecision.REJECTED
        return EngineDecision.ACCEPTED

    def _aggregate(
        self,
        values: tuple[Decimal, ...],
        policy: SamplePolicy,
        rule: Rule,
        *,
        source: str,
        scale: int,
        rounding_version: str,
    ) -> tuple[EngineDecision | None, SampleAggregation | None]:
        if not values:
            return None, None
        rule.validate()
        decisions = tuple(_evaluate_rule(rule, value) for value in values)
        if policy in {
            SamplePolicy.ALL_SAMPLES_IN_SPEC,
            SamplePolicy.WORST_CASE_IN_SPEC,
        }:
            return self._combine(decisions), SampleAggregation(
                source,
                policy,
                None,
                None,
                scale,
                rounding_version,
            )
        if policy is SamplePolicy.AVERAGE_IN_SPEC:
            with localcontext(arithmetic_context()):
                pre_round = sum(values, Decimal(0)) / Decimal(len(values))
                result = pre_round.quantize(Decimal(1).scaleb(-scale))
            return _evaluate_rule(rule, result), SampleAggregation(
                source,
                policy,
                pre_round,
                result,
                scale,
                rounding_version,
            )
        if policy is SamplePolicy.MIN_IN_SPEC:
            result = min(values)
            return _evaluate_rule(rule, result), SampleAggregation(
                source,
                policy,
                result,
                result,
                scale,
                rounding_version,
            )
        if policy is SamplePolicy.MAX_IN_SPEC:
            result = max(values)
            return _evaluate_rule(rule, result), SampleAggregation(
                source,
                policy,
                result,
                result,
                scale,
                rounding_version,
            )
        return EngineDecision.ON_HOLD, SampleAggregation(
            source,
            policy,
            None,
            None,
            scale,
            rounding_version,
        )
