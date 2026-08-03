from __future__ import annotations

import os
import re
import stat
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol
from uuid import UUID, uuid4

from hyc_api.contracts import BoundingBox, ExtractionCandidate, ExtractionValue, SourceReference
from hyc_local_ocr.contracts import OcrLine, OcrPageResult
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pipeline import LocalOcrPipeline


class ExtractionProvider(Protocol):
    def extract(self, document_id: str, source_reference: str) -> ExtractionCandidate: ...


class SyntheticFixtureExtractionProvider:
    """Only synthetic contract data; this port never calls OCR or AI."""

    def extract(self, document_id: str, source_reference: str) -> ExtractionCandidate:
        reference = SourceReference(
            document_id=UUID(document_id),
            source_reference=source_reference,
            page_number=1,
            bbox=BoundingBox(left=0.0, top=0.0, right=1.0, bottom=1.0),
        )
        return ExtractionCandidate(
            schema_version="1.0",
            candidate_id=uuid4(),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            document=reference,
            provider_name="synthetic-fixture",
            values=[
                ExtractionValue(
                    item_key="SYNTHETIC_VALUE",
                    raw_text="TEST_FIXTURE_VALUE",
                    normalized_value=Decimal("1.00"),
                    provenance=reference,
                    confidence=1.0,
                    review_required=True,
                )
            ],
            review_required=True,
        )


class LocalDocumentResolver(Protocol):
    def read(self, source_reference: str) -> bytes: ...


class RootedLocalDocumentResolver:
    """Resolve opaque references through an explicit allowlist under one local root."""

    def __init__(
        self, root: Path, references: dict[str, str], *, max_file_bytes: int = 25 * 1024 * 1024
    ) -> None:
        self._root = root.resolve()
        self._references = dict(references)
        self._max_file_bytes = max_file_bytes

    def read(self, source_reference: str) -> bytes:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", source_reference):
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        relative = self._references.get(source_reference)
        if relative is None:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        candidate = (self._root / relative).resolve()
        if candidate == self._root or self._root not in candidate.parents:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        descriptor = -1
        try:
            descriptor = os.open(candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
            if metadata.st_size > self._max_file_bytes:
                raise LocalOcrError("LOCAL_OCR_FILE_TOO_LARGE")
            with os.fdopen(descriptor, "rb", closefd=True) as source:
                descriptor = -1
                body = source.read(self._max_file_bytes + 1)
            if len(body) > self._max_file_bytes:
                raise LocalOcrError("LOCAL_OCR_FILE_TOO_LARGE")
            return body
        except LocalOcrError:
            raise
        except OSError as error:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT") from error
        finally:
            if descriptor >= 0:
                os.close(descriptor)


class BytesDocumentResolver:
    """In-memory resolver for generated non-sensitive synthetic smoke inputs."""

    def __init__(self, references: dict[str, bytes]) -> None:
        self._references = dict(references)

    def read(self, source_reference: str) -> bytes:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", source_reference):
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT")
        try:
            return self._references[source_reference]
        except KeyError as error:
            raise LocalOcrError("LOCAL_OCR_INVALID_INPUT") from error


def _line_reference(
    document_id: UUID,
    source_reference: str,
    page: OcrPageResult,
    line: OcrLine,
    *,
    page_width: int,
    page_height: int,
) -> SourceReference:
    return SourceReference(
        document_id=document_id,
        source_reference=source_reference,
        page_number=page.page_number,
        bbox=BoundingBox(
            left=line.bbox.left / page_width,
            top=line.bbox.top / page_height,
            right=min(1.0, line.bbox.right / page_width),
            bottom=min(1.0, line.bbox.bottom / page_height),
        ),
    )


class LocalOcrExtractionProvider:
    """Candidate-only adapter; local failures never fall back to another provider."""

    def __init__(self, pipeline: LocalOcrPipeline, resolver: LocalDocumentResolver) -> None:
        self._pipeline = pipeline
        self._resolver = resolver

    def extract(self, document_id: str, source_reference: str) -> ExtractionCandidate:
        parsed_document_id = UUID(document_id)
        result = self._pipeline.extract(self._resolver.read(source_reference))
        values: list[ExtractionValue] = []
        value_index = 0
        for page in result.pages:
            for line in page.selected_lines:
                value_index += 1
                reference = _line_reference(
                    parsed_document_id,
                    source_reference,
                    page,
                    line,
                    page_width=page.source_width,
                    page_height=page.source_height,
                )
                values.append(
                    ExtractionValue(
                        item_key=f"OCR_TEXT_{value_index:04d}",
                        raw_text=line.text,
                        normalized_value=None,
                        provenance=reference,
                        confidence=float(line.confidence),
                        review_required=True,
                        reading_order=line.reading_order,
                        recipe_id=page.selected_recipe_id,
                        variant_id=page.selected_variant_id,
                        rotation_degrees=page.selected_rotation_degrees,
                        deskew_millidegrees=page.selected_deskew_millidegrees,
                        deskew_status=page.selected_deskew_status,
                        perspective_corrected=page.selected_perspective_corrected,
                        reason_codes=list(page.reason_codes),
                    )
                )
        document_reference = SourceReference(
            document_id=parsed_document_id,
            source_reference=source_reference,
            page_number=1,
            bbox=BoundingBox(left=0.0, top=0.0, right=1.0, bottom=1.0),
        )
        if not values:
            values.append(
                ExtractionValue(
                    item_key="OCR_NO_TEXT",
                    raw_text="NO_TEXT_CANDIDATE",
                    normalized_value=None,
                    provenance=document_reference,
                    confidence=0.0,
                    review_required=True,
                    reading_order=1,
                    recipe_id="original",
                    variant_id="original-r0",
                    rotation_degrees=0,
                    deskew_millidegrees=0,
                    deskew_status="NOT_NEEDED",
                    perspective_corrected=False,
                    reason_codes=["HUMAN_REVIEW_REQUIRED", "MISSING_REQUIRED"],
                )
            )
        return ExtractionCandidate(
            schema_version="1.0",
            candidate_id=uuid4(),
            created_at=datetime.now(UTC),
            document=document_reference,
            provider_name="local-paddleocr",
            values=values,
            review_required=True,
        )
