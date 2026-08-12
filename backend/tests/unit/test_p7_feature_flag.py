from __future__ import annotations

from hyc_api.config import Settings


def test_p7_traceability_flag_defaults_to_false() -> None:
    settings = Settings()
    assert settings.traceability_enabled is False
