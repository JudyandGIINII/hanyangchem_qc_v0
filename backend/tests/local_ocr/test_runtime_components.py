from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from hyc_local_ocr.contracts import LocalOcrLimits, RenderedPage
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pdf_backend import (
    PyMuPdfDocumentBackend,
    _native_table_suspected,
    _select_dpi,
)
from hyc_local_ocr.pipeline import LocalOcrPipeline
from hyc_local_ocr.preprocess import OpenCvPreprocessor, _deskew
from hyc_local_ocr.synthetic import (
    _apply_degradations,
    _base_image,
    generate_mixed_native_scanned_pdf,
    generate_synthetic_smoke_cases,
)
from hyc_local_ocr.testing import RecordingOcrEngine

pytestmark = pytest.mark.local_ocr_runtime


def test_generated_pdf_bytes_are_seeded_and_render_at_bounded_400_dpi() -> None:
    first = generate_synthetic_smoke_cases(seed=20260803)
    second = generate_synthetic_smoke_cases(seed=20260803)

    assert first == second
    page = PyMuPdfDocumentBackend().load(first[0].document_bytes, LocalOcrLimits())[0]
    assert page.rendered_dpi == 400
    assert page.width * page.height <= LocalOcrLimits().max_total_pixels
    variants = OpenCvPreprocessor().variants(page, LocalOcrLimits())
    assert variants[0].variant_id == "original-r0"
    assert variants[0].image_png == page.image_png
    assert {variant.rotation_degrees for variant in variants} >= {0, 90, 180, 270}
    assert {variant.recipe_id for variant in variants} == {
        "original",
        "grayscale-clahe",
        "adaptive-threshold",
        "otsu-denoise-sharpen",
    }


def test_mixed_pdf_routes_native_and_scanned_pages_independently() -> None:
    pages = PyMuPdfDocumentBackend().load(
        generate_mixed_native_scanned_pdf(), LocalOcrLimits()
    )

    assert len(pages) == 2
    assert pages[0].native_text.startswith("SYNTHETIC COA")
    assert pages[0].image_png == b""
    assert pages[1].native_text == ""
    assert pages[1].image_png.startswith(b"\x89PNG")
    assert pages[1].rendered_dpi == 400


def test_table_degradation_is_detected_for_fail_closed_review() -> None:
    table_case = generate_synthetic_smoke_cases()[-1]
    page = PyMuPdfDocumentBackend().load(table_case.document_bytes, LocalOcrLimits())[0]
    assert page.table_suspected is True


def test_corrupt_pdf_fails_with_stable_code_and_no_path(tmp_path: Path) -> None:
    with pytest.raises(LocalOcrError) as caught:
        PyMuPdfDocumentBackend().load(b"%PDF-corrupt", LocalOcrLimits())

    assert caught.value.code == "LOCAL_OCR_PDF_CORRUPT"
    assert str(tmp_path) not in str(caught.value)


def _single_page_pdf(text: str) -> bytes:
    import fitz  # type: ignore[import-untyped]

    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_textbox(fitz.Rect(40, 40, 555, 700), text, fontsize=16)
        return bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    finally:
        document.close()


def _native_table_pdf() -> bytes:
    import fitz  # type: ignore[import-untyped]

    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text(
            (40, 45),
            "SYNTHETIC COA SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001",
            fontsize=11,
        )
        for y_position, row in (
            (110, "ITEM          RESULT        UNIT"),
            (140, "ASSAY         99.50         PERCENT"),
            (170, "MOISTURE      1.25          PERCENT"),
        ):
            page.insert_text((50, y_position), row, fontname="courier", fontsize=12)
        return bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    finally:
        document.close()


def _native_aligned_prose_pdf() -> bytes:
    """Ordinary left-aligned prose rows: three words each, no wide column gutters."""

    import fitz  # type: ignore[import-untyped]

    document = fitz.open()
    try:
        page = document.new_page(width=595, height=842)
        page.insert_text(
            (40, 45),
            "SYNTHETIC COA SUPPLIER TEST LAB PRODUCT GENERATED MATERIAL LOT SYN-001",
            fontsize=11,
        )
        for y_position, line in (
            (110, "SUPPLIER OPERATOR DOCUMENT"),
            (140, "MATERIAL FACILITY LOCATION"),
            (170, "SHIPMENT RECEIVER APPROVAL"),
        ):
            page.insert_text((50, y_position), line, fontname="courier", fontsize=12)
        return bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    finally:
        document.close()


