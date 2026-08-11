from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from uuid import UUID

from hyc_domain.errors import CodedDomainError, FailureCode


class UnsupportedReportKind(CodedDomainError):
    """Raised when a report kind or its parameter set is not supported."""

    code = FailureCode.INVALID_RULE


class ReportKind(StrEnum):
    INTEGRATED_INSPECTION = "INTEGRATED_INSPECTION"


_REQUIRED: dict[ReportKind, frozenset[str]] = {
    ReportKind.INTEGRATED_INSPECTION: frozenset({"inspection_case_id"}),
}
_OPTIONAL: dict[ReportKind, dict[str, Any]] = {
    ReportKind.INTEGRATED_INSPECTION: {"include_audit": False},
}


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
        try:
            canonical[key] = str(UUID(str(raw[key])))
        except ValueError as error:
            raise UnsupportedReportKind(f"{key} is not a UUID") from error
    for key in sorted(optional):
        canonical[key] = bool(raw.get(key, optional[key]))
    return dict(sorted(canonical.items()))
