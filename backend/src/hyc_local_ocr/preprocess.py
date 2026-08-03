from __future__ import annotations

from typing import Any, Literal, cast

from hyc_local_ocr.contracts import (
    DeskewStatus,
    ImageVariant,
    LocalOcrLimits,
    RecipeId,
    RenderedPage,
)
from hyc_local_ocr.errors import LocalOcrError


def _runtime_modules() -> tuple[Any, Any]:
    try:
        import cv2
        import numpy
    except ImportError as error:
        raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
    return cv2, numpy


def _encode_png(image: Any, cv2: Any) -> bytes:
    success, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 9])
    if not success:
        raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
    return bytes(encoded.tobytes())


def _identity_matrix(numpy: Any) -> Any:
    return numpy.eye(3, dtype=numpy.float64)


def _matrix_tuple(
    matrix: Any,
) -> tuple[float, float, float, float, float, float, float, float, float]:
    return cast(
        tuple[float, float, float, float, float, float, float, float, float],
        tuple(float(value) for value in matrix.reshape(-1)),
    )


def _deskew(image: Any, cv2: Any, numpy: Any) -> tuple[Any, int, DeskewStatus, Any]:
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    inverse = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    y_coordinates, x_coordinates = numpy.where(inverse > 0)
    coordinates = numpy.column_stack((x_coordinates, y_coordinates)).astype(numpy.float32)
    if len(coordinates) < 100:
        return image, 0, "NOT_NEEDED", _identity_matrix(numpy)
    raw_angle = float(cv2.minAreaRect(coordinates)[-1])
    skew_angle = raw_angle - 90.0 if raw_angle > 45.0 else raw_angle
    correction_angle = skew_angle
    if abs(correction_angle) < 0.15:
        return image, 0, "NOT_NEEDED", _identity_matrix(numpy)
    if abs(correction_angle) > 10:
        return image, 0, "OUT_OF_BOUNDS", _identity_matrix(numpy)
    height, width = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), correction_angle, 1.0)
    corrected = cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    homogeneous = numpy.vstack((matrix, numpy.array([0.0, 0.0, 1.0])))
    return corrected, round(correction_angle * 1000), "APPLIED", homogeneous


def _safe_unwarp(image: Any, cv2: Any, numpy: Any) -> tuple[Any, bool, Any]:
    gray = image if len(image.shape) == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 160)
    contours = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]
    height, width = gray.shape[:2]
    page_area = height * width
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:5]:
        perimeter = cv2.arcLength(contour, True)
        polygon = cv2.approxPolyDP(contour, 0.02 * perimeter, True)
        if len(polygon) != 4 or cv2.contourArea(polygon) < page_area * 0.55:
            continue
        points = polygon.reshape(4, 2).astype("float32")
        sums = points.sum(axis=1)
        differences = numpy.diff(points, axis=1).reshape(-1)
        ordered = numpy.array(
            [
                points[numpy.argmin(sums)],
                points[numpy.argmin(differences)],
                points[numpy.argmax(sums)],
                points[numpy.argmax(differences)],
            ],
            dtype="float32",
        )
        target = numpy.array(
            [[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]],
            dtype="float32",
        )
        transform = cv2.getPerspectiveTransform(ordered, target)
        return cv2.warpPerspective(image, transform, (width, height)), True, transform
    return image, False, _identity_matrix(numpy)


class OpenCvPreprocessor:
    """Deterministic variants with original preservation and bounded geometry correction."""

    def variants(
        self, page: RenderedPage, limits: LocalOcrLimits
    ) -> tuple[ImageVariant, ...]:
        cv2, numpy = _runtime_modules()
        if not page.image_png:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        original = cv2.imdecode(
            numpy.frombuffer(page.image_png, dtype=numpy.uint8), cv2.IMREAD_COLOR
        )
        if original is None:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        height, width = original.shape[:2]
        variants: list[ImageVariant] = [
            ImageVariant(
                variant_id="original-r0",
                recipe_id="original",
                image_png=page.image_png,
                width=width,
                height=height,
                source_width=width,
                source_height=height,
                transform_to_source=_matrix_tuple(_identity_matrix(numpy)),
            )
        ]

        rotations = (
            (90, cv2.ROTATE_90_CLOCKWISE),
            (180, cv2.ROTATE_180),
            (270, cv2.ROTATE_90_COUNTERCLOCKWISE),
        )
        for degrees, operation in rotations:
            rotated = cv2.rotate(original, operation)
            rotated_height, rotated_width = rotated.shape[:2]
            transforms_to_source = {
                90: numpy.array(
                    [[0.0, 1.0, 0.0], [-1.0, 0.0, float(height)], [0.0, 0.0, 1.0]]
                ),
                180: numpy.array(
                    [
                        [-1.0, 0.0, float(width)],
                        [0.0, -1.0, float(height)],
                        [0.0, 0.0, 1.0],
                    ]
                ),
                270: numpy.array(
                    [[0.0, -1.0, float(width)], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]]
                ),
            }
            variants.append(
                ImageVariant(
                    variant_id=f"original-r{degrees}",
                    recipe_id="original",
                    image_png=_encode_png(rotated, cv2),
                    width=rotated_width,
                    height=rotated_height,
                    source_width=width,
                    source_height=height,
                    transform_to_source=_matrix_tuple(transforms_to_source[degrees]),
                    rotation_degrees=cast(Literal[90, 180, 270], degrees),
                )
            )

        corrected, perspective, perspective_transform = _safe_unwarp(original, cv2, numpy)
        corrected, deskew, deskew_status, deskew_transform = _deskew(corrected, cv2, numpy)
        transform_to_source = numpy.linalg.inv(deskew_transform @ perspective_transform)
        gray = cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
        adaptive = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11
        )
        denoised = cv2.medianBlur(gray, 3)
        otsu = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
        sharpened = cv2.addWeighted(otsu, 1.35, cv2.GaussianBlur(otsu, (0, 0), 1.0), -0.35, 0)
        recipes: tuple[tuple[RecipeId, Any], ...] = (
            ("grayscale-clahe", clahe),
            ("adaptive-threshold", adaptive),
            ("otsu-denoise-sharpen", sharpened),
        )
        for recipe, image in recipes:
            variants.append(
                ImageVariant(
                    variant_id=recipe,
                    recipe_id=recipe,
                    image_png=_encode_png(image, cv2),
                    width=width,
                    height=height,
                    source_width=width,
                    source_height=height,
                    transform_to_source=_matrix_tuple(transform_to_source),
                    deskew_millidegrees=deskew,
                    deskew_status=deskew_status,
                    perspective_corrected=perspective,
                )
            )
        if len(variants) > limits.max_variants_per_page:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        return tuple(variants)
