from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))


def main() -> int:
    from hyc_evaluation.runner import (
        load_fixture_bundle,
        run_synthetic_benchmark,
        write_benchmark_output,
    )

    parser = argparse.ArgumentParser(description="Run the offline P4-A synthetic benchmark")
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run_synthetic_benchmark(load_fixture_bundle(args.fixture))
    except (OSError, ValueError) as error:
        print(f"p4-golden: validation failed: {type(error).__name__}", file=sys.stderr)
        return 2
    if args.output is not None:
        write_benchmark_output(result, args.output)
    else:
        print(
            "p4-golden: provider=synthetic-fixture "
            f"cases={len(result.report.cases)} "
            f"review_required={str(result.report.review_required).lower()} "
            f"digest={result.report_sha256}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
