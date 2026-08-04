from __future__ import annotations

from typing import Literal

type LocalOcrErrorCode = Literal[
    "LOCAL_OCR_ENGINE_UNSUPPORTED",
    "LOCAL_OCR_CONCURRENCY_LIMIT_EXCEEDED",
    "LOCAL_OCR_FILE_TOO_LARGE",
    "LOCAL_OCR_INFERENCE_FAILED",
    "LOCAL_OCR_INVALID_INPUT",
    "LOCAL_OCR_LINE_LIMIT_EXCEEDED",
    "LOCAL_OCR_MODEL_HASH_MISMATCH",
    "LOCAL_OCR_MODEL_MANIFEST_INVALID",
    "LOCAL_OCR_MODEL_MISSING",
    "LOCAL_OCR_MODEL_PATH_INVALID",
    "LOCAL_OCR_NETWORK_ACCESS_DENIED",
    "LOCAL_OCR_PAGE_LIMIT_EXCEEDED",
    "LOCAL_OCR_PDF_CORRUPT",
    "LOCAL_OCR_PDF_ENCRYPTED",
    "LOCAL_OCR_PIXEL_LIMIT_EXCEEDED",
    "LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING",
    "LOCAL_OCR_TIMEOUT_EXCEEDED",
    "LOCAL_OCR_UNSUPPORTED_MEDIA_TYPE",
]


class LocalOcrError(RuntimeError):
    """Fail-closed error that intentionally carries no source text or path."""

    def __init__(self, code: LocalOcrErrorCode) -> None:
        self.code = code
        super().__init__(code)
