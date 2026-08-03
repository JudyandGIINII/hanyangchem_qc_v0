from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND / "src"))

from hyc_api.contracts import ExtractionCandidate, ExtractionValue  # noqa: E402
from hyc_api.extraction import BytesDocumentResolver, LocalOcrExtractionProvider  # noqa: E402
from hyc_local_ocr.contracts import LocalOcrResult  # noqa: E402
from hyc_local_ocr.engine import PaddleOcrEngine  # noqa: E402
from hyc_local_ocr.errors import LocalOcrError  # noqa: E402
from hyc_local_ocr.manifest import (  # noqa: E402
    load_and_verify_manifest,
    manifest_binding_sha256,
)
from hyc_local_ocr.pdf_backend import PyMuPdfDocumentBackend  # noqa: E402
from hyc_local_ocr.pipeline import LocalOcrPipeline  # noqa: E402
from hyc_local_ocr.preprocess import OpenCvPreprocessor  # noqa: E402
from hyc_local_ocr.synthetic import (  # noqa: E402
    SyntheticEngineeringMetrics,
    generate_synthetic_smoke_cases,
)


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _line_has_pair(lines: tuple[str, ...], field: str, value: str) -> bool:
    expected_field = re.sub(r"\s+", " ", field.strip()).upper()
    expected_value = re.sub(r"\s+", " ", value.strip()).upper()
    return any(expected_field in line and expected_value in line for line in lines)


def _associated_candidate_lines(candidate: ExtractionCandidate) -> tuple[str, ...]:
    groups: list[list[ExtractionValue]] = []
    ordered = sorted(
        candidate.values,
        key=lambda value: (
            value.provenance.page_number,
            value.provenance.bbox.top,
            value.provenance.bbox.left,
        ),
    )
    for value in ordered:
        bbox = value.provenance.bbox
        center = (bbox.top + bbox.bottom) / 2
        height = bbox.bottom - bbox.top
        width = bbox.right - bbox.left
        matched_group: list[ExtractionValue] | None = None
        for group in groups:
            reference = group[0].provenance
            reference_center = (reference.bbox.top + reference.bbox.bottom) / 2
            reference_height = reference.bbox.bottom - reference.bbox.top
            reference_x_center = (reference.bbox.left + reference.bbox.right) / 2
            reference_width = reference.bbox.right - reference.bbox.left
            horizontal = width >= height and reference_width >= reference_height
            aligned = (
                abs(center - reference_center) <= max(height, reference_height) * 0.75
                if horizontal
                else abs((bbox.left + bbox.right) / 2 - reference_x_center)
                <= max(width, reference_width) * 0.75
            )
            if (
                reference.page_number == value.provenance.page_number
                and aligned
            ):
                matched_group = group
                break
        if matched_group is None:
            groups.append([value])
        else:
            matched_group.append(value)
    return tuple(
        " ".join(
            re.sub(r"\s+", " ", value.raw_text.strip()).upper()
            for value in sorted(
                group,
                key=lambda item: (
                    item.provenance.bbox.left
                    if (
                        group[0].provenance.bbox.right
                        - group[0].provenance.bbox.left
                        >= group[0].provenance.bbox.bottom
                        - group[0].provenance.bbox.top
                    )
                    else item.provenance.bbox.top
                ),
            )
        )
        for group in groups
    )


