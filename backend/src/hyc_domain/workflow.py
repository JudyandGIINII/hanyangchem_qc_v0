from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hyc_domain.errors import CodedDomainError, FailureCode
from hyc_domain.judgment import WorkflowState


class StateTransitionError(CodedDomainError):
    code = FailureCode.INVALID_TRANSITION


class DocumentState(StrEnum):
    RECEIVED = "RECEIVED"
    STABILIZING = "STABILIZING"
    HASHED = "HASHED"
    DUPLICATE = "DUPLICATE"
    PREPROCESSING = "PREPROCESSING"
    OCR_RUNNING = "OCR_RUNNING"
    PARSED = "PARSED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    PARSE_CONFIRMED = "PARSE_CONFIRMED"
    MATCH_PENDING = "MATCH_PENDING"
    MATCHED = "MATCHED"
    FAILED = "FAILED"
    ARCHIVED = "ARCHIVED"


@dataclass(frozen=True, slots=True)
class Transition:
    current: WorkflowState
    target: WorkflowState
    role: str
    requires_reason: bool = False
    requires_re_evaluation: bool = False


@dataclass(frozen=True, slots=True)
class DocumentTransition:
    current: DocumentState
    target: DocumentState
    role: str
    requires_reason: bool = False


CASE_TRANSITIONS = (
        Transition(WorkflowState.DRAFT, WorkflowState.DOCUMENT_PENDING, "INSPECTOR"),
        Transition(
            WorkflowState.DOCUMENT_PENDING,
            WorkflowState.MATCH_REVIEW,
            "INSPECTOR",
        ),
        Transition(
            WorkflowState.MATCH_REVIEW,
            WorkflowState.SUPPLIER_REVIEW,
            "INSPECTOR",
        ),
        Transition(
            WorkflowState.SUPPLIER_REVIEW,
            WorkflowState.INTERNAL_TEST_PENDING,
            "INSPECTOR",
        ),
        Transition(
            WorkflowState.SUPPLIER_REVIEW,
            WorkflowState.READY_FOR_REVIEW,
            "INSPECTOR",
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.INTERNAL_TEST_PENDING,
            WorkflowState.READY_FOR_REVIEW,
            "INSPECTOR",
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.READY_FOR_REVIEW,
            WorkflowState.LEAD_REVIEW,
            "INSPECTOR",
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.RETURNED,
            WorkflowState.READY_FOR_REVIEW,
            "INSPECTOR",
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.ACCEPTED,
            "LEAD",
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.REJECTED,
            "LEAD",
            requires_reason=True,
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.ON_HOLD,
            "LEAD",
            requires_reason=True,
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.RETEST,
            "LEAD",
            requires_reason=True,
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.SPECIAL_ACCEPTED,
            "LEAD",
            requires_reason=True,
            requires_re_evaluation=True,
        ),
        Transition(
            WorkflowState.LEAD_REVIEW,
            WorkflowState.RETURNED,
            "LEAD",
            requires_reason=True,
        ),
        Transition(
            WorkflowState.RETURNED,
            WorkflowState.DOCUMENT_PENDING,
            "INSPECTOR",
            requires_reason=True,
        ),
        Transition(
            WorkflowState.RETEST,
            WorkflowState.DOCUMENT_PENDING,
            "INSPECTOR",
            requires_reason=True,
        ),
        Transition(
            WorkflowState.DRAFT,
            WorkflowState.ON_HOLD,
            "INSPECTOR",
            requires_reason=True,
        ),
        Transition(
            WorkflowState.ON_HOLD,
            WorkflowState.DRAFT,
            "LEAD",
            requires_reason=True,
        ),
        Transition(WorkflowState.ACCEPTED, WorkflowState.CLOSED, "LEAD"),
        Transition(WorkflowState.REJECTED, WorkflowState.CLOSED, "LEAD"),
        Transition(WorkflowState.SPECIAL_ACCEPTED, WorkflowState.CLOSED, "LEAD"),
        Transition(
            WorkflowState.DRAFT,
            WorkflowState.CANCELLED,
            "INSPECTOR",
            requires_reason=True,
        ),
)

_CASE_TRANSITIONS_BY_KEY = {
    (item.current, item.target, item.role): item for item in CASE_TRANSITIONS
}
if len(_CASE_TRANSITIONS_BY_KEY) != len(CASE_TRANSITIONS):
    raise RuntimeError("case workflow contains a duplicate transition key")

DOCUMENT_TRANSITIONS = (
    DocumentTransition(DocumentState.RECEIVED, DocumentState.STABILIZING, "SYSTEM"),
    DocumentTransition(DocumentState.STABILIZING, DocumentState.HASHED, "SYSTEM"),
    DocumentTransition(DocumentState.HASHED, DocumentState.DUPLICATE, "SYSTEM"),
    DocumentTransition(DocumentState.HASHED, DocumentState.PREPROCESSING, "SYSTEM"),
    DocumentTransition(DocumentState.PREPROCESSING, DocumentState.OCR_RUNNING, "SYSTEM"),
    DocumentTransition(DocumentState.OCR_RUNNING, DocumentState.PARSED, "SYSTEM"),
    DocumentTransition(DocumentState.PARSED, DocumentState.REVIEW_REQUIRED, "SYSTEM"),
    DocumentTransition(DocumentState.PARSED, DocumentState.PARSE_CONFIRMED, "INSPECTOR"),
    DocumentTransition(DocumentState.REVIEW_REQUIRED, DocumentState.PARSE_CONFIRMED, "INSPECTOR"),
    DocumentTransition(DocumentState.PARSE_CONFIRMED, DocumentState.MATCH_PENDING, "INSPECTOR"),
    DocumentTransition(DocumentState.MATCH_PENDING, DocumentState.MATCHED, "INSPECTOR"),
    DocumentTransition(DocumentState.MATCHED, DocumentState.ARCHIVED, "LEAD"),
    DocumentTransition(
        DocumentState.FAILED,
        DocumentState.RECEIVED,
        "INSPECTOR",
        requires_reason=True,
    ),
)

_DOCUMENT_TRANSITIONS_BY_KEY = {
    (item.current, item.target, item.role): item for item in DOCUMENT_TRANSITIONS
}
if len(_DOCUMENT_TRANSITIONS_BY_KEY) != len(DOCUMENT_TRANSITIONS):
    raise RuntimeError("document workflow contains a duplicate transition key")


def guard_transition(
    *,
    current: WorkflowState,
    target: WorkflowState,
    role: str,
    reason: str | None,
    re_evaluated: bool = False,
) -> None:
    permitted = _CASE_TRANSITIONS_BY_KEY.get((current, target, role))
    if permitted is None:
        raise StateTransitionError("state transition or role is not permitted")
    if permitted.requires_reason and not (reason and reason.strip()):
        raise StateTransitionError("state transition requires a reason")
    if permitted.requires_re_evaluation and not re_evaluated:
        raise StateTransitionError("state transition requires deterministic re-evaluation")


def guard_document_transition(
    *,
    current: DocumentState,
    target: DocumentState,
    role: str,
    reason: str | None,
) -> None:
    permitted = _DOCUMENT_TRANSITIONS_BY_KEY.get((current, target, role))
    if permitted is None:
        raise StateTransitionError("document transition or role is not permitted")
    if permitted.requires_reason and not (reason and reason.strip()):
        raise StateTransitionError("document transition requires a reason")