def _native_words(document_bytes: bytes) -> tuple[tuple[object, ...], ...]:
    import fitz  # type: ignore[import-untyped]

    document = fitz.open(stream=document_bytes, filetype="pdf")
    try:
        return tuple(tuple(word) for word in document[0].get_text("words", sort=True))
    finally:
        document.close()


def _three_word_row_gaps(words: tuple[tuple[object, ...], ...]) -> tuple[float, ...]:
    grouped: dict[tuple[int, int], list[tuple[object, ...]]] = {}
    for word in words:
        grouped.setdefault((int(word[5]), int(word[6])), []).append(word)
    gaps: list[float] = []
    for row in grouped.values():
        sorted_row = sorted(row, key=lambda word: float(word[0]))
        if len(sorted_row) != 3:
            continue
        for index in range(1, len(sorted_row)):
            gaps.append(float(sorted_row[index][0]) - float(sorted_row[index - 1][2]))
    return tuple(gaps)


def test_native_table_signal_requires_wide_cell_gutters() -> None:
    prose_words = _native_words(_native_aligned_prose_pdf())
    table_words = _native_words(_native_table_pdf())

    assert _three_word_row_gaps(prose_words)
    assert max(_three_word_row_gaps(prose_words)) < 8.0
    assert _native_table_suspected(prose_words) is False
    assert min(_three_word_row_gaps(table_words)) >= 12.0
    assert _native_table_suspected(table_words) is True


def test_real_native_backend_has_no_low_confidence_signal_for_the_evaluator() -> None:
    result = LocalOcrPipeline(PyMuPdfDocumentBackend(), RecordingOcrEngine(results={})).extract(
        generate_mixed_native_scanned_pdf()
    )

    assert result.pages[0].route == "NATIVE_TEXT"
    assert {line.confidence for line in result.pages[0].selected_lines} == {Decimal("1.00")}
    assert "LOW_CONFIDENCE" not in result.pages[0].reason_codes


def test_shared_native_predicate_renders_and_ocrs_punctuation_heavy_layer() -> None:
    payload = _single_page_pdf(
        "SUPPLIER: ---------------- PRODUCT: ================ LOT: ________________"
    )
    engine = RecordingOcrEngine(results={"original": ()})

    result = LocalOcrPipeline(PyMuPdfDocumentBackend(), engine).extract(payload)

    assert result.pages[0].route == "LOCAL_OCR"
    assert engine.calls


def test_shared_native_predicate_never_routes_sufficient_empty_image_to_ocr() -> None:
    payload = _single_page_pdf(
        "SYNTHETIC COA SUPPLIER: TEST LAB PRODUCT: GENERATED MATERIAL "
        "LOT: SYN-NATIVE-001 MOISTURE 1.25 ASSAY 99.50"
    )
    engine = RecordingOcrEngine(results={})

    result = LocalOcrPipeline(PyMuPdfDocumentBackend(), engine).extract(payload)

    assert result.pages[0].route == "NATIVE_TEXT"
    assert result.pages[0].selected_lines
    assert engine.calls == []


def test_native_layout_table_signal_is_exposed_without_rendering_or_ocr() -> None:
    engine = RecordingOcrEngine(results={})

    result = LocalOcrPipeline(PyMuPdfDocumentBackend(), engine).extract(_native_table_pdf())

    assert result.pages[0].route == "NATIVE_TEXT"
    assert "TABLE_LAYOUT_REVIEW_REQUIRED" in result.pages[0].reason_codes
    assert engine.calls == []


