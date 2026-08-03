from __future__ import annotations

import os
import signal
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import FrameType
from typing import Any, Never, cast

from hyc_local_ocr.contracts import ImageVariant, OcrBoundingBox, OcrLine
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.manifest import LocalOcrModelManifest, load_and_verify_manifest
from hyc_local_ocr.network import NetworkDenyAudit, deny_outbound_network

PROHIBITED_RUNTIME_ENVIRONMENT = (
    "PADDLEOCR_ACCESS_TOKEN",
    "PADDLEOCR_API_KEY",
    "PADDLEOCR_ENDPOINT",
    "PADDLE_PDX_MODEL_SOURCE",
)


@contextmanager
def _wall_clock_timeout(deadline: float) -> Iterator[None]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def timed_out(_: int, __: FrameType | None) -> Never:
        raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")

    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.setitimer(signal.ITIMER_REAL, remaining)
    signal.signal(signal.SIGALRM, timed_out)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        if previous_timer[0] > 0:
            signal.setitimer(signal.ITIMER_REAL, previous_timer[0], previous_timer[1])


def _artifact_path(
    manifest: LocalOcrModelManifest, models_root: Path, role: str
) -> tuple[str, Path]:
    artifact = next((item for item in manifest.artifacts if item.role == role), None)
    if artifact is None:
        raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID")
    return artifact.model, (models_root / artifact.local_path).resolve()


class PaddleOcrEngine:
    """PaddleOCR adapter that initializes and predicts with outbound networking denied."""

    def __init__(self, pipeline: Any, initialization_audit: NetworkDenyAudit) -> None:
        self._pipeline = pipeline
        self.initialization_network_attempt_count = initialization_audit.attempt_count
        self.prediction_network_attempt_count = 0

    @classmethod
    def from_local_models(
        cls, manifest_path: Path, models_root: Path
    ) -> PaddleOcrEngine:
        if any(os.environ.get(name) for name in PROHIBITED_RUNTIME_ENVIRONMENT):
            raise LocalOcrError("LOCAL_OCR_MODEL_MANIFEST_INVALID")
        manifest = load_and_verify_manifest(manifest_path, models_root)
        detection_name, detection_path = _artifact_path(
            manifest, models_root, "text-detection"
        )
        recognition_name, recognition_path = _artifact_path(
            manifest, models_root, "text-recognition"
        )
        try:
            with deny_outbound_network() as audit:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    from paddleocr import PaddleOCR  # type: ignore[import-untyped]

                    pipeline = PaddleOCR(
                        text_detection_model_name=detection_name,
                        text_detection_model_dir=str(detection_path),
                        text_recognition_model_name=recognition_name,
                        text_recognition_model_dir=str(recognition_path),
                        use_doc_orientation_classify=False,
                        use_doc_unwarping=False,
                        use_textline_orientation=False,
                        device="cpu",
                        enable_mkldnn=False,
                    )
        except LocalOcrError:
            raise
        except ImportError as error:
            raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
        except Exception as error:
            raise LocalOcrError("LOCAL_OCR_INFERENCE_FAILED") from error
        return cls(pipeline, audit)

    def recognize(self, variant: ImageVariant, deadline: float) -> tuple[OcrLine, ...]:
        if time.monotonic() >= deadline:
            raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")
        try:
            import cv2
            import numpy
        except ImportError as error:
            raise LocalOcrError("LOCAL_OCR_RUNTIME_DEPENDENCY_MISSING") from error
        image = cv2.imdecode(
            numpy.frombuffer(variant.image_png, dtype=numpy.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        try:
            with deny_outbound_network() as audit:
                with redirect_stdout(StringIO()), redirect_stderr(StringIO()):
                    with _wall_clock_timeout(deadline):
                        results = self._pipeline.predict(
                            image,
                            use_doc_orientation_classify=False,
                            use_doc_unwarping=False,
                            use_textline_orientation=False,
                        )
        except LocalOcrError:
            raise
        except Exception as error:
            raise LocalOcrError("LOCAL_OCR_INFERENCE_FAILED") from error
        self.prediction_network_attempt_count += audit.attempt_count
        if time.monotonic() >= deadline:
            raise LocalOcrError("LOCAL_OCR_TIMEOUT_EXCEEDED")
        if not results:
            return ()
        payload = cast(dict[str, Any], results[0].json).get("res", {})
        texts = payload.get("rec_texts", [])
        scores = payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes", [])
        if not (isinstance(texts, list) and isinstance(scores, list)):
            raise LocalOcrError("LOCAL_OCR_INFERENCE_FAILED")
        if len(texts) != len(scores) or len(texts) != len(boxes):
            raise LocalOcrError("LOCAL_OCR_INFERENCE_FAILED")
        lines: list[OcrLine] = []
        for index, (text, score, box) in enumerate(zip(texts, scores, boxes, strict=True), start=1):
            if not isinstance(text, str) or not text.strip() or len(box) != 4:
                continue
            left, top, right, bottom = (max(0, int(value)) for value in box)
            if right <= left or bottom <= top:
                continue
            lines.append(
                OcrLine(
                    text=text.strip(),
                    confidence=Decimal(str(score)),
                    bbox=OcrBoundingBox(left=left, top=top, right=right, bottom=bottom),
                    reading_order=index,
                )
            )
        return tuple(lines)
