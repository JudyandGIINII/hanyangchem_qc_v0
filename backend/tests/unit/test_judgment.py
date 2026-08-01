from decimal import ROUND_UP, Decimal, localcontext

import pytest

from hyc_domain.errors import FailureCode
from hyc_domain.judgment import (
    EngineDecision,
    ItemInput,
    JudgmentEngine,
    MappingStatus,
    MissingPolicy,
    SamplePolicy,
    SourcePolicy,
    WorkflowState,
)
from hyc_domain.specs import Operator, Rule
from hyc_domain.workflow import (
    DocumentState,
    StateTransitionError,
    guard_document_transition,
    guard_transition,
)


def _item(**changes: object) -> ItemInput:
    values: dict[str, object] = dict(
        rule=Rule(Operator.GTE, lower=Decimal("10")),
        source_policy=SourcePolicy.BOTH_INTERNAL_PRIORITY,
        missing_policy=MissingPolicy.HOLD,
        sample_policy=SamplePolicy.ALL_SAMPLES_IN_SPEC,
        supplier_values=(Decimal("12"),),
        internal_values=(Decimal("11"),),
    )
    values.update(changes)
    return ItemInput(**values)  # type: ignore[arg-type]


def test_internal_result_is_final_over_supplier_and_hold_precedence() -> None:
    engine = JudgmentEngine()
    assert (
        engine.evaluate_item(
            _item(supplier_values=(Decimal("1"),), internal_values=(Decimal("11"),))
        )
        is EngineDecision.ACCEPTED
    )
    assert (
        engine.evaluate_item(_item(internal_values=(), internal_required=True))
        is EngineDecision.ON_HOLD
    )
    assert (
        engine.evaluate_case((_item(), _item(mapped=False, internal_values=(Decimal("99"),))))
        is EngineDecision.ON_HOLD
    )
    assert (
        engine.evaluate_case(
            (
                _item(supplier_values=(), missing_policy=MissingPolicy.REJECT),
                _item(mapped=False),
            )
        )
        is EngineDecision.ON_HOLD
    )


def test_unmapped_manual_and_supplier_missing_reject_fail_closed() -> None:
    engine = JudgmentEngine()
    assert engine.evaluate_item(_item(sample_policy=SamplePolicy.MANUAL)) is EngineDecision.ON_HOLD
    assert (
        engine.evaluate_item(_item(supplier_values=(), missing_policy=MissingPolicy.REJECT))
        is EngineDecision.REJECTED
    )


