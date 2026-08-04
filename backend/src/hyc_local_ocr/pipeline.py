from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol, cast

from hyc_local_ocr.contracts import (
    ImageVariant,
    LocalOcrLimits,
    LocalOcrResult,
    LocalReviewReason,
    OcrBoundingBox,
    OcrLine,
    OcrPageResult,
    OcrVariantResult,
    RecipeId,
    RenderedPage,
)
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.native_text import REQUIRED_NATIVE_MARKERS, native_text_is_sufficient

RECIPE_ORDER: tuple[RecipeId, ...] = (
    "original",
    "grayscale-clahe",
    "adaptive-threshold",
    "otsu-denoise-sharpen",
)
REASON_ORDER: tuple[LocalReviewReason, ...] = (
    "HUMAN_REVIEW_REQUIRED",
    "LOW_CONFIDENCE",
    "MISSING_REQUIRED",
    "NATIVE_OCR_DISAGREEMENT",
    "VARIANT_DISAGREEMENT",
    "NUMERIC_CONFLICT",
    "UNIT_CONFLICT",
    "LOT_CONFLICT",
    "TABLE_LAYOUT_REVIEW_REQUIRED",
)
REQUIRED_MARKERS = REQUIRED_NATIVE_MARKERS
_OCR_EXECUTION_LOCK = threading.Lock()
_IDENTITY_TRANSFORM = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0)


class DocumentBackend(Protocol):
    def load(
        self, document_bytes: bytes, limits: LocalOcrLimits, deadline: float
    ) -> tuple[RenderedPage, ...]: ...


class LocalOcrEngine(Protocol):
    def recognize(self, variant: ImageVariant, deadline: float) -> tuple[OcrLine, ...]: ...


class PagePreprocessor(Protocol):
    def variants(
        self, page: RenderedPage, limits: LocalOcrLimits
    ) -> tuple[ImageVariant, ...]: ...


class DeterministicPassThroughPreprocessor:
    """Pure contract default; the runtime injects the OpenCV implementation."""

    def variants(
        self, page: RenderedPage, limits: LocalOcrLimits
    ) -> tuple[ImageVariant, ...]:
        variants = tuple(
            ImageVariant(
                variant_id=recipe,
                recipe_id=recipe,
                image_png=page.image_png,
                width=page.width,
                height=page.height,
                source_width=page.width,
                source_height=page.height,
                transform_to_source=_IDENTITY_TRANSFORM,
            )
            for recipe in RECIPE_ORDER
        )
        return variants[: limits.max_variants_per_page]


def _normalized_lines(lines: Sequence[OcrLine]) -> tuple[str, ...]:
    return tuple(re.sub(r"\s+", " ", line.text.strip()).upper() for line in lines)


def _best_variant(variants: Sequence[OcrVariantResult]) -> OcrVariantResult:
    non_empty = [variant for variant in variants if variant.lines]
    if not non_empty:
        return variants[0]

    def score(variant: OcrVariantResult) -> tuple[Decimal, int, int]:
        confidence_sum = sum(
            (cast(Decimal, line.confidence) * Decimal(len(line.text)) for line in variant.lines),
            Decimal("0"),
        )
        return (
            confidence_sum,
            sum(len(line.text) for line in variant.lines),
            -variants.index(variant),
        )

    return max(non_empty, key=score)


def _transform_point(
    x: float,
    y: float,
    matrix: tuple[float, float, float, float, float, float, float, float, float],
) -> tuple[float, float]:
    denominator = matrix[6] * x + matrix[7] * y + matrix[8]
    if abs(denominator) < 1e-12:
        raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
    return (
        (matrix[0] * x + matrix[1] * y + matrix[2]) / denominator,
        (matrix[3] * x + matrix[4] * y + matrix[5]) / denominator,
    )


