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


def test_statistics_dates_are_normalised() -> None:
    result = canonical_report_parameters(
        ReportKind.SUPPLIER_QUALITY_STATISTICS,
        {"period_start": "2026-08-01", "period_end": "2026-08-31"},
    )
    assert result["period_start"] == "2026-08-01"
    assert result["period_end"] == "2026-08-31"


def test_statistics_rejects_a_non_date_period() -> None:
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(
            ReportKind.SUPPLIER_QUALITY_STATISTICS,
            {"period_start": "not-a-date", "period_end": "2026-08-31"},
        )


def test_statistics_rejects_an_inverted_period() -> None:
    # An inverted window silently returns nothing rather than failing, which
    # reads as "no defects this month" — the most dangerous possible wrong answer.
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(
            ReportKind.SUPPLIER_QUALITY_STATISTICS,
            {"period_start": "2026-08-31", "period_end": "2026-08-01"},
        )


def test_lot_trace_still_requires_a_uuid() -> None:
    with pytest.raises(UnsupportedReportKind):
        canonical_report_parameters(ReportKind.LOT_TRACE, {"material_lot_id": "2026-08-01"})


def test_raw_data_shares_the_inspection_case_contract() -> None:
    result = canonical_report_parameters(ReportKind.RAW_DATA, {"inspection_case_id": _CASE})
    assert result == {"inspection_case_id": _CASE, "include_audit": False}
