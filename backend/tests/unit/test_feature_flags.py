from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError
from decimal import Decimal
from itertools import product
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from hyc_api.config import Settings
from hyc_api.extraction import SyntheticFixtureExtractionProvider
from hyc_api.main import create_app
from hyc_api.module_exposure import resolve_module_exposure_flags
from hyc_data.models import Document
from hyc_data.repositories import ApprovalRepository
from hyc_domain.judgment import (
    EngineDecision,
    ItemInput,
    JudgmentEngine,
    MissingPolicy,
    SamplePolicy,
    SourcePolicy,
)
from hyc_domain.snapshots import DecisionSnapshot
from hyc_domain.specs import Operator, Rule
from hyc_local_ocr.contracts import OcrBoundingBox, OcrLine, RenderedPage
from hyc_local_ocr.pipeline import LocalOcrPipeline
from hyc_local_ocr.testing import FakeDocumentBackend, RecordingOcrEngine

FLAG_NAMES = (
    "ncr_report_module_enabled",
    "ncr_approver_module_enabled",
    "ncr_retest_module_enabled",
    "ncr_attachment_module_enabled",
    "ncr_completion_date_module_enabled",
)
FLAG_COMBINATIONS = tuple(product((False, True), repeat=len(FLAG_NAMES)))


def _settings(values: tuple[bool, ...]) -> Settings:
    return Settings(_env_file=None, **dict(zip(FLAG_NAMES, values, strict=True)))


def _candidate_only_ocr() -> LocalOcrPipeline:
    line = OcrLine(
        text="SUPPLIER PRODUCT GENERATED MATERIAL CERTIFICATE REFERENCE",
        confidence=Decimal("0.50"),
        bbox=OcrBoundingBox(left=0, top=0, right=100, bottom=20),
        reading_order=1,
    )
    page = RenderedPage(
        page_number=1,
        width=100,
        height=100,
        rendered_dpi=300,
        native_text="SUPPLIER PRODUCT GENERATED MATERIAL CERTIFICATE REFERENCE DETAILS OMITTED",
        native_lines=(line,),
        image_png=b"",
        table_suspected=False,
    )
    return LocalOcrPipeline(FakeDocumentBackend((page,)), RecordingOcrEngine(results={}))


@pytest.mark.parametrize("values", FLAG_COMBINATIONS)
def test_every_module_flag_combination_preserves_fail_closed_invariants(
    values: tuple[bool, ...],
) -> None:
    settings = _settings(values)
    exposure = resolve_module_exposure_flags(settings)
    assert tuple(getattr(exposure, name) for name in FLAG_NAMES) == values

    candidate = SyntheticFixtureExtractionProvider().extract(str(uuid4()), "synthetic-source")
    assert candidate.review_required is True
    assert all(value.review_required for value in candidate.values)

    ocr_result = _candidate_only_ocr().extract(b"synthetic-candidate")
    reasons = ocr_result.pages[0].reason_codes
    assert ocr_result.pages[0].review_required is True
    assert {"HUMAN_REVIEW_REQUIRED", "LOW_CONFIDENCE", "MISSING_REQUIRED"} <= set(reasons)

    engine = JudgmentEngine()
    base = dict(
        rule=Rule(Operator.GTE, lower=Decimal("10")),
        source_policy=SourcePolicy.BOTH_INTERNAL_PRIORITY,
        missing_policy=MissingPolicy.HOLD,
        sample_policy=SamplePolicy.ALL_SAMPLES_IN_SPEC,
        supplier_values=(Decimal("12"),),
        internal_values=(Decimal("12"),),
    )
    assert engine.evaluate_item(ItemInput(**base, mapped=False)) is EngineDecision.ON_HOLD
    assert engine.evaluate_item(ItemInput(**base, source_confident=False)) is EngineDecision.ON_HOLD
    assert (
        engine.evaluate_item(
            ItemInput(**(base | {"internal_values": (), "internal_required": True}))
        )
        is EngineDecision.ON_HOLD
    )

    snapshot = DecisionSnapshot.freeze({"decision": "ON_HOLD"})
    with pytest.raises(FrozenInstanceError):
        snapshot.content_hash = "mutate"  # type: ignore[misc]


def test_flags_are_confined_to_exposure_and_cannot_reach_approval_or_evidence_guards() -> None:
    source_root = Path(__file__).resolve().parents[2] / "src"
    expected_paths = {
        "hyc_api/config.py",
        "hyc_api/contracts.py",
        "hyc_api/module_exposure.py",
        "hyc_api/routes/feature_flags.py",
    }
    observed_paths = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if any(flag_name in path.read_text() for flag_name in FLAG_NAMES)
    }

    assert observed_paths == expected_paths
    for invariant in (ApprovalRepository.finalize, Document, LocalOcrPipeline, JudgmentEngine):
        source = inspect.getsource(invariant)
        assert not any(flag_name in source for flag_name in FLAG_NAMES)

    finalize_source = inspect.getsource(ApprovalRepository.finalize)
    assert "session.add_all" in finalize_source
    assert "session.flush()" in finalize_source
    assert "immutable" in inspect.getsource(Document)


def test_feature_flags_endpoint_returns_resolved_exposure_flags() -> None:
    settings = _settings((True, False, True, False, True)).model_copy(
        update={"p3_fixture_mode": True}
    )
    app = create_app(settings)
    with TestClient(app) as client:
        session = client.post(
            "/api/v1/local-auth/sessions", json={"fixture_principal": "p3-inspector"}
        )
        assert session.status_code == 200, session.text
        response = client.get(
            "/api/v1/feature-flags",
            headers={"Authorization": f"Bearer {session.json()['session_handle']}"},
        )

    assert response.status_code == 200, response.text
    assert response.json() == dict(zip(FLAG_NAMES, (True, False, True, False, True), strict=True))
