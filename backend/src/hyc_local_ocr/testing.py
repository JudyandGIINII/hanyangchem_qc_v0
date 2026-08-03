from __future__ import annotations

from dataclasses import dataclass, field

from hyc_local_ocr.contracts import ImageVariant, LocalOcrLimits, OcrLine, RenderedPage
from hyc_local_ocr.errors import LocalOcrError


@dataclass
class FakeDocumentBackend:
    pages: tuple[RenderedPage, ...]
    corrupt: bool = False

    def load(
        self, document_bytes: bytes, limits: LocalOcrLimits, deadline: float
    ) -> tuple[RenderedPage, ...]:
        del document_bytes, limits, deadline
        if self.corrupt:
            raise LocalOcrError("LOCAL_OCR_PDF_CORRUPT")
        return self.pages


@dataclass
class RecordingOcrEngine:
    results: dict[str, tuple[OcrLine, ...]]
    calls: list[str] = field(default_factory=list)

    def recognize(self, variant: ImageVariant, deadline: float) -> tuple[OcrLine, ...]:
        del deadline
        self.calls.append(variant.variant_id)
        return self.results.get(variant.variant_id, self.results.get(variant.recipe_id, ()))
