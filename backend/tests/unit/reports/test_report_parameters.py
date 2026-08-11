from __future__ import annotations

import pytest

from hyc_domain.reports import (
    ReportKind,
    UnsupportedReportKind,
    canonical_report_parameters,
)

_CASE = "3f1d9c8e-0b2a-4c7d-9e1f-5a6b7c8d9e0f"


def test_key_order_does_not_change_the_canonical_form() -> None:
    first = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE, "include_audit": True}
    )
    second = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"include_audit": True, "inspection_case_id": _CASE}
    )
    assert first == second
    assert list(first) == sorted(first)


def test_uuid_case_is_normalised() -> None:
    upper = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE.upper()}
    )
    assert upper["inspection_case_id"] == _CASE


def test_unknown_parameter_is_rejected() -> None:
    # Silently dropping an unknown key would make two different requests share
    # one idempotency hash and return each other's artifact.
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(
            ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE, "surprise": 1}
        )


def test_missing_required_parameter_is_rejected() -> None:
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(ReportKind.INTEGRATED_INSPECTION, {})


def test_include_audit_defaults_to_false() -> None:
    result = canonical_report_parameters(
        ReportKind.INTEGRATED_INSPECTION, {"inspection_case_id": _CASE}
    )
    assert result["include_audit"] is False
