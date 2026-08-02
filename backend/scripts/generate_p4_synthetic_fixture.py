from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))


def main() -> int:
    from hyc_evaluation.fixture import SyntheticFixtureBundle
    from hyc_evaluation.synthetic_data import generated_fixture_payload

    parser = argparse.ArgumentParser(description="Generate the non-sensitive P4-A fixture")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = SyntheticFixtureBundle.model_validate(generated_fixture_payload())
    rendered = (
        json.dumps(
            bundle.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
