from __future__ import annotations

from fastapi import APIRouter, Request

from hyc_api.auth import require_principal
from hyc_api.contracts import ModuleFeatureFlagsResponse
from hyc_api.module_exposure import resolve_module_exposure_flags

router = APIRouter(prefix="/api/v1", tags=["p5-feature-flags"])


@router.get("/feature-flags", response_model=ModuleFeatureFlagsResponse)
def feature_flags(request: Request) -> ModuleFeatureFlagsResponse:
    require_principal(request)
    flags = resolve_module_exposure_flags(request.app.state.settings)
    return ModuleFeatureFlagsResponse(
        ncr_report_module_enabled=flags.ncr_report_module_enabled,
        ncr_approver_module_enabled=flags.ncr_approver_module_enabled,
        ncr_retest_module_enabled=flags.ncr_retest_module_enabled,
        ncr_attachment_module_enabled=flags.ncr_attachment_module_enabled,
        ncr_completion_date_module_enabled=flags.ncr_completion_date_module_enabled,
    )
