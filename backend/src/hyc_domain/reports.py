from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Any
from uuid import UUID

from hyc_domain.errors import CodedDomainError, FailureCode


class UnsupportedReportKind(CodedDomainError):
    """Raised when a report kind or its parameter set is not supported."""

    code = FailureCode.INVALID_RULE


class ReportKind(StrEnum):
    INTEGRATED_INSPECTION = "INTEGRATED_INSPECTION"
    RAW_DATA = "RAW_DATA"
    LOT_TRACE = "LOT_TRACE"
    SUPPLIER_QUALITY_STATISTICS = "SUPPLIER_QUALITY_STATISTICS"


_REQUIRED: dict[ReportKind, frozenset[str]] = {
    ReportKind.INTEGRATED_INSPECTION: frozenset({"inspection_case_id"}),
    ReportKind.RAW_DATA: frozenset({"inspection_case_id"}),
    ReportKind.LOT_TRACE: frozenset({"material_lot_id"}),
    ReportKind.SUPPLIER_QUALITY_STATISTICS: frozenset({"period_start", "period_end"}),
}
_OPTIONAL: dict[ReportKind, dict[str, Any]] = {
    ReportKind.INTEGRATED_INSPECTION: {"include_audit": False},
    ReportKind.RAW_DATA: {"include_audit": False},
    ReportKind.LOT_TRACE: {"include_audit": False},
    ReportKind.SUPPLIER_QUALITY_STATISTICS: {"include_audit": False},
}
#: Required keys carrying an ISO-8601 calendar date rather than a UUID. Naming them
#: here keeps one canonicaliser rather than branching per kind, and an unnamed key
#: still falls through to the UUID rule so a typo cannot silently pass unvalidated.
_DATE_PARAMS: frozenset[str] = frozenset({"period_start", "period_end"})


def canonical_report_parameters(kind: ReportKind, raw: Mapping[str, Any]) -> dict[str, Any]:
    required = _REQUIRED[kind]
    optional = _OPTIONAL[kind]
    unknown = set(raw) - required - set(optional)
    if unknown:
        raise UnsupportedReportKind(
            "unsupported report parameters: " + ",".join(sorted(unknown))
        )
    missing = required - set(raw)
    if missing:
        raise UnsupportedReportKind("missing report parameters: " + ",".join(sorted(missing)))
    canonical: dict[str, Any] = {}
    for key in sorted(required):
        if key in _DATE_PARAMS:
            try:
                canonical[key] = date.fromisoformat(str(raw[key])).isoformat()
            except ValueError as error:
                raise UnsupportedReportKind(f"{key} is not an ISO-8601 date") from error
            continue
        try:
            canonical[key] = str(UUID(str(raw[key])))
        except ValueError as error:
            raise UnsupportedReportKind(f"{key} is not a UUID") from error
    if {"period_start", "period_end"} <= set(canonical) and (
        canonical["period_start"] > canonical["period_end"]
    ):
        raise UnsupportedReportKind("period_start must not be after period_end")
    for key in sorted(optional):
        canonical[key] = bool(raw.get(key, optional[key]))
    return dict(sorted(canonical.items()))
