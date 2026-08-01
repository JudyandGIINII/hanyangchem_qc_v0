from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from backend.scripts.check_migrations import EXPECTED_P2_TABLES  # noqa: E402


def test_historical_migrations_are_metadata_independent() -> None:
    root = Path(__file__).resolve().parents[3]
    for revision in (root / "backend/alembic/versions").glob("*.py"):
        if revision.name == "__init__.py":
            continue
        tree = ast.parse(revision.read_text(encoding="utf-8"))
        imported_models = any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("hyc_data.models")
            for node in ast.walk(tree)
        )
        metadata_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"create_all", "drop_all"}
        ]
        assert not imported_models, revision.name
        assert not metadata_calls, revision.name


@pytest.mark.parametrize(
    ("cwd", "explicit_table_override"),
    (("root", True), ("backend", False)),
)
def test_p2_roundtrip_has_exact_table_set_from_both_supported_cwds(
    cwd: str, explicit_table_override: bool
) -> None:
    workdir = ROOT if cwd == "root" else ROOT / "backend"
    command = [sys.executable, str(ROOT / "backend/scripts/check_migrations.py")]
    if explicit_table_override:
        command.extend(("--expect-tables", ",".join(sorted(EXPECTED_P2_TABLES))))
    subprocess.run(command, check=True, cwd=workdir)


def test_postgres_runner_uses_canonical_migration_table_set() -> None:
    runner = (ROOT / "backend/scripts/run_p2_postgres_tests.sh").read_text(encoding="utf-8")
    assert runner.count("check_migrations.py") == 1
    assert 'python "$root/backend/scripts/check_migrations.py"' in runner
    assert '--postgres-url "$owner_dsn"' in runner
    assert "--expect-tables" not in runner