def _map_lines_to_source(
    lines: Sequence[OcrLine], variant: ImageVariant, page: RenderedPage
) -> tuple[OcrLine, ...]:
    mapped: list[tuple[OcrLine, OcrBoundingBox]] = []
    for line in lines:
        corners = (
            (line.bbox.left, line.bbox.top),
            (line.bbox.right, line.bbox.top),
            (line.bbox.right, line.bbox.bottom),
            (line.bbox.left, line.bbox.bottom),
        )
        transformed = tuple(
            _transform_point(float(x), float(y), variant.transform_to_source)
            for x, y in corners
        )
        left = max(0, min(page.width - 1, math.floor(min(point[0] for point in transformed))))
        top = max(0, min(page.height - 1, math.floor(min(point[1] for point in transformed))))
        right = max(
            left + 1,
            min(page.width, math.ceil(max(point[0] for point in transformed))),
        )
        bottom = max(
            top + 1,
            min(page.height, math.ceil(max(point[1] for point in transformed))),
        )
        mapped.append(
            (
                line,
                OcrBoundingBox(left=left, top=top, right=right, bottom=bottom),
            )
        )
    mapped.sort(key=lambda item: (item[1].top, item[1].left, item[0].reading_order))
    return tuple(
        OcrLine(
            text=line.text,
            confidence=cast(Decimal, line.confidence),
            bbox=bbox,
            reading_order=index,
        )
        for index, (line, bbox) in enumerate(mapped, start=1)
    )


def _review_reasons(
    page: RenderedPage,
    variants: Sequence[OcrVariantResult],
    selected: Sequence[OcrLine],
    limits: LocalOcrLimits,
) -> tuple[LocalReviewReason, ...]:
    reasons: set[LocalReviewReason] = {"HUMAN_REVIEW_REQUIRED"}
    if any(cast(Decimal, line.confidence) < limits.low_confidence_threshold for line in selected):
        reasons.add("LOW_CONFIDENCE")
    selected_text = "\n".join(line.text for line in selected).upper()
    if not all(marker in selected_text for marker in REQUIRED_MARKERS):
        reasons.add("MISSING_REQUIRED")
    non_empty_texts = {_normalized_lines(variant.lines) for variant in variants if variant.lines}
    if len(non_empty_texts) > 1:
        reasons.add("VARIANT_DISAGREEMENT")
        lot_values = {
            line
            for lines in non_empty_texts
            for line in lines
            if re.search(r"\bLOT\b", line)
        }
        if len(lot_values) > 1:
            reasons.add("LOT_CONFLICT")
        numeric_values = {
            tuple(re.findall(r"(?<![A-Z])[+-]?[0-9]+(?:\.[0-9]+)?", line))
            for lines in non_empty_texts
            for line in lines
            if re.search(r"[0-9]", line) and "LOT" not in line
        }
        if len(numeric_values) > 1:
            reasons.add("NUMERIC_CONFLICT")
        unit_values = {
            unit
            for lines in non_empty_texts
            for line in lines
            for unit in re.findall(r"(?:%|\b(?:PPM|MG/L|G/CM3|MM)\b)", line)
        }
        if len(unit_values) > 1:
            reasons.add("UNIT_CONFLICT")
    if page.native_text.strip() and _normalized_lines(page.native_lines) != _normalized_lines(
        selected
    ):
        reasons.add("NATIVE_OCR_DISAGREEMENT")
    if page.table_suspected:
        reasons.add("TABLE_LAYOUT_REVIEW_REQUIRED")
    return tuple(reason for reason in REASON_ORDER if reason in reasons)


