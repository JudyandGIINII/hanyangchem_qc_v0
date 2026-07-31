from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_p1_baseline_migrates_cleanly() -> None:
    root = Path(__file__).resolve().parents[3]
    subprocess.run([sys.executable, str(root / "backend/scripts/check_migrations.py")], check=True)
