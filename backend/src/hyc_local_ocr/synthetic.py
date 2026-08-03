from __future__ import annotations

import io
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from hyc_local_ocr.errors import LocalOcrError

REQUIRED_DEGRADATIONS: tuple[str, ...] = (
    "rotation-0",
    "rotation-90",
    "rotation-180",
    "rotation-270",
    "skew-positive",
    "skew-negative",
    "perspective",
    "uneven-illumination-shadow",
    "low-contrast",
    "gaussian-noise",
    "salt-pepper-noise",
    "blur-jpeg-artifact",
    "downsample-oversample",
    "mixed-native-scanned-pages",
    "table",
    "blank-input",
    "corrupt-input",
    "oversized-input",
)


@dataclass(frozen=True)
class SyntheticCasePlan:
    case_id: str
    seed: int
    degradations: tuple[str, ...]
    synthetic: bool = True
    provenance_marker: str = "generated-non-sensitive-synthetic"


def synthetic_case_plan(seed: int) -> tuple[SyntheticCasePlan, ...]:
    groups = (
        REQUIRED_DEGRADATIONS[0:4],
        REQUIRED_DEGRADATIONS[4:8],
        REQUIRED_DEGRADATIONS[8:13],
        REQUIRED_DEGRADATIONS[13:15],
        REQUIRED_DEGRADATIONS[15:18],
    )
    return tuple(
        SyntheticCasePlan(
            case_id=f"synthetic-local-ocr-{index:02d}",
            seed=seed + index,
            degradations=group,
        )
        for index, group in enumerate(groups, start=1)
    )


@dataclass(frozen=True)
class SyntheticEngineeringMetrics:
    required_header_accuracy: Decimal
    numeric_accuracy: Decimal
    review_trigger_exposure: Decimal
    production_readiness_claim: bool = False

    def __post_init__(self) -> None:
        for name in (
            "required_header_accuracy",
            "numeric_accuracy",
            "review_trigger_exposure",
        ):
            value = getattr(self, name)
            converted = value if isinstance(value, Decimal) else Decimal(value)
            if not converted.is_finite() or not Decimal("0") <= converted <= 1:
                raise ValueError("synthetic metrics must be finite ratios in [0,1]")
            object.__setattr__(self, name, converted)
        if self.production_readiness_claim:
            raise ValueError("synthetic local OCR evidence cannot claim production readiness")

    @property
    def engineering_gate_passed(self) -> bool:
        return (
            self.required_header_accuracy >= Decimal("0.95")
            and self.numeric_accuracy >= Decimal("0.98")
            and self.review_trigger_exposure == Decimal("1.00")
        )


@dataclass(frozen=True)
class SyntheticSmokeCase:
    case_id: str
    document_bytes: bytes
    expected_header_fields: tuple[tuple[str, str], ...]
    expected_numeric_fields: tuple[tuple[str, str], ...]
    required_review_reasons: tuple[str, ...]
    forbidden_review_reasons: tuple[str, ...]
    degradations: tuple[str, ...]


def _runtime_modules() -> tuple[Any, Any, Any, Any]:
    try:
        import cv2
        import numpy
        from PIL import Image, ImageDraw, ImageFont
    except ImportError as error:
        raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
    return cv2, numpy, (Image, ImageDraw, ImageFont), io


