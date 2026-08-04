from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest

from hyc_local_ocr.contracts import (
    ImageVariant,
    LocalOcrLimits,
    OcrBoundingBox,
    OcrLine,
    RenderedPage,
)
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pipeline import LocalOcrPipeline
from hyc_local_ocr.testing import FakeDocumentBackend, RecordingOcrEngine


def _line(text: str, confidence: str = "0.99", reading_order: int = 1) -> OcrLine:
    return OcrLine(
        text=text,
        confidence=confidence,
        bbox=OcrBoundingBox(left=10, top=10, right=500, bottom=60),
        reading_order=reading_order,
    )


def test_valid_native_text_is_preferred_and_engine_is_not_called() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=300,
        native_text=(
            "SYNTHETIC COA\nSUPPLIER: TEST LAB\nPRODUCT: GENERATED MATERIAL\n"
            "LOT: SYN-20260803-001\nMOISTURE % 1.25\nASSAY % 99.50"
        ),
        native_lines=(
            _line("SUPPLIER: TEST LAB"),
            _line("PRODUCT: GENERATED MATERIAL", reading_order=2),
            _line("LOT: SYN-20260803-001", reading_order=3),
            _line("MOISTURE % 1.25", reading_order=4),
            _line("ASSAY % 99.50", reading_order=5),
        ),
        image_png=b"unused-native-page",
        table_suspected=False,
    )
    engine = RecordingOcrEngine(results={})
    pipeline = LocalOcrPipeline(FakeDocumentBackend((page,)), engine)

    result = pipeline.extract(b"%PDF-synthetic-native")

    assert engine.calls == []
    assert result.pages[0].route == "NATIVE_TEXT"
    assert result.review_required is True
    assert result.pages[0].reason_codes == ("HUMAN_REVIEW_REQUIRED",)


def test_native_text_missing_lot_receives_stable_missing_reason_without_ocr() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=300,
        native_text=(
            "SYNTHETIC COA SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL "
            "MOISTURE 1.25 ASSAY 99.50"
        ),
        native_lines=(
            _line("SUPPLIER TEST LAB"),
            _line("PRODUCT GENERATED MATERIAL", reading_order=2),
            _line("MOISTURE 1.25 ASSAY 99.50", reading_order=3),
        ),
        image_png=b"",
        table_suspected=False,
    )
    engine = RecordingOcrEngine(results={})

    result = LocalOcrPipeline(FakeDocumentBackend((page,)), engine).extract(b"native-missing")

    assert result.pages[0].route == "NATIVE_TEXT"
    assert result.pages[0].reason_codes == (
        "HUMAN_REVIEW_REQUIRED",
        "MISSING_REQUIRED",
    )
    assert engine.calls == []


def test_native_text_low_confidence_receives_stable_low_confidence_reason() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=300,
        native_text=(
            "SYNTHETIC COA SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL "
            "LOT SYN-001 MOISTURE 1.25 ASSAY 99.50"
        ),
        native_lines=(
            _line(
                "SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001",
                confidence="0.55",
            ),
        ),
        image_png=b"",
        table_suspected=False,
    )

    result = LocalOcrPipeline(
        FakeDocumentBackend((page,)), RecordingOcrEngine(results={})
    ).extract(b"native-low-confidence")

    assert result.pages[0].route == "NATIVE_TEXT"
    assert result.pages[0].reason_codes == (
        "HUMAN_REVIEW_REQUIRED",
        "LOW_CONFIDENCE",
    )


def test_native_table_signal_receives_table_review_reason_without_ocr() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=300,
        native_text=(
            "SYNTHETIC COA SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL "
            "LOT SYN-001 ITEM RESULT UNIT ASSAY 99.50 PERCENT"
        ),
        native_lines=(
            _line("SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001"),
            _line("ITEM RESULT UNIT", reading_order=2),
            _line("ASSAY 99.50 PERCENT", reading_order=3),
        ),
        image_png=b"",
        table_suspected=True,
    )
    engine = RecordingOcrEngine(results={})

    result = LocalOcrPipeline(FakeDocumentBackend((page,)), engine).extract(b"native-table")

    assert result.pages[0].route == "NATIVE_TEXT"
    assert "TABLE_LAYOUT_REVIEW_REQUIRED" in result.pages[0].reason_codes
    assert engine.calls == []


