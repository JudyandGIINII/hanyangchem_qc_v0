from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from hyc_evaluation.artifacts import (
    CandidateValue,
    EvaluationReason,
    StageErrorCode,
    StageName,
    StageWarningCode,
)
from hyc_evaluation.schema import CanonicalDecimal, GoldenDataset, GoldenModel, Identifier


class SyntheticEdgeRecord(GoldenModel):
    edge_id: Annotated[str, Field(pattern=r"^P4-EDGE-(?:00[1-9]|01[0-9]|020)$")]
    prd_edge_number: Annotated[int, Field(ge=1, le=20)]
    title: Annotated[str, Field(min_length=1, max_length=200)]
    synthetic_fixture_ref: Literal["p4a_edge_dataset.v1.json"]
    case_id: Identifier
    expected_value_or_failure: Annotated[str, Field(min_length=1, max_length=256)]
    expected_confidence: CanonicalDecimal | Literal["NOT_APPLICABLE"]
    expected_reason_codes: tuple[EvaluationReason, ...]
    expected_stage_warning_codes: tuple[StageWarningCode, ...]
    expected_disposition: Literal[
        "CANDIDATE_ONLY",
        "REVIEW_REQUIRED",
        "MANUAL_FALLBACK",
        "STABLE_FAILURE",
    ]
    owner_phase: Literal["P2", "P3", "P4-A", "P5"]
    executable_test_path: Annotated[str, Field(pattern=r"^backend/tests/[A-Za-z0-9_./-]+\.py$")]
    p4a_signal: Annotated[str, Field(min_length=1, max_length=512)]
    p4a_limit: Literal[
        "OFFLINE_SYNTHETIC_ONLY_NO_REAL_CORPUS_OR_PROVIDER",
        "SIGNAL_ONLY_EXISTING_OR_FUTURE_OWNER_REMAINS_AUTHORITATIVE",
    ]
    failure_stage: StageName | None
    failure_code: StageErrorCode | None

    @field_validator("expected_reason_codes", "expected_stage_warning_codes", mode="before")
    @classmethod
    def freeze_reason_codes(cls, value: object) -> object:
        if isinstance(value, list):
            if len(value) != len(set(value)):
                raise ValueError("edge reason codes must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def bind_failure_fields(self) -> SyntheticEdgeRecord:
        if (self.failure_stage is None) != (self.failure_code is None):
            raise ValueError("edge failure stage and code must be bound together")
        if self.failure_stage is not None and self.expected_disposition != "STABLE_FAILURE":
            raise ValueError("stage failures must declare STABLE_FAILURE")
        return self


class SyntheticCandidateCase(GoldenModel):
    case_id: Identifier
    values: tuple[CandidateValue, ...]
    observed_stage_warning_codes: tuple[StageWarningCode, ...]

    @field_validator("values", mode="before")
    @classmethod
    def freeze_values(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @field_validator("observed_stage_warning_codes", mode="before")
    @classmethod
    def freeze_observed_stage_warning_codes(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != len(set(value)):
                raise ValueError("observed stage warning codes must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def require_contiguous_candidate_order(self) -> SyntheticCandidateCase:
        orders = tuple(value.candidate_order for value in self.values)
        if orders != tuple(range(1, len(self.values) + 1)):
            raise ValueError("synthetic candidate order must be contiguous")
        return self


class SyntheticFixtureBundle(GoldenModel):
    fixture_schema_version: Literal["hyc.synthetic-fixture-bundle.v1"]
    dataset: GoldenDataset
    edge_matrix: tuple[SyntheticEdgeRecord, ...]
    candidate_cases: tuple[SyntheticCandidateCase, ...]

    @field_validator("edge_matrix", "candidate_cases", mode="before")
    @classmethod
    def freeze_edges(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_exact_prd_edge_matrix(self) -> SyntheticFixtureBundle:
        expected_ids = tuple(f"P4-EDGE-{index:03d}" for index in range(1, 21))
        if tuple(edge.edge_id for edge in self.edge_matrix) != expected_ids:
            raise ValueError("fixture must contain the exact ordered PRD 20-edge matrix")
        if tuple(edge.prd_edge_number for edge in self.edge_matrix) != tuple(range(1, 21)):
            raise ValueError("PRD edge numbers must be contiguous from 1 through 20")
        case_ids = tuple(case.case_id for case in self.dataset.cases)
        edge_case_ids = tuple(edge.case_id for edge in self.edge_matrix)
        if case_ids != edge_case_ids:
            raise ValueError("edge matrix must bind one-to-one in exact dataset case order")
        if case_ids != tuple(candidate.case_id for candidate in self.candidate_cases):
            raise ValueError("candidate cases must bind one-to-one in exact dataset case order")
        return self
