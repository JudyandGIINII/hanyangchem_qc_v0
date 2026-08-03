from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal
from typing import Any

from hyc_local_ocr.contracts import (
    LocalOcrLimits,
    OcrBoundingBox,
    OcrLine,
    RenderedPage,
)
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.native_text import native_text_is_sufficient


def _runtime_modules() -> tuple[Any, Any, Any]:
    try:
        import cv2
        import fitz  # type: ignore[import-untyped]
        import numpy
    except ImportError as error:
        raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
    return fitz, cv2, numpy


def _native_lines(page: Any, dpi: int) -> tuple[OcrLine, ...]:
    scale = Decimal(dpi) / Decimal(72)
    grouped: dict[tuple[int, int], list[tuple[float, float, float, float, str, int]]] = (
        defaultdict(list)
    )
    for word in page.get_text("words", sort=True):
        x0, y0, x1, y1, text, block_no, line_no, word_no = word[:8]
        grouped[(int(block_no), int(line_no))].append(
            (float(x0), float(y0), float(x1), float(y1), str(text), int(word_no))
        )
    lines: list[OcrLine] = []
    for reading_order, key in enumerate(sorted(grouped), start=1):
        words = sorted(grouped[key], key=lambda item: item[5])
        text = " ".join(item[4] for item in words).strip()
        if not text:
            continue
        left = max(0, int(Decimal(str(min(item[0] for item in words))) * scale))
        top = max(0, int(Decimal(str(min(item[1] for item in words))) * scale))
        right = max(left + 1, int(Decimal(str(max(item[2] for item in words))) * scale))
        bottom = max(top + 1, int(Decimal(str(max(item[3] for item in words))) * scale))
        lines.append(
            OcrLine(
                text=text,
                confidence=Decimal("1.00"),
                bbox=OcrBoundingBox(left=left, top=top, right=right, bottom=bottom),
                reading_order=reading_order,
            )
        )
    return tuple(lines)


def _select_dpi(page: Any, limits: LocalOcrLimits) -> int:
    page_width_inches = float(page.rect.width) / 72
    page_height_inches = float(page.rect.height) / 72
    required_width = page_width_inches * 200
    required_height = page_height_inches * 200
    images = page.get_images(full=True)
    if not images:
        return limits.render_dpi
    dominant = max(images, key=lambda image: float(image[2]) * float(image[3]))
    if float(dominant[2]) < required_width or float(dominant[3]) < required_height:
        return limits.oversample_dpi
    return limits.render_dpi


def _native_table_suspected(page: Any) -> bool:
    """Conservatively detect three-by-three aligned native-text table geometry."""

    grouped: dict[tuple[int, int], list[float]] = defaultdict(list)
    for word in page.get_text("words", sort=True):
        x0, _, _, _, text, block_no, line_no = word[:7]
        if str(text).strip():
            grouped[(int(block_no), int(line_no))].append(float(x0))
    rows = [tuple(sorted(positions)) for positions in grouped.values() if len(positions) >= 3]
    if len(rows) < 3:
        return False

    clusters: list[tuple[float, set[int]]] = []
    for row_index, positions in enumerate(rows):
        for position in positions:
            matching = next(
                (
                    index
                    for index, (center, _) in enumerate(clusters)
                    if abs(position - center) <= 12.0
                ),
                None,
            )
            if matching is None:
                clusters.append((position, {row_index}))
                continue
            center, row_indexes = clusters[matching]
            row_indexes.add(row_index)
            clusters[matching] = (center, row_indexes)
    return sum(len(row_indexes) >= 3 for _, row_indexes in clusters) >= 3


def _check_deadline(deadline: float) -> None:
    if time.monotonic() >= deadline:
        raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")