class LocalOcrPipeline:
    def __init__(
        self,
        document_backend: DocumentBackend,
        engine: LocalOcrEngine,
        *,
        preprocessor: PagePreprocessor | None = None,
        limits: LocalOcrLimits | None = None,
    ) -> None:
        self._document_backend = document_backend
        self._engine = engine
        self._preprocessor = preprocessor or DeterministicPassThroughPreprocessor()
        self._limits = limits or LocalOcrLimits()

    def extract(self, document_bytes: bytes) -> LocalOcrResult:
        if not _OCR_EXECUTION_LOCK.acquire(blocking=False):
            raise LocalOcrError("LOCAL_OCR_CONCURRENCY_LIMIT_EXCEEDED")
        try:
            return self._extract_exclusive(document_bytes)
        finally:
            _OCR_EXECUTION_LOCK.release()

    def _extract_exclusive(self, document_bytes: bytes) -> LocalOcrResult:
        if not document_bytes:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        if len(document_bytes) > self._limits.max_file_bytes:
            raise LocalOcrError("LOCAL_OCR_FILE_TOO_LARGE")
        deadline = time.monotonic() + self._limits.timeout_seconds
        pages = self._document_backend.load(document_bytes, self._limits, deadline)
        if not pages or len(pages) > self._limits.max_pages:
            raise LocalOcrError("LOCAL_OCR_PAGE_LIMIT_EXCEEDED")
        if sum(page.width * page.height for page in pages) > self._limits.max_total_pixels:
            raise LocalOcrError("LOCAL_OCR_PIXEL_LIMIT_EXCEEDED")

        results: list[OcrPageResult] = []
        for page in pages:
            if time.monotonic() >= deadline:
                raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")
            if native_text_is_sufficient(page.native_text, self._limits):
                native = OcrVariantResult(
                    variant_id="native-text",
                    recipe_id="native-text",
                    lines=page.native_lines,
                    width=page.width,
                    height=page.height,
                    transform_to_source=_IDENTITY_TRANSFORM,
                )
                results.append(
                    OcrPageResult(
                        page_number=page.page_number,
                        route="NATIVE_TEXT",
                        rendered_dpi=page.rendered_dpi,
                        source_width=page.width,
                        source_height=page.height,
                        variants=(native,),
                        selected_lines=page.native_lines,
                        selected_variant_id=native.variant_id,
                        selected_recipe_id=native.recipe_id,
                        selected_rotation_degrees=0,
                        selected_deskew_millidegrees=0,
                        selected_deskew_status="NOT_NEEDED",
                        selected_perspective_corrected=False,
                        reason_codes=_review_reasons(
                            page, (native,), page.native_lines, self._limits
                        ),
                    )
                )
                continue

            if not page.image_png:
                raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
            image_variants = self._preprocessor.variants(page, self._limits)
            if not image_variants or len(image_variants) > self._limits.max_variants_per_page:
                raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
            variant_results: list[OcrVariantResult] = []
            for variant in image_variants:
                if time.monotonic() >= deadline:
                    raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")
                lines = _map_lines_to_source(
                    self._engine.recognize(variant, deadline), variant, page
                )
                variant_results.append(
                    OcrVariantResult(
                        variant_id=variant.variant_id,
                        recipe_id=variant.recipe_id,
                        lines=lines,
                        width=variant.width,
                        height=variant.height,
                        transform_to_source=variant.transform_to_source,
                        rotation_degrees=variant.rotation_degrees,
                        deskew_millidegrees=variant.deskew_millidegrees,
                        deskew_status=variant.deskew_status,
                        perspective_corrected=variant.perspective_corrected,
                    )
                )
            best = _best_variant(variant_results)
            results.append(
                OcrPageResult(
                    page_number=page.page_number,
                    route="LOCAL_OCR",
                    rendered_dpi=page.rendered_dpi,
                    source_width=page.width,
                    source_height=page.height,
                    variants=tuple(variant_results),
                    selected_lines=best.lines,
                    selected_variant_id=best.variant_id,
                    selected_recipe_id=best.recipe_id,
                    selected_rotation_degrees=best.rotation_degrees,
                    selected_deskew_millidegrees=best.deskew_millidegrees,
                    selected_deskew_status=best.deskew_status,
                    selected_perspective_corrected=best.perspective_corrected,
                    reason_codes=_review_reasons(
                        page, variant_results, best.lines, self._limits
                    ),
                )
            )
        selected_line_count = sum(len(result.selected_lines) for result in results)
        if selected_line_count > self._limits.max_lines_per_document:
            raise LocalOcrError("LOCAL_OCR_LINE_LIMIT_EXCEEDED")
        return LocalOcrResult(
            pages=tuple(results), input_sha256=hashlib.sha256(document_bytes).hexdigest()
        )
