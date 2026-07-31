"""Fail if a sensitive source document is tracked by Git; never opens documents."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".hwp",
    ".hwpx",
    ".pdf",
    ".ppt",
    ".pptx",
    ".xls",
    ".xlsb",
    ".xlsm",
    ".xlsx",
}


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    )
    forbidden = [path for path in result.stdout.splitlines() if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES]
    if forbidden:
        print("tracked sensitive documents are prohibited:\n" + "\n".join(forbidden))
        return 1
    print("tracked sensitive document scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
