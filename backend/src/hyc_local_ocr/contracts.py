from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

type RecipeId = Literal[
    "native-text",
    "original",
    "grayscale-clahe",
    "adaptive-threshold",
    "otsu-denoise-sharpen",
]
type PageRoute = Literal["NATIVE_TEXT", "LOCAL_OCR"]
type DeskewStatus = Literal["NOT_NEEDED", "APPLIED", "OUT_OF_BOUNDS"]
type LocalReviewReason = Literal[
    "HUMAN_REVIEW_REQUIRED",
    "LOW_CONFIDENCE",
    "MISSING_REQUIRED",
    "NATIVE_OCR_DISAGREEMENT",
    "NUMERIC_CONFLICT",
    "TABLE_LAYOUT_REVIEW_REQUIRED",
    "UNIT_CONFLICT",
    "LOT_CONFLICT",
    "VARIANT_DISAGREEMENT",
]


@dataclass(frozen=True)
class LocalOcrLimits:
    max_file_bytes: int = 25 * 1024 * 1024
    max_pages: int = 10
    max_total_pixels: int = 120_000_000
    render_dpi: int = 300
    oversample_dpi: int = 400
    max_variants_per_page: int = 12
    timeout_seconds: int = 120
    max_concurrency: Literal[1] = 1
    native_text_min_characters: int = 48
    native_text_min_alnum_ratio: Decimal = Decimal("0.55")
    low_confidence_threshold: Decimal = Decimal("0.85")

    def __post_init__(self) -> None:
        if self.max_file_bytes < 1 or self.max_pages < 1 or self.max_total_pixels < 1:
            raise ValueError("local OCR resource limits must be positive")
        if not 300 <= self.render_dpi <= 400 or not 300 <= self.oversample_dpi <= 400:
            raise ValueError("local OCR DPI must stay within the approved 300-400 range")
        if self.render_dpi > self.oversample_dpi:
            raise ValueError("local OCR base DPI cannot exceed oversample DPI")
        if self.max_variants_per_page < 1 or self.timeout_seconds < 1:
            raise ValueError("local OCR variant and timeout limits must be positive")
        if self.max_concurrency != 1:
            raise ValueError("local OCR concurrency is fixed at one")


@dataclass(frozen=True)
class OcrBoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    def __post_init__(self) -> None:
        if min(self.left, self.top) < 0 or self.right <= self.left or self.bottom <= self.top:
            raise ValueError("OCR bounding boxes must have non-negative positive area")


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: Decimal | str
    bbox: OcrBoundingBox
    reading_order: int

    def __post_init__(self) -> None:
        confidence = (
            self.confidence
            if isinstance(self.confidence, Decimal)
            else Decimal(self.confidence)
        )
        if not self.text or not confidence.is_finite() or not Decimal("0") <= confidence <= 1:
            raise ValueError("OCR lines require text and finite confidence in [0,1]")
        if self.reading_order < 1:
            raise ValueError("OCR reading order begins at one")
        object.__setattr__(self, "confidence", confidence)


@dataclass(frozen=True)
class RenderedPage:
    page_number: int
    width: int
    height: int
    rendered_dpi: int
    native_text: str
    native_lines: tuple[OcrLine, ...]
    image_png: bytes
    table_suspected: bool

    def __post_init__(self) -> None:
        if self.page_number < 1 or self.width < 1 or self.height < 1:
            raise ValueError("rendered page dimensions and number must be positive")
        if not 300 <= self.rendered_dpi <= 400:
            raise ValueError("rendered page DPI must be in the approved range")


@dataclass(frozen=True)
class ImageVariant:
    variant_id: str
    recipe_id: RecipeId
    image_png: bytes
    width: int
    height: int
    source_width: int
    source_height: int
    transform_to_source: tuple[float, float, float, float, float, float, float, float, float]
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    deskew_millidegrees: int = 0
    deskew_status: DeskewStatus = "NOT_NEEDED"
    perspective_corrected: bool = False

    def __post_init__(self) -> None:
        if min(self.width, self.height, self.source_width, self.source_height) < 1:
            raise ValueError("image variant dimensions must be positive")
        if len(self.transform_to_source) != 9:
            raise ValueError("image variant transform must be a 3x3 matrix")