def test_conservative_perspective_correction_preserves_valid_source_transform() -> None:
    import cv2
    import numpy

    image = numpy.full((600, 800, 3), 255, dtype=numpy.uint8)
    polygon = numpy.array([[70, 35], [730, 80], [680, 565], [110, 520]], dtype=numpy.int32)
    cv2.fillConvexPoly(image, polygon, (245, 245, 245))
    cv2.polylines(image, [polygon], True, (0, 0, 0), 10)
    for offset in range(120, 481, 70):
        cv2.line(image, (140, offset), (650, offset + 15), (0, 0, 0), 5)
    encoded_ok, encoded = cv2.imencode(".png", image)
    assert encoded_ok
    page = RenderedPage(
        page_number=1,
        width=800,
        height=600,
        rendered_dpi=300,
        native_text="",
        native_lines=(),
        image_png=bytes(encoded.tobytes()),
        table_suspected=False,
    )

    enhanced = OpenCvPreprocessor().variants(page, LocalOcrLimits())[4:]

    assert enhanced
    assert all(variant.perspective_corrected is True for variant in enhanced)
    for variant in enhanced:
        transform = numpy.asarray(variant.transform_to_source).reshape(3, 3)
        assert numpy.isfinite(transform).all()
        assert abs(float(numpy.linalg.det(transform))) > 1e-9


@pytest.mark.parametrize(("source_angle", "correction_sign"), [(3.0, -1), (-3.0, 1)])
def test_opencv_410_deskew_corrects_positive_and_negative_angles(
    source_angle: float, correction_sign: int
) -> None:
    import cv2
    import numpy

    image = numpy.full((500, 900, 3), 255, dtype=numpy.uint8)
    for y in range(100, 401, 60):
        cv2.rectangle(image, (100, y), (800, y + 18), (0, 0, 0), -1)
    matrix = cv2.getRotationMatrix2D((450, 250), source_angle, 1.0)
    skewed = cv2.warpAffine(
        image, matrix, (900, 500), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )

    _, correction, status, _ = _deskew(skewed, cv2, numpy)

    assert status == "APPLIED"
    assert correction * correction_sign > 0
    assert abs(abs(correction) - 3000) <= 250


def test_synthetic_skew_uses_white_three_channel_border() -> None:
    import numpy

    skewed = _apply_degradations(_base_image(), ("skew-positive",), 20260803)
    array = numpy.asarray(skewed)

    assert tuple(int(value) for value in array[0, 0]) == (255, 255, 255)
    assert tuple(int(value) for value in array[-1, -1]) == (255, 255, 255)


class _FakeRect:
    width = 595.0
    height = 842.0


class _FakeImagePage:
    rect = _FakeRect()

    def __init__(self, images: list[tuple[int, int, int, int]]) -> None:
        self._images = images

    def get_images(self, *, full: bool) -> list[tuple[int, int, int, int]]:
        assert full is True
        return self._images


def test_dominant_page_image_ignores_tiny_logo_for_dpi_selection() -> None:
    page = _FakeImagePage([(1, 0, 2480, 3508), (2, 0, 64, 64)])

    assert _select_dpi(page, LocalOcrLimits()) == 300


def test_low_resolution_dominant_page_image_selects_bounded_400_dpi() -> None:
    page = _FakeImagePage([(1, 0, 1200, 900), (2, 0, 64, 64)])

    assert _select_dpi(page, LocalOcrLimits()) == 400


def test_document_load_checks_deadline_before_page_render(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = _single_page_pdf("generated synthetic")
    moments = iter((0.0, 2.0))
    monkeypatch.setattr(
        "hyc_local_ocr.pdf_backend.time.monotonic", lambda: next(moments, 2.0)
    )

    with pytest.raises(LocalOcrError) as caught:
        PyMuPdfDocumentBackend().load(payload, LocalOcrLimits(), deadline=1.0)

    assert caught.value.code == "LOCAL_OCR_TIMEOUT_EXCEEDED"


def test_page_operation_failure_maps_to_stable_corrupt_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenDocument:
        needs_pass = False
        page_count = 1

        def load_page(self, page_number: int) -> object:
            del page_number
            raise RuntimeError("non-sensitive synthetic failure")

        def close(self) -> None:
            return None

    class FakeFitz:
        csRGB = object()

        @staticmethod
        def open(*, stream: bytes, filetype: str) -> BrokenDocument:
            del stream, filetype
            return BrokenDocument()

    monkeypatch.setattr(
        "hyc_local_ocr.pdf_backend._runtime_modules",
        lambda: (FakeFitz, object(), object()),
    )

    with pytest.raises(LocalOcrError) as caught:
        PyMuPdfDocumentBackend().load(b"%PDF-synthetic", LocalOcrLimits())

    assert caught.value.code == "LOCAL_OCR_PDF_CORRUPT"