def test_scanned_page_preserves_variants_and_exposes_disagreement() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=400,
        native_text="",
        native_lines=(),
        image_png=b"scan",
        table_suspected=False,
    )
    engine = RecordingOcrEngine(
        results={
            "original": (_line("LOT: SYN-001", "0.93"), _line("ASSAY % 99.50", "0.99", 2)),
            "grayscale-clahe": (
                _line("LOT: SYN-OO1", "0.91"),
                _line("ASSAY % 99.50", "0.99", 2),
            ),
            "adaptive-threshold": (
                _line("LOT: SYN-001", "0.94"),
                _line("ASSAY % 99.80", "0.90", 2),
            ),
            "otsu-denoise-sharpen": (
                _line("LOT: SYN-001", "0.96"),
                _line("ASSAY % 99.50", "0.98", 2),
            ),
        }
    )
    pipeline = LocalOcrPipeline(FakeDocumentBackend((page,)), engine)

    result = pipeline.extract(b"%PDF-synthetic-scan")

    assert result.pages[0].route == "LOCAL_OCR"
    assert [variant.recipe_id for variant in result.pages[0].variants] == [
        "original",
        "grayscale-clahe",
        "adaptive-threshold",
        "otsu-denoise-sharpen",
    ]
    assert "VARIANT_DISAGREEMENT" in result.pages[0].reason_codes
    assert "LOT_CONFLICT" in result.pages[0].reason_codes
    assert "NUMERIC_CONFLICT" in result.pages[0].reason_codes
    assert result.review_required is True


def test_table_page_fails_closed_when_structure_engine_is_deferred() -> None:
    page = RenderedPage(
        page_number=1,
        width=2480,
        height=3508,
        rendered_dpi=300,
        native_text="",
        native_lines=(),
        image_png=b"table-scan",
        table_suspected=True,
    )
    engine = RecordingOcrEngine(results={"original": (_line("ITEM VALUE"),)})

    result = LocalOcrPipeline(FakeDocumentBackend((page,)), engine).extract(b"table")

    assert "TABLE_LAYOUT_REVIEW_REQUIRED" in result.pages[0].reason_codes
    assert result.review_required is True


@pytest.mark.parametrize(
    ("backend", "payload", "expected_code"),
    [
        (FakeDocumentBackend((), corrupt=True), b"broken", "LOCAL_OCR_PDF_CORRUPT"),
        (FakeDocumentBackend(()), b"x" * 33, "LOCAL_OCR_FILE_TOO_LARGE"),
    ],
)
def test_invalid_or_oversized_inputs_fail_closed_before_inference(
    backend: FakeDocumentBackend, payload: bytes, expected_code: str
) -> None:
    limits = replace(LocalOcrLimits(), max_file_bytes=32)
    engine = RecordingOcrEngine(results={})

    with pytest.raises(LocalOcrError) as caught:
        LocalOcrPipeline(backend, engine, limits=limits).extract(payload)

    assert caught.value.code == expected_code
    assert engine.calls == []


def test_selected_line_limit_fails_closed_without_truncation() -> None:
    lines = tuple(_line(f"generated line {index}", reading_order=index) for index in range(1, 502))
    page = RenderedPage(
        page_number=1,
        width=1000,
        height=1000,
        rendered_dpi=300,
        native_text="SYNTHETIC COA SUPPLIER PRODUCT LOT SYN-001 " + "x" * 64,
        native_lines=lines,
        image_png=b"",
        table_suspected=False,
    )
    engine = RecordingOcrEngine(results={})

    with pytest.raises(LocalOcrError, match="LOCAL_OCR_LINE_LIMIT_EXCEEDED"):
        LocalOcrPipeline(FakeDocumentBackend((page,)), engine).extract(b"generated-line-limit")

    assert engine.calls == []


def test_sanitized_report_digest_is_deterministic_and_contains_no_text_or_path(
    tmp_path: Path,
) -> None:
    page = RenderedPage(
        page_number=1,
        width=1000,
        height=1000,
        rendered_dpi=300,
        native_text="",
        native_lines=(),
        image_png=b"scan",
        table_suspected=False,
    )
    secret_text = "LOT: DO-NOT-LEAK-001"
    engine = RecordingOcrEngine(results={"original": (_line(secret_text),)})
    pipeline = LocalOcrPipeline(FakeDocumentBackend((page,)), engine)

    first = pipeline.extract(b"same-input").sanitized_report(
        source_binding="opaque-source", model_binding="manifest-digest"
    )
    second = pipeline.extract(b"same-input").sanitized_report(
        source_binding="opaque-source", model_binding="manifest-digest"
    )
    encoded = first.canonical_json()

    assert first.report_sha256 == second.report_sha256
    assert secret_text not in encoded
    assert str(tmp_path) not in encoded
    assert "image_png" not in encoded


