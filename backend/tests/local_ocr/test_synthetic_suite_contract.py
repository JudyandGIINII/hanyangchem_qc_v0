from __future__ import annotations

from types import SimpleNamespace

from backend.scripts.run_local_ocr_smoke import _associated_candidate_lines

from hyc_local_ocr.synthetic import (
    REQUIRED_DEGRADATIONS,
    SyntheticEngineeringMetrics,
    synthetic_case_plan,
)


def test_synthetic_plan_is_seeded_complete_and_non_sensitive() -> None:
    first = synthetic_case_plan(seed=20260803)
    second = synthetic_case_plan(seed=20260803)

    assert first == second
    assert {degradation for case in first for degradation in case.degradations} == set(
        REQUIRED_DEGRADATIONS
    )
    assert all(case.synthetic is True for case in first)
    assert all(case.provenance_marker == "generated-non-sensitive-synthetic" for case in first)


def test_engineering_gate_requires_accuracy_and_review_exposure() -> None:
    passing = SyntheticEngineeringMetrics(
        required_header_accuracy="0.95",
        numeric_accuracy="0.98",
        review_trigger_exposure="1.00",
    )
    failing = SyntheticEngineeringMetrics(
        required_header_accuracy="0.94",
        numeric_accuracy="0.98",
        review_trigger_exposure="1.00",
    )

    assert passing.engineering_gate_passed is True
    assert passing.production_readiness_claim is False
    assert failing.engineering_gate_passed is False


def test_smoke_associates_split_fields_only_with_same_physical_line() -> None:
    def value(text: str, left: float, top: float, right: float, bottom: float) -> object:
        return SimpleNamespace(
            raw_text=text,
            provenance=SimpleNamespace(
                page_number=1,
                bbox=SimpleNamespace(left=left, top=top, right=right, bottom=bottom),
            ),
        )

    horizontal = SimpleNamespace(
        values=[
            value("SUPPLIER:", 0.10, 0.10, 0.30, 0.14),
            value("TEST LAB", 0.31, 0.10, 0.50, 0.14),
            value("PRODUCT: OTHER", 0.10, 0.20, 0.50, 0.24),
        ]
    )
    vertical = SimpleNamespace(
        values=[
            value("SUPPLIER:", 0.10, 0.10, 0.14, 0.30),
            value("TEST LAB", 0.10, 0.31, 0.14, 0.50),
            value("PRODUCT: OTHER", 0.20, 0.10, 0.24, 0.50),
        ]
    )

    assert _associated_candidate_lines(horizontal)[0] == "SUPPLIER: TEST LAB"  # type: ignore[arg-type]
    assert _associated_candidate_lines(vertical)[0] == "SUPPLIER: TEST LAB"  # type: ignore[arg-type]
