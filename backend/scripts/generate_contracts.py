from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

ROOT = BACKEND.parent
SCHEMAS = ROOT / "contracts" / "schemas"


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def artifacts() -> dict[Path, str]:
    from hyc_api.contracts import ErrorEnvelope, ExtractionCandidate
    from hyc_api.main import create_app

    return {
        SCHEMAS / "extraction-candidate.schema.json": canonical_json(
            ExtractionCandidate.model_json_schema()
        ),
        SCHEMAS / "error-envelope.schema.json": canonical_json(ErrorEnvelope.model_json_schema()),
        ROOT / "contracts" / "openapi.json": canonical_json(create_app().openapi()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = [
        path
        for path, rendered in artifacts().items()
        if not path.exists() or path.read_text() != rendered
    ]
    if args.check:
        if stale:
            names = ", ".join(str(path.relative_to(ROOT)) for path in stale)
            print("contract artifacts are stale: " + names)
            return 1
        return 0
    for path, rendered in artifacts().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