class _RotatedWinnerPreprocessor:
    def variants(
        self, page: RenderedPage, limits: LocalOcrLimits
    ) -> tuple[ImageVariant, ...]:
        del limits
        return (
            ImageVariant(
                variant_id="original-r180",
                recipe_id="original",
                image_png=page.image_png,
                width=page.width,
                height=page.height,
                source_width=page.width,
                source_height=page.height,
                transform_to_source=(
                    -1.0,
                    0.0,
                    float(page.width),
                    0.0,
                    -1.0,
                    float(page.height),
                    0.0,
                    0.0,
                    1.0,
                ),
                rotation_degrees=180,
            ),
        )


def test_rotated_winner_preserves_identity_and_maps_bbox_to_source_frame() -> None:
    page = RenderedPage(
        page_number=1,
        width=100,
        height=200,
        rendered_dpi=300,
        native_text="",
        native_lines=(),
        image_png=b"scan",
        table_suspected=False,
    )
    rotated_line = OcrLine(
        text="LOT: SYN-001",
        confidence="0.99",
        bbox=OcrBoundingBox(left=10, top=20, right=30, bottom=40),
        reading_order=1,
    )
    pipeline = LocalOcrPipeline(
        FakeDocumentBackend((page,)),
        RecordingOcrEngine({"original-r180": (rotated_line,)}),
        preprocessor=_RotatedWinnerPreprocessor(),
    )

    result = pipeline.extract(b"rotated")
    selected = result.pages[0]

    assert selected.selected_variant_id == "original-r180"
    assert selected.selected_recipe_id == "original"
    assert selected.selected_rotation_degrees == 180
    assert selected.selected_lines[0].bbox == OcrBoundingBox(
        left=70, top=160, right=90, bottom=180
    )
    report = result.sanitized_report(
        source_binding="opaque", model_binding="manifest"
    ).canonical_json()
    assert '"selected_variant_id":"original-r180"' in report
    assert '"selected_rotation_degrees":180' in report


class _BlockingBackend:
    def __init__(self, page: RenderedPage, entered: Event, release: Event) -> None:
        self._page = page
        self._entered = entered
        self._release = release

    def load(
        self, document_bytes: bytes, limits: LocalOcrLimits, deadline: float
    ) -> tuple[RenderedPage, ...]:
        del document_bytes, limits, deadline
        self._entered.set()
        assert self._release.wait(timeout=5)
        return (self._page,)


def test_concurrency_one_rejects_overlapping_attempts_across_pipelines() -> None:
    page = RenderedPage(
        page_number=1,
        width=1000,
        height=1000,
        rendered_dpi=300,
        native_text=(
            "SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001 "
            "MOISTURE 1.25 ASSAY 99.50"
        ),
        native_lines=(_line("SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001"),),
        image_png=b"",
        table_suspected=False,
    )
    entered = Event()
    release = Event()
    first = LocalOcrPipeline(
        _BlockingBackend(page, entered, release), RecordingOcrEngine({})
    )
    second = LocalOcrPipeline(FakeDocumentBackend((page,)), RecordingOcrEngine({}))

    with ThreadPoolExecutor(max_workers=2) as executor:
        running = executor.submit(first.extract, b"first")
        assert entered.wait(timeout=5)
        with pytest.raises(LocalOcrError) as caught:
            second.extract(b"second")
        release.set()
        assert running.result(timeout=5).pages[0].route == "NATIVE_TEXT"

    assert caught.value.code == "LOCAL_OCR_CONCURRENCY_LIMIT_EXCEEDED"


def test_invalid_dpi_and_concurrency_limits_are_rejected() -> None:
    with pytest.raises(ValueError):
        replace(LocalOcrLimits(), render_dpi=401)
    with pytest.raises(ValueError):
        replace(LocalOcrLimits(), render_dpi=400, oversample_dpi=399)
    with pytest.raises(ValueError):
        replace(LocalOcrLimits(), max_concurrency=2)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(LocalOcrLimits(), max_lines_per_document=0)