@pytest.mark.parametrize(
    ("source_policy", "supplier_missing", "internal_present", "internal_required", "expected"),
    (
        (SourcePolicy.SUPPLIER_ONLY, False, False, False, EngineDecision.ACCEPTED),
        (SourcePolicy.SUPPLIER_ONLY, True, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.SUPPLIER_ONLY, False, True, False, EngineDecision.ACCEPTED),
        (SourcePolicy.SUPPLIER_ONLY, True, True, False, EngineDecision.ON_HOLD),
        (SourcePolicy.SUPPLIER_ONLY, False, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.SUPPLIER_ONLY, True, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.SUPPLIER_ONLY, False, True, True, EngineDecision.ACCEPTED),
        (SourcePolicy.SUPPLIER_ONLY, True, True, True, EngineDecision.ON_HOLD),
        (SourcePolicy.INTERNAL_ONLY, False, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.INTERNAL_ONLY, True, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.INTERNAL_ONLY, False, True, False, EngineDecision.ACCEPTED),
        (SourcePolicy.INTERNAL_ONLY, True, True, False, EngineDecision.ACCEPTED),
        (SourcePolicy.INTERNAL_ONLY, False, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.INTERNAL_ONLY, True, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.INTERNAL_ONLY, False, True, True, EngineDecision.ACCEPTED),
        (SourcePolicy.INTERNAL_ONLY, True, True, True, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, False, False, False, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, True, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, False, True, False, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, True, True, False, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, False, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, True, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, False, True, True, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_INTERNAL_PRIORITY, True, True, True, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, False, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, True, False, False, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, False, True, False, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_ALL_MUST_PASS, True, True, False, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, False, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, True, False, True, EngineDecision.ON_HOLD),
        (SourcePolicy.BOTH_ALL_MUST_PASS, False, True, True, EngineDecision.ACCEPTED),
        (SourcePolicy.BOTH_ALL_MUST_PASS, True, True, True, EngineDecision.ON_HOLD),
        (
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
            False,
            False,
            False,
            EngineDecision.ON_HOLD,
        ),
        (
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
            True,
            False,
            False,
            EngineDecision.ON_HOLD,
        ),
        (
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
            False,
            True,
            False,
            EngineDecision.ACCEPTED,
        ),
        (SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL, True, True, False, EngineDecision.ON_HOLD),
        (
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
            False,
            False,
            True,
            EngineDecision.ON_HOLD,
        ),
        (SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL, True, False, True, EngineDecision.ON_HOLD),
        (
            SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
            False,
            True,
            True,
            EngineDecision.ACCEPTED,
        ),
        (SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL, True, True, True, EngineDecision.ON_HOLD),
    ),
)
def test_source_policy_supplier_missing_internal_presence_matrix(
    source_policy: SourcePolicy,
    supplier_missing: bool,
    internal_present: bool,
    internal_required: bool,
    expected: EngineDecision,
) -> None:
    engine = JudgmentEngine()
    assert (
        engine.evaluate_item(
            _item(
                source_policy=source_policy,
                supplier_values=() if supplier_missing else (Decimal("12"),),
                internal_values=(Decimal("11"),) if internal_present else (),
                internal_required=internal_required,
            )
        )
        is expected
    )


@pytest.mark.parametrize(
    ("missing_policy", "internal_values", "expected"),
    (
        (MissingPolicy.REJECT, (), EngineDecision.REJECTED),
        (MissingPolicy.INTERNAL_SUBSTITUTE, (), EngineDecision.ON_HOLD),
        (MissingPolicy.INTERNAL_SUBSTITUTE, (Decimal("11"),), EngineDecision.ACCEPTED),
        (MissingPolicy.INTERNAL_SUBSTITUTE, (Decimal("1"),), EngineDecision.REJECTED),
        (MissingPolicy.REQUEST_SUPPLEMENT, (Decimal("11"),), EngineDecision.ON_HOLD),
        (MissingPolicy.HOLD, (Decimal("11"),), EngineDecision.ON_HOLD),
        (MissingPolicy.SPECIAL_ACCEPTANCE, (Decimal("11"),), EngineDecision.ON_HOLD),
    ),
)
def test_supplier_missing_policy_is_applied_before_source_selection(
    missing_policy: MissingPolicy,
    internal_values: tuple[Decimal, ...],
    expected: EngineDecision,
) -> None:
    assert (
        JudgmentEngine().evaluate_item(
            _item(
                supplier_values=(), internal_values=internal_values, missing_policy=missing_policy
            )
        )
        is expected
    )


def test_workflow_guards_are_separate_from_engine_decisions() -> None:
    guard_transition(
        current=WorkflowState.DRAFT,
        target=WorkflowState.DOCUMENT_PENDING,
        role="INSPECTOR",
        reason=None,
    )
    try:
        guard_transition(
            current=WorkflowState.READY_FOR_REVIEW,
            target=WorkflowState.ACCEPTED,
            role="INSPECTOR",
            reason=None,
        )
    except StateTransitionError:
        pass
    else:
        raise AssertionError("wrong role must fail")
    with pytest.raises(StateTransitionError):
        guard_transition(
            current=WorkflowState.DRAFT,
            target=WorkflowState.READY_FOR_REVIEW,
            role="INSPECTOR",
            reason=None,
            re_evaluated=True,
        )