def _table_suspected(image_png: bytes, cv2: Any, numpy: Any) -> bool:
    image = cv2.imdecode(numpy.frombuffer(image_png, dtype=numpy.uint8), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return False
    edges = cv2.Canny(image, 60, 180)
    lines = cv2.HoughLinesP(
        edges,
        1,
        numpy.pi / 180,
        threshold=120,
        minLineLength=max(80, min(image.shape[:2]) // 5),
        maxLineGap=8,
    )
    if lines is None:
        return False
    horizontal = 0
    vertical = 0
    for raw in lines[:100]:
        x1, y1, x2, y2 = (int(value) for value in raw[0])
        horizontal += abs(y2 - y1) <= 4 and abs(x2 - x1) >= 80
        vertical += abs(x2 - x1) <= 4 and abs(y2 - y1) >= 80
    return horizontal >= 3 and vertical >= 3


class PyMuPdfDocumentBackend:
    """Read-only PDF inspection and bounded 300/400 DPI rendering."""

    def load(
        self, document_bytes: bytes, limits: LocalOcrLimits, deadline: float = float("inf")
    ) -> tuple[RenderedPage, ...]:
        if not document_bytes.startswith(b"%PDF-"):
            raise LocalOcrError("LOCAL_OCR_UNSUPPORTED_MEDIA_TYPE")
        _check_deadline(deadline)
        fitz, cv2, numpy = _runtime_modules()
        try:
            document = fitz.open(stream=document_bytes, filetype="pdf")
        except Exception as error:
            raise LocalOcrError("LOCAL_OCR_PDF_CORRUPT") from error
        try:
            if document.needs_pass:
                raise LocalOcrError("LOCAL_OCR_PDF_ENCRYPTED")
            if document.page_count < 1 or document.page_count > limits.max_pages:
                raise LocalOcrError("LOCAL_OCR_PAGE_LIMIT_EXCEEDED")

            plans: list[tuple[Any, str, tuple[OcrLine, ...], int, int, int]] = []
            total_pixels = 0
            for page_number in range(document.page_count):
                _check_deadline(deadline)
                try:
                    page = document.load_page(page_number)
                    text = str(page.get_text("text", sort=True))
                    dpi = _select_dpi(page, limits)
                    width = max(1, round(float(page.rect.width) * dpi / 72))
                    height = max(1, round(float(page.rect.height) * dpi / 72))
                    native_lines = _native_lines(page, dpi)
                except LocalOcrError:
                    raise
                except Exception as error:
                    raise LocalOcrError("LOCAL_OCR_PDF_CORRUPT") from error
                total_pixels += width * height
                if total_pixels > limits.max_total_pixels:
                    raise LocalOcrError("LOCAL_OCR_PIXEL_LIMIT_EXCEEDED")
                plans.append((page, text, native_lines, dpi, width, height))

            rendered: list[RenderedPage] = []
            for page_number, (page, text, lines, dpi, width, height) in enumerate(plans, start=1):
                _check_deadline(deadline)
                image_png = b""
                table = False
                if native_text_is_sufficient(text, limits):
                    try:
                        table = _native_table_suspected(page)
                    except Exception as error:
                        raise LocalOcrError("LOCAL_OCR_PDF_CORRUPT") from error
                    _check_deadline(deadline)
                else:
                    try:
                        pixmap = page.get_pixmap(dpi=dpi, alpha=False, colorspace=fitz.csRGB)
                        image_png = bytes(pixmap.tobytes("png"))
                    except Exception as error:
                        raise LocalOcrError("LOCAL_OCR_PDF_CORRUPT") from error
                    _check_deadline(deadline)
                    table = _table_suspected(image_png, cv2, numpy)
                    _check_deadline(deadline)
                rendered.append(
                    RenderedPage(
                        page_number=page_number,
                        width=width,
                        height=height,
                        rendered_dpi=dpi,
                        native_text=text,
                        native_lines=lines,
                        image_png=image_png,
                        table_suspected=table,
                    )
                )
            return tuple(rendered)
        finally:
            document.close()
