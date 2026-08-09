from __future__ import annotations

from pathlib import Path

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_DEMO_VARIABLE = "NEXT_PUBLIC_HYC_PUBLIC_DEMO"


def test_compose_passes_the_public_demo_flag_to_the_web_build_with_a_safe_default() -> None:
    compose = yaml.safe_load((REPOSITORY_ROOT / "compose.yaml").read_text())

    web_build = compose["services"]["web"]["build"]

    assert web_build["args"][PUBLIC_DEMO_VARIABLE] == "${NEXT_PUBLIC_HYC_PUBLIC_DEMO:-0}"


def test_dockerfile_inlines_the_public_demo_flag_before_the_next_build() -> None:
    dockerfile_lines = (REPOSITORY_ROOT / "frontend/Dockerfile").read_text().splitlines()
    build_stage_end = next(
        index
        for index, line in enumerate(dockerfile_lines)
        if index > 0 and line.startswith("FROM ")
    )
    build_stage = dockerfile_lines[:build_stage_end]

    argument_index = build_stage.index(f"ARG {PUBLIC_DEMO_VARIABLE}=0")
    environment_index = build_stage.index(f"ENV {PUBLIC_DEMO_VARIABLE}=${PUBLIC_DEMO_VARIABLE}")
    pnpm_build_index = build_stage.index("RUN pnpm build")

    assert argument_index < environment_index < pnpm_build_index