def test_engine_emits_only_canonical_three_candidate_states() -> None:
    assert {item.value for item in EngineDecision} == {
        "ACCEPTED",
        "REJECTED",
        "ON_HOLD",
    }
    assert {"RETEST", "SPECIAL_ACCEPTED"}.isdisjoint({item.value for item in EngineDecision})


def test_ordered_pipeline_fails_closed_and_keeps_supplier_hyc_decisions_separate() -> None:
    engine = JudgmentEngine()
    evaluation = engine.evaluate_item_details(
        _item(
            supplier_rule=Rule(Operator.GTE, lower=Decimal("5")),
            rule=Rule(Operator.GTE, lower=Decimal("10")),
            raw_supplier_values=("7",),
            supplier_values=(),
            internal_values=(Decimal("11"),),
        )
    )
    assert evaluation.supplier_decision is EngineDecision.ACCEPTED
    assert evaluation.hyc_supplier_decision is EngineDecision.REJECTED
    assert evaluation.internal_decision is EngineDecision.ACCEPTED
    assert evaluation.overall is EngineDecision.ACCEPTED
    assert evaluation.completed_stages == (
        "mapping",
        "parse_type",
        "unit",
        "sample",
        "supplier_hyc_internal_decisions",
        "source_policy",
        "missing_policy",
        "overall",
    )
    assert (
        engine.evaluate_item(_item(raw_supplier_values=(1.1,), supplier_values=()))
        is EngineDecision.ON_HOLD
    )
    assert (
        engine.evaluate_item(_item(mapping_status=MappingStatus.UNMAPPED)) is EngineDecision.ON_HOLD
    )
    assert (
        engine.evaluate_item(_item(mapping_status=MappingStatus.MANUAL_CONFIRMED))
        is EngineDecision.ACCEPTED
    )


def test_final_workflow_requires_role_reason_and_fresh_re_evaluation() -> None:
    with pytest.raises(StateTransitionError):
        guard_transition(
            current=WorkflowState.LEAD_REVIEW,
            target=WorkflowState.ACCEPTED,
            role="LEAD",
            reason=None,
            re_evaluated=False,
        )
    guard_transition(
        current=WorkflowState.LEAD_REVIEW,
        target=WorkflowState.ACCEPTED,
        role="LEAD",
        reason=None,
        re_evaluated=True,
    )
    with pytest.raises(StateTransitionError):
        guard_transition(
            current=WorkflowState.LEAD_REVIEW,
            target=WorkflowState.SPECIAL_ACCEPTED,
            role="LEAD",
            reason=None,
            re_evaluated=True,
        )
    guard_transition(
        current=WorkflowState.LEAD_REVIEW,
        target=WorkflowState.RETEST,
        role="LEAD",
        reason="synthetic retest reason",
        re_evaluated=True,
    )
    guard_document_transition(
        current=DocumentState.REVIEW_REQUIRED,
        target=DocumentState.PARSE_CONFIRMED,
        role="INSPECTOR",
        reason=None,
    )


@pytest.mark.parametrize("missing_policy", tuple(MissingPolicy))
def test_both_all_missing_supplier_is_always_on_hold(
    missing_policy: MissingPolicy,
) -> None:
    item = _item(
        source_policy=SourcePolicy.BOTH_ALL_MUST_PASS,
        missing_policy=missing_policy,
        supplier_values=(),
        internal_values=(Decimal("11"),),
    )
    assert JudgmentEngine().evaluate_item(item) is EngineDecision.ON_HOLD


def test_average_rounding_and_verdict_ignore_process_global_decimal_context() -> None:
    item = _item(
        rule=Rule(Operator.GTE, lower=Decimal("1.0000005")),
        source_policy=SourcePolicy.INTERNAL_ONLY,
        sample_policy=SamplePolicy.AVERAGE_IN_SPEC,
        supplier_values=(),
        internal_values=(Decimal("1.0000004"), Decimal("1.0000006")),
        rounding_scale=7,
        rounding_version="round-v1",
    )
    baseline = JudgmentEngine().evaluate_item_details(item)
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_UP
        mutated = JudgmentEngine().evaluate_item_details(item)
    assert mutated == baseline
    aggregation = next(
        entry for entry in baseline.aggregations if entry.source == "internal_result_hyc_spec"
    )
    assert aggregation.pre_round == Decimal("1.0000005")
    assert aggregation.result == Decimal("1.0000005")
    assert aggregation.rounding_version == "round-v1"


