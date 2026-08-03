from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from hyc_api.extraction import (
    BytesDocumentResolver,
    ExtractionProvider,
    LocalOcrExtractionProvider,
    RootedLocalDocumentResolver,
    SyntheticFixtureExtractionProvider,
)
from hyc_api.storage import ImmutableSourceStorage
from hyc_local_ocr.contracts import OcrBoundingBox, OcrLine, RenderedPage
from hyc_local_ocr.errors import LocalOcrError
from hyc_local_ocr.pipeline import LocalOcrPipeline
from hyc_local_ocr.testing import FakeDocumentBackend, RecordingOcrEngine


def test_synthetic_provider_is_contract_only() -> None:
    provider: ExtractionProvider = SyntheticFixtureExtractionProvider()
    candidate = provider.extract(
        "123e4567-e89b-12d3-a456-426614174001", "synthetic://fixture/document"
    )
    assert candidate.provider_name == "synthetic-fixture"
    assert candidate.review_required is True
    assert all(value.review_required for value in candidate.values)


def test_storage_port_is_a_type_only_boundary() -> None:
    # P1 must not instantiate a real-source storage adapter.
    assert ImmutableSourceStorage.__name__ == "ImmutableSourceStorage"


def test_local_provider_returns_review_only_candidate_without_fallback() -> None:
    page = RenderedPage(
        page_number=1,
        width=1000,
        height=1000,
        rendered_dpi=300,
        native_text="",
        native_lines=(),
        image_png=b"synthetic-scan",
        table_suspected=False,
    )
    line = OcrLine(
        text="LOT: SYN-001",
        confidence="0.99",
        bbox=OcrBoundingBox(left=1, top=1, right=100, bottom=30),
        reading_order=1,
    )
    pipeline = LocalOcrPipeline(
        FakeDocumentBackend((page,)), RecordingOcrEngine({"original": (line,)})
    )
    provider: ExtractionProvider = LocalOcrExtractionProvider(
        pipeline, BytesDocumentResolver({"local-source:synthetic": b"%PDF-synthetic"})
    )

    candidate = provider.extract(
        "123e4567-e89b-12d3-a456-426614174001", "local-source:synthetic"
    )

    assert candidate.provider_name == "local-paddleocr"
    assert candidate.review_required is True
    assert all(value.review_required for value in candidate.values)
    assert all("HUMAN_REVIEW_REQUIRED" in value.reason_codes for value in candidate.values)
    assert candidate.values[0].variant_id == "original"
    assert candidate.values[0].rotation_degrees == 0
    assert candidate.values[0].deskew_status == "NOT_NEEDED"
    assert candidate.values[0].provenance.bbox.left == pytest.approx(0.001)
    assert candidate.values[0].provenance.bbox.right == pytest.approx(0.1)
    assert candidate.values[0].provenance.bbox.bottom == pytest.approx(0.03)
    assert candidate.values[0].provenance.bbox.right <= 1
    assert candidate.values[0].provenance.bbox.bottom <= 1


def test_rooted_resolver_is_read_only_bounded_and_opaque(tmp_path: Path) -> None:
    source = tmp_path / "generated.bin"
    source.write_bytes(b"generated-synthetic")
    before = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)
    resolver = RootedLocalDocumentResolver(
        tmp_path, {"opaque-source-1": "generated.bin"}, max_file_bytes=32
    )

    assert resolver.read("opaque-source-1") == b"generated-synthetic"
    after = (hashlib.sha256(source.read_bytes()).hexdigest(), source.stat().st_mtime_ns)

    assert before == after
    with pytest.raises(LocalOcrError, match="LOCAL_OCR_INVALID_INPUT"):
        resolver.read("../generated.bin")


def test_rooted_resolver_bounds_read_even_if_metadata_underreports_size(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "growing.bin"
    source.write_bytes(b"x" * 64)
    resolver = RootedLocalDocumentResolver(
        tmp_path, {"opaque-growing": "growing.bin"}, max_file_bytes=32
    )
    real_fstat = os.fstat

    def underreported(descriptor: int) -> SimpleNamespace:
        metadata = real_fstat(descriptor)
        return SimpleNamespace(st_mode=metadata.st_mode, st_size=1)

    monkeypatch.setattr("hyc_api.extraction.os.fstat", underreported)

    with pytest.raises(LocalOcrError) as caught:
        resolver.read("opaque-growing")

    assert caught.value.code == "LOCAL_OCR_FILE_TOO_LARGE"
