"""Accepted P0B artifacts are frozen while later phases evolve around them."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("relative_path", "expected_digest"),
    (
        (
            "backend/scripts/import_spec_workbook.py",
            "61caebd06f8ee7697c77a2f3c07265e1578b10924fea6fbd74e53bd76f818e23",
        ),
        (
            "backend/tests/integration/importers/test_spec_workbook_dry_run.py",
            "c0799b0413f093b06de41d56f9c27b20e388cb2448ef55e39de6e78120dba801",
        ),
    ),
)
def test_accepted_p0b_artifact_is_byte_identical(relative_path: str, expected_digest: str) -> None:
    root = Path(__file__).resolve().parents[3]
    assert hashlib.sha256((root / relative_path).read_bytes()).hexdigest() == expected_digest