class _CapturingLocalOcrPipeline(LocalOcrPipeline):
    last_result: LocalOcrResult | None = None

    def extract(self, document_bytes: bytes) -> LocalOcrResult:
        result = super().extract(document_bytes)
        self.last_result = result
        return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generated synthetic PDF smoke through the real local PaddleOCR engine"
    )
    parser.add_argument(
        "--manifest", type=Path, default=BACKEND / "local_ocr/model-manifest.v1.json"
    )
    parser.add_argument("--models-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    try:
        manifest = load_and_verify_manifest(args.manifest, args.models_root)
        binding = manifest_binding_sha256(manifest)
        engine = PaddleOcrEngine.from_local_models(args.manifest, args.models_root)
        pipeline = _CapturingLocalOcrPipeline(
            PyMuPdfDocumentBackend(), engine, preprocessor=OpenCvPreprocessor()
        )
        cases = generate_synthetic_smoke_cases(args.seed)
        header_matches = 0
        header_total = 0
        numeric_matches = 0
        numeric_total = 0
        review_matches = 0
        case_reports: list[dict[str, object]] = []
        for case in cases:
            provider = LocalOcrExtractionProvider(
                pipeline,
                BytesDocumentResolver({case.case_id: case.document_bytes}),
            )
            candidate = provider.extract(
                "123e4567-e89b-12d3-a456-426614174001", case.case_id
            )
            result = pipeline.last_result
            if result is None:
                raise LocalOcrError("LOCAL_OCR_INFERENCE_FAILED")
            selected_lines = _associated_candidate_lines(candidate)
            case_header_matches: dict[str, bool] = {}
            for field, expected in case.expected_header_fields:
                matched = _line_has_pair(selected_lines, field, expected)
                case_header_matches[field] = matched
                header_total += 1
                header_matches += matched
            case_numeric_matches: dict[str, bool] = {}
            for field, expected in case.expected_numeric_fields:
                matched = _line_has_pair(selected_lines, field, expected)
                case_numeric_matches[field] = matched
                numeric_total += 1
                numeric_matches += matched
            candidate_reasons = {
                reason for value in candidate.values for reason in value.reason_codes
            }
            review_exposed = (
                candidate.provider_name == "local-paddleocr"
                and candidate.review_required
                and all(value.review_required for value in candidate.values)
                and all(
                    "HUMAN_REVIEW_REQUIRED" in value.reason_codes
                    for value in candidate.values
                )
                and set(case.required_review_reasons) <= candidate_reasons
                and not set(case.forbidden_review_reasons) & candidate_reasons
            )
            review_matches += review_exposed
            report = result.sanitized_report(
                source_binding=case.case_id, model_binding=binding
            )
            case_reports.append(
                {
                    "case_id": case.case_id,
                    "degradations": list(case.degradations),
                    "header_field_matches": case_header_matches,
                    "numeric_field_matches": case_numeric_matches,
                    "report_sha256": report.report_sha256,
                    "review_exposed": review_exposed,
                }
            )
        metrics = SyntheticEngineeringMetrics(
            required_header_accuracy=Decimal(header_matches) / Decimal(header_total),
            numeric_accuracy=Decimal(numeric_matches) / Decimal(numeric_total),
            review_trigger_exposure=Decimal(review_matches) / Decimal(len(cases)),
        )
        if engine.initialization_network_attempt_count or engine.prediction_network_attempt_count:
            raise LocalOcrError("LOCAL_OCR_NETWORK_ACCESS_DENIED")
        payload: dict[str, object] = {
            "case_reports": case_reports,
            "engineering_gate_passed": metrics.engineering_gate_passed,
            "engine": manifest.engine,
            "engine_version": manifest.engine_version,
            "initialization_network_attempt_count": engine.initialization_network_attempt_count,
            "manifest_binding_sha256": binding,
            "numeric_accuracy": format(metrics.numeric_accuracy, ".4f"),
            "prediction_network_attempt_count": engine.prediction_network_attempt_count,
            "production_readiness_claim": False,
            "provider_name": "local-paddleocr",
            "required_header_accuracy": format(metrics.required_header_accuracy, ".4f"),
            "review_trigger_exposure": format(metrics.review_trigger_exposure, ".4f"),
            "runtime_version": manifest.runtime_version,
            "schema_version": "hyc.local-ocr-synthetic-smoke.v1",
            "seed": args.seed,
        }
        payload["aggregate_sha256"] = hashlib.sha256(_canonical_bytes(payload)).hexdigest()
    except LocalOcrError as error:
        print(json.dumps({"status": "BLOCKED", "error_code": error.code}, sort_keys=True))
        return 2
    encoded = _canonical_bytes(payload) + b"\n"
    if args.output:
        args.output.write_bytes(encoded)
    else:
        sys.stdout.buffer.write(encoded)
    return 0 if metrics.engineering_gate_passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
