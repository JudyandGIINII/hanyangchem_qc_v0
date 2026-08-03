from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

from hyc_local_ocr.engine import (  # noqa: E402
    PROHIBITED_RUNTIME_ENVIRONMENT,
    PaddleOcrEngine,
)
from hyc_local_ocr.errors import LocalOcrError  # noqa: E402
from hyc_local_ocr.manifest import (  # noqa: E402
    load_and_verify_manifest,
    manifest_binding_sha256,
)

EXPECTED_PACKAGES = {
    "numpy": "2.3.5",
    "opencv-contrib-python": "4.10.0.84",
    "paddleocr": "3.7.0",
    "paddlepaddle": "3.3.1",
    "pillow": "12.3.0",
    "pymupdf": "1.28.0",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed local OCR runtime preflight")
    parser.add_argument(
        "--manifest", type=Path, default=BACKEND / "local_ocr/model-manifest.v1.json"
    )
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--initialize-engine", action="store_true")
    args = parser.parse_args()
    try:
        if any(os.environ.get(name) for name in PROHIBITED_RUNTIME_ENVIRONMENT):
            raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID")
        for package, expected in EXPECTED_PACKAGES.items():
            if importlib.metadata.version(package) != expected:
                raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING")
        manifest = load_and_verify_manifest(args.manifest, args.models_root)
        initialization_attempts = 0
        if args.initialize_engine:
            engine = PaddleOcrEngine.from_local_models(args.manifest, args.models_root)
            initialization_attempts = engine.initialization_network_attempt_count
            if initialization_attempts:
                raise LocalOcrError("LOCAL_OCR_NETWORK_ACCESS_DENIED")
    except (importlib.metadata.PackageNotFoundError, LocalOcrError) as error:
        code = (
            error.code
            if isinstance(error, LocalOcrError)
            else "LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING"
        )
        print(json.dumps({"status": "BLOCKED", "error_code": code}, sort_keys=True))
        return 2
    print(
        json.dumps(
            {
                "engine": manifest.engine,
                "engine_version": manifest.engine_version,
                "initialization_network_attempt_count": initialization_attempts,
                "language": manifest.language,
                "manifest_binding_sha256": manifest_binding_sha256(manifest),
                "model_count": len(manifest.artifacts),
                "runtime_version": manifest.runtime_version,
                "status": "READY_LOCAL_ONLY",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