def test_invalid_persisted_style_rule_fails_closed_with_on_hold() -> None:
    invalid = Rule(
        Operator.GTE,
        lower=Decimal("1"),
        upper=Decimal("2"),
    )
    evaluation = JudgmentEngine().evaluate_item_details(_item(rule=invalid))
    assert evaluation.overall is EngineDecision.ON_HOLD
    assert evaluation.failure_codes == (FailureCode.INVALID_RULE,)


def test_on_hold_precedence_over_rejected_is_explicit_v1_policy() -> None:
    rejected = _item(
        source_policy=SourcePolicy.INTERNAL_ONLY,
        internal_values=(Decimal("1"),),
    )
    held = _item(mapped=False)
    assert JudgmentEngine().evaluate_case((rejected, held)) is EngineDecision.ON_HOLD


def test_all_workflow_states_are_reachable_without_draft_bypass() -> None:
    from hyc_domain.workflow import CASE_TRANSITIONS

    reachable = {WorkflowState.DRAFT}
    changed = True
    while changed:
        changed = False
        for transition in CASE_TRANSITIONS:
            if transition.current in reachable and transition.target not in reachable:
                reachable.add(transition.target)
                changed = True
    assert reachable == set(WorkflowState)
    assert not any(
        transition.current is WorkflowState.INTERNAL_TEST_PENDING
        and transition.target is WorkflowState.LEAD_REVIEW
        for transition in CASE_TRANSITIONS
    )


def test_case_transition_role_reason_and_re_evaluation_matrix() -> None:
    from hyc_domain.workflow import CASE_TRANSITIONS

    for transition in CASE_TRANSITIONS:
        guard_transition(
            current=transition.current,
            target=transition.target,
            role=transition.role,
            reason="required reason" if transition.requires_reason else None,
            re_evaluated=transition.requires_re_evaluation,
        )
        with pytest.raises(StateTransitionError):
            guard_transition(
                current=transition.current,
                target=transition.target,
                role="WRONG_ROLE",
                reason="required reason",
                re_evaluated=True,
            )
        if transition.requires_reason:
            with pytest.raises(StateTransitionError):
                guard_transition(
                    current=transition.current,
                    target=transition.target,
                    role=transition.role,
                    reason=" ",
                    re_evaluated=True,
                )
        if transition.requires_re_evaluation:
            with pytest.raises(StateTransitionError):
                guard_transition(
                    current=transition.current,
                    target=transition.target,
                    role=transition.role,
                    reason="required reason",
                    re_evaluated=False,
                )


def test_document_transition_role_reason_and_uniqueness_matrix() -> None:
    from hyc_domain.workflow import _DOCUMENT_TRANSITIONS_BY_KEY, DOCUMENT_TRANSITIONS

    assert len(DOCUMENT_TRANSITIONS) == 13
    assert len(_DOCUMENT_TRANSITIONS_BY_KEY) == len(DOCUMENT_TRANSITIONS)
    for transition in DOCUMENT_TRANSITIONS:
        guard_document_transition(
            current=transition.current,
            target=transition.target,
            role=transition.role,
            reason="required reason" if transition.requires_reason else None,
        )
        with pytest.raises(StateTransitionError):
            guard_document_transition(
                current=transition.current,
                target=transition.target,
                role="WRONG_ROLE",
                reason="required reason",
            )
        if transition.requires_reason:
            with pytest.raises(StateTransitionError):
                guard_document_transition(
                    current=transition.current,
                    target=transition.target,
                    role=transition.role,
                    reason=" ",
                )