@dataclass(frozen=True)
class OcrVariantResult:
    variant_id: str
    recipe_id: RecipeId
    lines: tuple[OcrLine, ...]
    width: int
    height: int
    transform_to_source: tuple[float, float, float, float, float, float, float, float, float]
    rotation_degrees: Literal[0, 90, 180, 270] = 0
    deskew_millidegrees: int = 0
    deskew_status: DeskewStatus = "NOT_NEEDED"
    perspective_corrected: bool = False


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    route: PageRoute
    rendered_dpi: int
    source_width: int
    source_height: int
    variants: tuple[OcrVariantResult, ...]
    selected_lines: tuple[OcrLine, ...]
    selected_variant_id: str
    selected_recipe_id: RecipeId
    selected_rotation_degrees: Literal[0, 90, 180, 270]
    selected_deskew_millidegrees: int
    selected_deskew_status: DeskewStatus
    selected_perspective_corrected: bool
    reason_codes: tuple[LocalReviewReason, ...]
    review_required: Literal[True] = True


@dataclass(frozen=True)
class SanitizedPageReport:
    page_number: int
    route: PageRoute
    rendered_dpi: int
    source_width: int
    source_height: int
    variant_count: int
    selected_line_count: int
    selected_text_sha256: str
    selected_variant_id: str
    selected_recipe_id: RecipeId
    selected_rotation_degrees: Literal[0, 90, 180, 270]
    selected_deskew_millidegrees: int
    selected_deskew_status: DeskewStatus
    selected_perspective_corrected: bool
    reason_codes: tuple[LocalReviewReason, ...]


@dataclass(frozen=True)
class SanitizedLocalOcrReport:
    source_binding: str
    model_binding: str
    pages: tuple[SanitizedPageReport, ...]
    review_required: Literal[True] = True
    provider_name: Literal["local-paddleocr"] = "local-paddleocr"
    schema_version: Literal["hyc.local-ocr-sanitized-report.v1"] = (
        "hyc.local-ocr-sanitized-report.v1"
    )

    def _payload(self) -> dict[str, object]:
        return {
            "model_binding": self.model_binding,
            "pages": [
                {
                    "page_number": page.page_number,
                    "reason_codes": list(page.reason_codes),
                    "rendered_dpi": page.rendered_dpi,
                    "source_width": page.source_width,
                    "source_height": page.source_height,
                    "route": page.route,
                    "selected_line_count": page.selected_line_count,
                    "selected_text_sha256": page.selected_text_sha256,
                    "selected_variant_id": page.selected_variant_id,
                    "selected_recipe_id": page.selected_recipe_id,
                    "selected_rotation_degrees": page.selected_rotation_degrees,
                    "selected_deskew_millidegrees": page.selected_deskew_millidegrees,
                    "selected_deskew_status": page.selected_deskew_status,
                    "selected_perspective_corrected": page.selected_perspective_corrected,
                    "variant_count": page.variant_count,
                }
                for page in self.pages
            ],
            "provider_name": self.provider_name,
            "review_required": self.review_required,
            "schema_version": self.schema_version,
            "source_binding": self.source_binding,
        }

    @property
    def report_sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self._payload(), ensure_ascii=True, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def canonical_json(self) -> str:
        payload = self._payload()
        payload["report_sha256"] = self.report_sha256
        return json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LocalOcrResult:
    pages: tuple[OcrPageResult, ...]
    input_sha256: str = field(repr=False)
    review_required: Literal[True] = True

    def sanitized_report(
        self, *, source_binding: str, model_binding: str
    ) -> SanitizedLocalOcrReport:
        pages = tuple(
            SanitizedPageReport(
                page_number=page.page_number,
                route=page.route,
                rendered_dpi=page.rendered_dpi,
                source_width=page.source_width,
                source_height=page.source_height,
                variant_count=len(page.variants),
                selected_line_count=len(page.selected_lines),
                selected_text_sha256=hashlib.sha256(
                    "\n".join(line.text for line in page.selected_lines).encode("utf-8")
                ).hexdigest(),
                selected_variant_id=page.selected_variant_id,
                selected_recipe_id=page.selected_recipe_id,
                selected_rotation_degrees=page.selected_rotation_degrees,
                selected_deskew_millidegrees=page.selected_deskew_millidegrees,
                selected_deskew_status=page.selected_deskew_status,
                selected_perspective_corrected=page.selected_perspective_corrected,
                reason_codes=page.reason_codes,
            )
            for page in self.pages
        )
        return SanitizedLocalOcrReport(
            source_binding=source_binding,
            model_binding=model_binding,
            pages=pages,
        )