def _font_path() -> Path:
    configured = os.environ.get("HYC_LOCAL_OCR_SYNTHETIC_FONT_PATH")
    candidates = tuple(
        path
        for path in (
            Path(configured) if configured else None,
            Path("/System/Library/Fonts/AppleSDGothicNeo.ttc"),
            Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
            Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        )
        if path is not None
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING")


def _base_image() -> Any:
    _, _, pil, _ = _runtime_modules()
    Image, ImageDraw, ImageFont = pil
    image = Image.new("RGB", (1200, 900), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(_font_path()), 44)
    lines = (
        "SYNTHETIC COA",
        "합성 시험성적서",
        "SUPPLIER: TEST LAB",
        "PRODUCT: GENERATED MATERIAL",
        "LOT: SYN-20260803-001",
        "MOISTURE % 1.25",
        "ASSAY % 99.50",
    )
    for index, line in enumerate(lines):
        draw.text((60, 35 + index * 100), line, font=font, fill=(10, 10, 10))
    return image


def _apply_degradations(image: Any, degradations: tuple[str, ...], seed: int) -> Any:
    cv2, numpy, _, _ = _runtime_modules()
    array = cv2.cvtColor(numpy.array(image), cv2.COLOR_RGB2BGR)
    height, width = array.shape[:2]
    generator = numpy.random.default_rng(seed)
    for degradation in degradations:
        if degradation.startswith("rotation-"):
            degrees = int(degradation.rsplit("-", 1)[1])
            operations = {
                90: cv2.ROTATE_90_CLOCKWISE,
                180: cv2.ROTATE_180,
                270: cv2.ROTATE_90_COUNTERCLOCKWISE,
            }
            if degrees in operations:
                array = cv2.rotate(array, operations[degrees])
                height, width = array.shape[:2]
        elif degradation in ("skew-positive", "skew-negative"):
            angle = 2.0 if degradation == "skew-positive" else -2.0
            matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
            array = cv2.warpAffine(
                array,
                matrix,
                (width, height),
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(255, 255, 255),
            )
        elif degradation == "perspective":
            source = numpy.float32([[0, 0], [width, 0], [width, height], [0, height]])
            offset = min(width, height) * 0.025
            target = numpy.float32(
                [[offset, 0], [width - offset, offset], [width, height], [0, height - offset]]
            )
            array = cv2.warpPerspective(
                array,
                cv2.getPerspectiveTransform(source, target),
                (width, height),
                borderValue=(255, 255, 255),
            )
        elif degradation == "uneven-illumination-shadow":
            gradient = numpy.linspace(0.72, 1.0, width, dtype=numpy.float32)
            illuminated = array.astype(numpy.float32) * gradient[None, :, None]
            array = numpy.clip(illuminated, 0, 255).astype(numpy.uint8)
        elif degradation == "low-contrast":
            array = cv2.convertScaleAbs(array, alpha=0.58, beta=96)
        elif degradation == "gaussian-noise":
            noise = generator.normal(0, 5, array.shape)
            array = numpy.clip(array.astype(numpy.float32) + noise, 0, 255).astype(numpy.uint8)
        elif degradation == "salt-pepper-noise":
            count = max(1, array.size // 2500)
            ys = generator.integers(0, height, count)
            xs = generator.integers(0, width, count)
            array[ys, xs] = generator.choice((0, 255), count)[:, None]
        elif degradation == "blur-jpeg-artifact":
            array = cv2.GaussianBlur(array, (3, 3), 0.55)
            success, encoded = cv2.imencode(".jpg", array, [cv2.IMWRITE_JPEG_QUALITY, 78])
            if success:
                array = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        elif degradation == "downsample-oversample":
            small = cv2.resize(array, (width // 2, height // 2), interpolation=cv2.INTER_AREA)
            array = cv2.resize(small, (width, height), interpolation=cv2.INTER_CUBIC)
        elif degradation == "table":
            for y in (710, 785, 860):
                cv2.line(array, (50, y), (1150, y), (80, 80, 80), 2)
            for x in (50, 400, 800, 1150):
                cv2.line(array, (x, 695), (x, 880), (80, 80, 80), 2)
    Image = _runtime_modules()[2][0]
    return Image.fromarray(cv2.cvtColor(array, cv2.COLOR_BGR2RGB))


def _image_pdf_bytes(image: Any) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(
        output,
        format="PDF",
        resolution=190.0,
        title="generated-non-sensitive-synthetic",
        author="HYC local OCR synthetic generator",
        creationDate="D:20260803000000Z",
        modDate="D:20260803000000Z",
    )
    return output.getvalue()


def _image_png_bytes(image: Any) -> bytes:
    output = io.BytesIO()
    image.convert("RGB").save(output, format="PNG", compress_level=9)
    return output.getvalue()


def generate_mixed_native_scanned_pdf(seed: int = 20260803) -> bytes:
    try:
        import fitz  # type: ignore[import-untyped]
    except ImportError as error:
        raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
    document = fitz.open()
    try:
        native_page = document.new_page(width=595, height=842)
        native_page.insert_textbox(
            fitz.Rect(50, 60, 545, 600),
            (
                "SYNTHETIC COA\nSUPPLIER: TEST LAB\nPRODUCT: GENERATED MATERIAL\n"
                "LOT: SYN-NATIVE-001\nMOISTURE % 1.25\nASSAY % 99.50"
            ),
            fontsize=18,
        )
        scanned_page = document.new_page(width=595, height=842)
        scanned = _apply_degradations(
            _base_image(), ("low-contrast", "gaussian-noise"), seed
        )
        scanned_page.insert_image(scanned_page.rect, stream=_image_png_bytes(scanned))
        return bytes(document.tobytes(garbage=4, deflate=True, no_new_id=True))
    finally:
        document.close()


def generate_synthetic_smoke_cases(seed: int = 20260803) -> tuple[SyntheticSmokeCase, ...]:
    groups = (
        ("rotation-0", "low-contrast", "uneven-illumination-shadow"),
        ("rotation-90", "skew-positive", "gaussian-noise"),
        ("rotation-180", "skew-negative", "salt-pepper-noise"),
        ("rotation-270", "perspective", "blur-jpeg-artifact"),
        ("downsample-oversample", "table"),
    )
    cases: list[SyntheticSmokeCase] = []
    for index, degradations in enumerate(groups, start=1):
        image = _apply_degradations(_base_image(), degradations, seed + index)
        cases.append(
            SyntheticSmokeCase(
                case_id=f"generated-synthetic-scan-{index:02d}",
                document_bytes=_image_pdf_bytes(image),
                expected_header_fields=(
                    ("SUPPLIER", "TEST LAB"),
                    ("PRODUCT", "GENERATED MATERIAL"),
                    ("LOT", "SYN-20260803-001"),
                ),
                expected_numeric_fields=(("MOISTURE", "1.25"), ("ASSAY", "99.50")),
                required_review_reasons=(
                    ("HUMAN_REVIEW_REQUIRED", "TABLE_LAYOUT_REVIEW_REQUIRED")
                    if "table" in degradations
                    else ("HUMAN_REVIEW_REQUIRED",)
                ),
                forbidden_review_reasons=(
                    () if "table" in degradations else ("TABLE_LAYOUT_REVIEW_REQUIRED",)
                ),
                degradations=degradations,
            )
        )
    return tuple(cases)
