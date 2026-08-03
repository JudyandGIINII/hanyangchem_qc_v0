"""Bounded, local-only OCR candidate extraction.

The package has no import-time dependency on PaddleOCR, OpenCV, or a PDF renderer.
Those optional runtime dependencies are loaded only after the local model manifest
has passed its fail-closed integrity checks.
"""

from hyc_local_ocr.contracts import LocalOcrLimits, LocalOcrResult
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pipeline import LocalOcrPipeline

__all__ = ["LocalOcrError", "LocalOcrLimits", "LocalOcrPipeline", "LocalOcrResult"]
