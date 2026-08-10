from __future__ import annotations

from dataclasses import dataclass

from hyc_api.config import Settings


@dataclass(frozen=True, slots=True)
class ModuleExposureFlags:
    """UI exposure only; these values are not passed to domain or DB guards."""

    ncr_report_module_enabled: bool
    ncr_approver_module_enabled: bool
    ncr_retest_module_enabled: bool
    ncr_attachment_module_enabled: bool
    ncr_completion_date_module_enabled: bool


def resolve_module_exposure_flags(settings: Settings) -> ModuleExposureFlags:
    return ModuleExposureFlags(
        ncr_report_module_enabled=settings.ncr_report_module_enabled,
        ncr_approver_module_enabled=settings.ncr_approver_module_enabled,
        ncr_retest_module_enabled=settings.ncr_retest_module_enabled,
        ncr_attachment_module_enabled=settings.ncr_attachment_module_enabled,
        ncr_completion_date_module_enabled=settings.ncr_completion_date_module_enabled,
    )
