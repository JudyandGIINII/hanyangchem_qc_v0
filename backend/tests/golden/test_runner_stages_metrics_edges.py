from __future__ import annotations

import json
from copy import deepcopy
from decimal import (
    ROUND_CEILING,
    ROUND_DOWN,
    ROUND_FLOOR,
    ROUND_HALF_EVEN,
    ROUND_UP,
    Decimal,
    localcontext,
)
from pathlib import Path

import pytest
from pydantic import ValidationError

from hyc_evaluation.artifacts import (
    CandidateRunArtifact,
    GoldenEvaluationReport,
    StageArtifact,
    StageArtifactManifest,
    canonical_json_bytes,
    canonical_sha256,
)
from hyc_evaluation.runner import (
    FIXED_CLOCK_TOKENS,
    BenchmarkOutput,
    build_success_stage_manifest,
    load_fixture_bundle,
    run_synthetic_benchmark,
)
from hyc_evaluation.scoring import score_candidate_runs
from hyc_evaluation.synthetic_data import generated_fixture_payload

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/p4/synthetic/p4a_edge_dataset.v1.json"
EXPECTED_STAGES = (
    "TEXT_LAYER_DETECTION",
    "PAGE_RENDER",
    "ROTATION_DESKEW_CONTRAST",
    "TABLE_DETECTION",
    "SYNTHETIC_FIXTURE_EXTRACTION",
    "PARSE",
    "SCHEMA_VALIDATION",
    "LOGIC_VALIDATION",
)


def test_staged_artifacts_are_exact_ordered_lineage_bound_and_fail_closed() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    successful = result.candidate_artifacts[0]

    assert tuple(stage.stage_name for stage in successful.stage_manifest.stages) == EXPECTED_STAGES
    assert tuple(stage.stage_order for stage in successful.stage_manifest.stages) == tuple(
        range(1, 9)
    )
    assert successful.stage_manifest_sha256 == canonical_sha256(successful.stage_manifest)
    assert successful.final_stage_artifact_ref == successful.stage_manifest.stages[-1].artifact_ref
    for previous, current in zip(
        successful.stage_manifest.stages,
        successful.stage_manifest.stages[1:],
        strict=False,
    ):
        assert current.upstream_artifact_refs == (previous.artifact_ref,)
        assert current.input_digests == (previous.output_sha256,)

    failed = next(
        artifact for artifact in result.candidate_artifacts if artifact.case_id == "edge-016"
    )
    failed_stages = failed.stage_manifest.stages
    failure_index = next(
        index for index, stage in enumerate(failed_stages) if stage.status == "FAILED"
    )
    assert all(
        stage.status == "SKIPPED_UPSTREAM_FAILURE"
        and stage.error_codes == ("SKIPPED_UPSTREAM_FAILURE",)
        for stage in failed_stages[failure_index + 1 :]
    )
    assert failed.review_required is True
    assert failed.escalation_required is True
    assert "UPSTREAM_FAILURE" in failed.reason_codes


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["stages"].reverse(),
        lambda payload: payload["stages"][1].update(upstream_artifact_refs=[]),
        lambda payload: payload["stages"][1].update(input_digests=["f" * 64]),
        lambda payload: payload["stages"][1].update(
            artifact_ref=payload["stages"][0]["artifact_ref"]
        ),
        lambda payload: payload["stages"][3].update(
            status="SKIPPED_UPSTREAM_FAILURE", error_codes=["SKIPPED_UPSTREAM_FAILURE"]
        ),
    ],
)
def test_stage_manifest_rejects_order_lineage_ref_and_status_contradictions(
    mutator: object,
) -> None:
    manifest = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).stage_manifests[0]
    payload = manifest.model_dump(mode="json")
    mutator(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        StageArtifactManifest.model_validate(payload)


def test_candidate_and_report_reject_stage_digest_order_cardinality_contradictions() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    candidate_payload = result.candidate_artifacts[0].model_dump(mode="json")
    candidate_payload["stage_manifest_sha256"] = "f" * 64
    with pytest.raises(ValidationError):
        CandidateRunArtifact.model_validate(candidate_payload)

    report_payload = result.report.model_dump(mode="json")
    report_payload["stage_manifest_sha256"].reverse()
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate(report_payload)

    report_payload = result.report.model_dump(mode="json")
    report_payload["stage_manifest_sha256"].pop()
    with pytest.raises(ValidationError):
        GoldenEvaluationReport.model_validate(report_payload)


def test_stage_schemas_are_strict_frozen_and_carry_no_raw_payload_fields() -> None:
    manifest = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).stage_manifests[0]
    for model, instance in (
        (StageArtifact, manifest.stages[0]),
        (StageArtifactManifest, manifest),
    ):
        schema = model.model_json_schema()
        assert schema["additionalProperties"] is False
        payload = instance.model_dump(mode="json")
        payload["raw_bytes"] = "forbidden"
        with pytest.raises(ValidationError):
            model.model_validate(payload)
    assert "raw_bytes" not in canonical_json_bytes(manifest).decode()
    assert "ocr_payload" not in canonical_json_bytes(manifest).decode()

def test_metrics_include_classification_page_geometry_and_not_applicable_operations() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    metrics = result.report.metrics

    assert metrics.document_classification_exact.denominator == 20
    assert metrics.document_classification_exact.numerator == 20
    assert metrics.page_number_exact.denominator > 0
    assert metrics.page_number_exact.numerator == metrics.page_number_exact.denominator - 1
    assert metrics.page_mismatch_count == 1
    assert metrics.missing_polygon_count == 0
    assert metrics.invalid_polygon_count == 0
    assert metrics.polygon_iou
    page_mismatch = next(item for item in metrics.polygon_iou if item.error_code is not None)
    assert page_mismatch.case_id == "edge-018"
    assert page_mismatch.iou is None
    assert page_mismatch.error_code == "PAGE_MISMATCH"
    assert any(
        item.iou is not None and Decimal("0") < item.iou < Decimal("1")
        for item in metrics.polygon_iou
    )
    assert {item.field_key for item in metrics.polygon_iou} >= {
        "SUPPLIER_NAME",
        "PRODUCT_NAME",
        "LOT_NUMBER",
        "CALCIUM_CHLORIDE_CONTENT",
    }
    assert next(item for item in metrics.by_kind if item.kind == "header")
    assert next(item for item in metrics.by_kind if item.kind == "decimal")
    assert next(item for item in metrics.by_kind if item.kind == "unit")
    assert next(item for item in metrics.by_kind if item.kind == "lot")
    assert result.report.operational_metrics.latency.status == "NOT_APPLICABLE"
    assert result.report.operational_metrics.provider_cost.status == "NOT_APPLICABLE"
    assert result.report.operational_metrics.human_correction_time.status == "NOT_APPLICABLE"
    assert result.report.operational_metrics.latency.reason == "P4A_SYNTHETIC_NO_MEASUREMENT"


def test_public_report_polygon_counters_remain_present_and_zero() -> None:
    report = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).report
    report_payload = report.model_dump(mode="json")

    assert report_payload["metrics"]["missing_polygon_count"] == 0
    assert report_payload["metrics"]["invalid_polygon_count"] == 0
    assert all(case["metrics"]["missing_polygon_count"] == 0 for case in report_payload["cases"])
    assert all(case["metrics"]["invalid_polygon_count"] == 0 for case in report_payload["cases"])


def test_tracked_twenty_edge_metric_numerators_and_denominators_are_exact() -> None:
    metrics = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).report.metrics
    assert (
        metrics.document_classification_exact.numerator,
        metrics.document_classification_exact.denominator,
    ) == (20, 20)
    assert (metrics.exact_field_match.numerator, metrics.exact_field_match.denominator) == (
        35,
        44,
    )
    assert (
        metrics.normalized_field_match.numerator,
        metrics.normalized_field_match.denominator,
    ) == (35, 44)
    assert (metrics.missing_required.numerator, metrics.missing_required.denominator) == (
        3,
        44,
    )
    assert (metrics.row_precision.numerator, metrics.row_precision.denominator) == (23, 24)
    assert (metrics.row_recall.numerator, metrics.row_recall.denominator) == (23, 25)
    assert (metrics.page_number_exact.numerator, metrics.page_number_exact.denominator) == (
        40,
        41,
    )


def test_strict_candidate_geometry_fails_closed_when_missing_invalid_or_zero_area() -> None:
    artifact = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).candidate_artifacts[0]
    payload = artifact.model_dump(mode="json")
    payload["values"][0].pop("geometry")
    with pytest.raises(ValidationError):
        CandidateRunArtifact.model_validate(payload)

    for polygon in (
        [
            {"x": "0", "y": "0"},
            {"x": "3", "y": "0"},
            {"x": "1", "y": "1"},
            {"x": "3", "y": "3"},
            {"x": "0", "y": "3"},
        ],
        [
            {"x": "0", "y": "0"},
            {"x": "3", "y": "3"},
            {"x": "0", "y": "3"},
            {"x": "3", "y": "0"},
        ],
    ):
        payload = artifact.model_dump(mode="json")
        payload["values"][0]["geometry"]["polygon"] = polygon
        with pytest.raises(ValidationError):
            CandidateRunArtifact.model_validate(payload)

    payload = artifact.model_dump(mode="json")
    payload["values"][0]["geometry"]["polygon"] = [
        {"x": "0", "y": "0"},
        {"x": "1", "y": "1"},
        {"x": "2", "y": "2"},
    ]
    with pytest.raises(ValidationError):
        CandidateRunArtifact.model_validate(payload)


def test_generated_fixture_has_exact_prd_edge_matrix_and_cross_phase_limits() -> None:
    bundle = load_fixture_bundle(FIXTURE)

    assert bundle.fixture_schema_version == "hyc.synthetic-fixture-bundle.v1"
    assert [edge.edge_id for edge in bundle.edge_matrix] == [
        f"P4-EDGE-{index:03d}" for index in range(1, 21)
    ]
    assert len(bundle.dataset.cases) == 20
    assert len(bundle.candidate_cases) == 20
    assert {edge.case_id for edge in bundle.edge_matrix} == {
        case.case_id for case in bundle.dataset.cases
    }
    assert all(edge.synthetic_fixture_ref == FIXTURE.name for edge in bundle.edge_matrix)
    assert all(
        edge.executable_test_path.startswith("backend/tests/") for edge in bundle.edge_matrix
    )
    cross_phase = [edge for edge in bundle.edge_matrix if edge.owner_phase != "P4-A"]
    assert cross_phase
    assert all(edge.p4a_limit != "FULL_WORKFLOW_IMPLEMENTED" for edge in cross_phase)
    assert json.loads(FIXTURE.read_text()) == load_fixture_bundle(
        generated_fixture_payload()
    ).model_dump(mode="json")


def test_runner_consumes_independent_candidates_and_reaches_nontrivial_evidence() -> None:
    payload = json.loads(FIXTURE.read_text())
    edge_index = 4
    expected = payload["dataset"]["cases"][edge_index]["expected_fields"][0]
    candidate = payload["candidate_cases"][edge_index]["values"][0]
    original_candidate_raw = candidate["value"]["raw"]
    expected["value"].update(raw="DIFFERENT-GOLDEN", normalized="DIFFERENT-GOLDEN")
    payload["edge_matrix"][edge_index]["expected_reason_codes"] = ["VALUE_MISMATCH"]
    payload["edge_matrix"][edge_index]["expected_disposition"] = "REVIEW_REQUIRED"

    changed = run_synthetic_benchmark(load_fixture_bundle(payload))
    changed_case = changed.report.cases[edge_index]
    assert changed.candidate_artifacts[edge_index].values[0].value.raw == original_candidate_raw
    assert "VALUE_MISMATCH" in changed_case.reason_codes

    baseline = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    assert baseline.report.metrics.exact_field_match.numerator < (
        baseline.report.metrics.exact_field_match.denominator
    )
    assert baseline.report.metrics.page_number_exact.numerator < (
        baseline.report.metrics.page_number_exact.denominator
    )
    assert any(
        evidence.iou is not None and Decimal("0") < evidence.iou < Decimal("1")
        for evidence in baseline.report.metrics.polygon_iou
    )
    reachable = set(baseline.report.reason_codes)
    assert reachable >= {
        "DUPLICATE_FIELD",
        "PAGE_MISMATCH",
        "UNAPPROVED_NORMALIZATION",
        "UNMAPPED",
        "VALUE_MISMATCH",
    }
    edge_four = baseline.candidate_artifacts[3]
    assert [value.value.raw for value in edge_four.values] == ["LOT-01", "llI"]


def test_all_edge_dispositions_and_executable_reasons_match_outcomes() -> None:
    bundle = load_fixture_bundle(FIXTURE)
    result = run_synthetic_benchmark(bundle)

    for edge, case in zip(bundle.edge_matrix, result.report.cases, strict=True):
        assert case.reason_codes == edge.expected_reason_codes
        if edge.expected_disposition == "CANDIDATE_ONLY":
            assert case.acceptance_eligible is True
            assert case.review_required is False
        else:
            assert case.acceptance_eligible is False
            assert case.review_required is True
        if edge.expected_disposition == "STABLE_FAILURE":
            assert "UPSTREAM_FAILURE" in case.reason_codes
        if edge.expected_disposition == "MANUAL_FALLBACK":
            assert "MISSING_REQUIRED" in case.reason_codes
            assert "UPSTREAM_FAILURE" not in case.reason_codes
        if edge.expected_disposition == "REVIEW_REQUIRED":
            assert "MISSING_REQUIRED" not in case.reason_codes
            assert "UPSTREAM_FAILURE" not in case.reason_codes

    assert all(
        next(case for case in result.report.cases if case.case_id == case_id).review_required
        for case_id in ("edge-007", "edge-009", "edge-011", "edge-018")
    )


@pytest.mark.parametrize(
    ("case_id", "replacement"),
    [
        ("edge-008", "REVIEW_REQUIRED"),
        ("edge-007", "MANUAL_FALLBACK"),
        ("edge-016", "REVIEW_REQUIRED"),
        ("edge-016", "MANUAL_FALLBACK"),
        ("edge-005", "REVIEW_REQUIRED"),
        ("edge-005", "MANUAL_FALLBACK"),
        ("edge-005", "STABLE_FAILURE"),
    ],
)
def test_edge_disposition_labels_cannot_be_swapped(
    case_id: str,
    replacement: str,
) -> None:
    payload = json.loads(FIXTURE.read_text())
    edge = next(item for item in payload["edge_matrix"] if item["case_id"] == case_id)
    edge["expected_disposition"] = replacement

    with pytest.raises(ValueError, match="disposition|STABLE_FAILURE"):
        run_synthetic_benchmark(load_fixture_bundle(payload))


def test_stage_warnings_come_from_candidate_observations_not_golden_review_reasons() -> None:
    baseline = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    baseline_extraction = baseline.stage_manifests[0].stages[4]
    payload = json.loads(FIXTURE.read_text())
    golden_fields = payload["dataset"]["cases"][0]["expected_fields"]
    low_confidence = next(
        field for field in golden_fields if field["field_key"] == "STAMP_OVERLAP_VALUE"
    )
    low_confidence["review"]["reason_codes"] = []
    low_confidence["review"]["review_required"] = False

    changed = run_synthetic_benchmark(load_fixture_bundle(payload))
    changed_extraction = changed.stage_manifests[0].stages[4]

    assert changed_extraction.warning_codes == baseline_extraction.warning_codes == (
        "HANDWRITING_REFERENCE_ONLY",
        "LOW_CONFIDENCE",
        "STAMP_OVERLAP",
    )


def test_direct_success_manifest_accepts_explicit_observed_warnings() -> None:
    case = load_fixture_bundle(FIXTURE).dataset.cases[4]
    without_warnings = build_success_stage_manifest(case)
    with_warning = build_success_stage_manifest(
        case,
        observed_warning_codes=("STAMP_OVERLAP",),
    )

    assert without_warnings.stages[4].warning_codes == ()
    assert with_warning.stages[4].warning_codes == ("STAMP_OVERLAP",)
    assert canonical_sha256(without_warnings) != canonical_sha256(with_warning)


@pytest.mark.parametrize("mismatch_side", ["candidate", "declaration"])
def test_stage_warning_declaration_candidate_mismatch_fails_real_runner_path(
    mismatch_side: str,
) -> None:
    payload = json.loads(FIXTURE.read_text())
    if mismatch_side == "candidate":
        payload["candidate_cases"][0]["observed_stage_warning_codes"].remove(
            "STAMP_OVERLAP"
        )
    else:
        payload["edge_matrix"][0]["expected_stage_warning_codes"].remove("STAMP_OVERLAP")

    with pytest.raises(ValueError, match="stage warnings"):
        run_synthetic_benchmark(load_fixture_bundle(payload))


def test_observed_warning_order_is_canonical_unique_and_never_emitted_on_failure_or_skip() -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["candidate_cases"][0]["observed_stage_warning_codes"].reverse()
    bundle = load_fixture_bundle(payload)
    assert bundle.candidate_cases[0].observed_stage_warning_codes == (
        "HANDWRITING_REFERENCE_ONLY",
        "LOW_CONFIDENCE",
        "STAMP_OVERLAP",
    )
    assert run_synthetic_benchmark(bundle).stage_manifests[0].stages[4].warning_codes == (
        "HANDWRITING_REFERENCE_ONLY",
        "LOW_CONFIDENCE",
        "STAMP_OVERLAP",
    )

    payload["candidate_cases"][0]["observed_stage_warning_codes"].append(
        "STAMP_OVERLAP"
    )
    with pytest.raises(ValidationError, match="unique"):
        load_fixture_bundle(payload)

    failed = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).stage_manifests[15]
    for stage_index in (0, 1):
        failed_payload = failed.model_dump(mode="json")
        failed_payload["stages"][stage_index]["warning_codes"] = ["LOW_CONFIDENCE"]
        with pytest.raises(
            ValidationError,
            match="warnings are only observable|cannot claim unobserved warnings",
        ):
            StageArtifactManifest.model_validate(failed_payload)


@pytest.mark.parametrize("case_id", ["edge-016", "edge-017"])
@pytest.mark.parametrize(
    "observed_warning_codes",
    [
        ["HANDWRITING_REFERENCE_ONLY"],
        ["LOW_CONFIDENCE"],
        ["STAMP_OVERLAP"],
        ["HANDWRITING_REFERENCE_ONLY", "LOW_CONFIDENCE"],
        ["HANDWRITING_REFERENCE_ONLY", "STAMP_OVERLAP"],
        ["LOW_CONFIDENCE", "STAMP_OVERLAP"],
        ["HANDWRITING_REFERENCE_ONLY", "LOW_CONFIDENCE", "STAMP_OVERLAP"],
    ],
)
def test_non_successful_extraction_rejects_every_non_empty_observed_warning_subset(
    case_id: str,
    observed_warning_codes: list[str],
) -> None:
    payload = json.loads(FIXTURE.read_text())
    candidate = next(
        item for item in payload["candidate_cases"] if item["case_id"] == case_id
    )
    candidate["observed_stage_warning_codes"] = observed_warning_codes

    with pytest.raises(
        ValueError,
        match="non-successful extraction cannot claim observed warnings",
    ):
        run_synthetic_benchmark(load_fixture_bundle(payload))


def test_each_edge_case_contains_its_evaluator_relevant_synthetic_signal() -> None:
    bundle = load_fixture_bundle(FIXTURE)
    keys_by_case = {
        case.case_id: {field.field_key for field in case.expected_fields}
        for case in bundle.dataset.cases
    }
    required_keys = {
        "edge-002": {"DECIMAL_AMBIGUITY_VALUE"},
        "edge-003": {"PERCENT_UNIT_MISSING_VALUE"},
        "edge-004": {"O_ZERO_AMBIGUITY", "I_L_AMBIGUITY"},
        "edge-005": {"CHEMICAL_FORMULA"},
        "edge-006": {"ALIASED_ITEM_NAME"},
        "edge-007": {"SUPPLIER_SPECIFICATION", "HYC_SPECIFICATION"},
        "edge-008": {"HYC_REQUIRED_FIELD"},
        "edge-009": {"PRODUCT_NAME", "LOT_NUMBER"},
        "edge-010": {"DUPLICATE_DOCUMENT_IDENTITY"},
        "edge-011": {"CANONICAL_LOT_ID", "INBOUND_ALLOCATION_ID"},
        "edge-012": {"SUPPLIER_RESULT", "HYC_INTERNAL_RESULT", "DEVIATION_SIGNAL"},
        "edge-014": {"QUALITATIVE_SENTENCE_RESULT"},
        "edge-015": {"HANDWRITING_DATE_REFERENCE"},
        "edge-018": {"RECEIPT_DATE", "EFFECTIVE_SPEC_VERSION"},
        "edge-019": {"FROZEN_SPEC_VERSION", "CURRENT_SPEC_VERSION"},
        "edge-020": {"ORIGINAL_DOCUMENT_LINK", "CORRECTED_DOCUMENT_LINK"},
    }
    for case_id, expected_keys in required_keys.items():
        assert keys_by_case[case_id] >= expected_keys


def test_at001_and_at004_metadata_and_source_order_are_preserved() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    at001 = next(item for item in result.candidate_artifacts if item.case_id == "edge-001")
    assert {value.field_key for value in at001.values} >= {
        "SUPPLIER_NAME",
        "PRODUCT_NAME",
        "LOT_NUMBER",
        "CALCIUM_CHLORIDE_CONTENT",
        "SUPPLIER_SPECIFICATION",
        "SUPPLIER_RESULT",
        "STAMP_OVERLAP_VALUE",
        "HANDWRITING_DATE_REFERENCE",
    }
    stamp = next(value for value in at001.values if value.field_key == "STAMP_OVERLAP_VALUE")
    handwriting = next(
        value for value in at001.values if value.field_key == "HANDWRITING_DATE_REFERENCE"
    )
    assert stamp.confidence < 1 and "LOW_CONFIDENCE" in stamp.reason_codes
    assert handwriting.handwriting_reference_only is True

    at004 = next(item for item in result.candidate_artifacts if item.case_id == "edge-013")
    five = [value for value in at004.values if value.identity.row_id == "dimension-row"]
    three = [value for value in at004.values if value.identity.row_id == "material-row"]
    assert [value.identity.sample_order for value in five] == [1, 2, 3, 4, 5]
    assert [value.identity.sample_order for value in three] == [1, 2, 3]
    assert [value.value.raw for value in five] == ["10.1", "10.2", "10.3", "10.4", "10.5"]
    assert [value.value.raw for value in three] == ["PASS", "PASS", "PASS"]


def test_runner_is_byte_deterministic_across_cwd_timezone_locale_and_has_no_external_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    bundle = load_fixture_bundle(FIXTURE)
    first = run_synthetic_benchmark(bundle, clock_tokens=FIXED_CLOCK_TOKENS)
    first_bytes = canonical_json_bytes(first)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TZ", "Pacific/Honolulu")
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: pytest.fail("network forbidden"))
    second = run_synthetic_benchmark(bundle, clock_tokens=FIXED_CLOCK_TOKENS)

    assert canonical_json_bytes(second) == first_bytes
    assert second.report_sha256 == first.report_sha256 == canonical_sha256(first.report)
    assert second.provider_name == "synthetic-fixture"

    import_graph = (
        Path(__file__).resolve().parents[2] / "src/hyc_evaluation/runner.py"
    ).read_text()
    assert "httpx" not in import_graph
    assert "requests" not in import_graph
    assert "subprocess" not in import_graph
    assert "socket" not in import_graph


def test_polygon_iou_is_decimal_evidence_without_an_invented_threshold() -> None:
    bundle = load_fixture_bundle(FIXTURE)
    result = run_synthetic_benchmark(bundle)
    case_index = next(
        index
        for index, artifact in enumerate(result.candidate_artifacts)
        if artifact.case_id == "edge-005"
    )
    payload = result.candidate_artifacts[case_index].model_dump(mode="json")
    payload["values"][0]["geometry"]["polygon"] = [
        {"x": "170", "y": "60"},
        {"x": "430", "y": "60"},
        {"x": "430", "y": "76"},
        {"x": "170", "y": "76"},
    ]
    changed = CandidateRunArtifact.model_validate(payload)
    artifacts = list(result.candidate_artifacts)
    artifacts[case_index] = changed
    report = score_candidate_runs(bundle.dataset, artifacts)
    case = next(item for item in report.cases if item.case_id == "edge-005")

    assert case.fields[0].polygon_iou == Decimal("0.3333333333333333333333333333")
    assert case.acceptance_eligible is True
    assert "IOU_THRESHOLD" not in canonical_json_bytes(report).decode()


def test_unknown_versions_and_tampered_fixture_fail_with_stable_validation() -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["dataset"]["bindings"]["provider_version"] = "9.9.9"
    with pytest.raises(ValueError, match="unsupported provider version"):
        run_synthetic_benchmark(load_fixture_bundle(payload))

    payload = json.loads(FIXTURE.read_text())
    payload["dataset"]["cases"].pop()
    with pytest.raises(ValidationError):
        load_fixture_bundle(payload)


def test_benchmark_output_digest_is_bound_and_canonical() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    restored = BenchmarkOutput.model_validate_json(canonical_json_bytes(result))
    assert restored == result

    payload = deepcopy(result.model_dump(mode="json"))
    payload["report_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        BenchmarkOutput.model_validate(payload)


def test_scorer_output_is_identical_under_ambient_decimal_precision_and_rounding() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    rendered = canonical_json_bytes(result)
    digest = canonical_sha256(result)
    report_rendered = canonical_json_bytes(result.report)
    report_digest = canonical_sha256(result.report)

    for precision in (12, 28, 50):
        for rounding in (
            ROUND_UP,
            ROUND_DOWN,
            ROUND_CEILING,
            ROUND_FLOOR,
            ROUND_HALF_EVEN,
        ):
            with localcontext() as context:
                context.prec = precision
                context.rounding = rounding
                restored = BenchmarkOutput.model_validate_json(rendered)
                assert canonical_json_bytes(restored) == rendered
                assert canonical_sha256(restored) == digest
                rescored = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
                assert canonical_json_bytes(rescored) == rendered
                assert canonical_sha256(rescored) == digest
                assert canonical_json_bytes(rescored.report) == report_rendered
                assert canonical_sha256(rescored.report) == report_digest


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["candidate_artifacts"].reverse(),
        lambda payload: payload["stage_manifests"].reverse(),
        lambda payload: payload["candidate_artifacts"].clear(),
        lambda payload: payload["candidate_artifacts"].pop(),
        lambda payload: payload["candidate_artifacts"].append(
            deepcopy(payload["candidate_artifacts"][-1])
        ),
        lambda payload: payload["candidate_artifacts"][0].update(dataset_id="foreign-dataset"),
        lambda payload: payload["candidate_artifacts"][0].update(dataset_sha256="f" * 64),
        lambda payload: payload["candidate_artifacts"][0]["values"][0]["value"].update(
            raw="digest-mismatch"
        ),
    ],
)
def test_benchmark_output_rejects_swapped_foreign_truncated_extra_and_digest_mismatch(
    mutator: object,
) -> None:
    payload = run_synthetic_benchmark(load_fixture_bundle(FIXTURE)).model_dump(mode="json")
    mutator(payload)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        BenchmarkOutput.model_validate(payload)


def test_stage_warning_and_error_sets_have_one_canonical_digest() -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    extraction = result.stage_manifests[0].stages[4]
    payload = extraction.model_dump(mode="json")
    payload["warning_codes"].reverse()
    reordered = StageArtifact.model_validate(payload)
    assert reordered.warning_codes == extraction.warning_codes
    assert canonical_sha256(reordered) == canonical_sha256(extraction)

    failed = result.stage_manifests[15].stages[0]
    failed_payload = failed.model_dump(mode="json")
    failed_payload["error_codes"] = [
        "ENCRYPTED_SYNTHETIC_INPUT",
        "CORRUPT_SYNTHETIC_INPUT",
    ]
    first = StageArtifact.model_validate(failed_payload)
    failed_payload["error_codes"].reverse()
    second = StageArtifact.model_validate(failed_payload)
    assert first.error_codes == second.error_codes
    assert canonical_sha256(first) == canonical_sha256(second)


@pytest.mark.parametrize(
    ("stage_index", "status", "errors", "warnings"),
    [
        (1, "FAILED", ["SCHEMA_VALIDATION_FAILED"], []),
        (6, "FAILED", ["LOGIC_VALIDATION_FAILED"], []),
        (7, "FAILED", ["UPLOAD_READ_RACE"], []),
        (
            6,
            "FAILED",
            ["SCHEMA_VALIDATION_FAILED", "SKIPPED_UPSTREAM_FAILURE"],
            [],
        ),
        (5, "SKIPPED_UPSTREAM_FAILURE", ["SKIPPED_UPSTREAM_FAILURE"], ["LOW_CONFIDENCE"]),
    ],
)
def test_stage_error_compatibility_matrix_rejects_incompatible_codes(
    stage_index: int,
    status: str,
    errors: list[str],
    warnings: list[str],
) -> None:
    result = run_synthetic_benchmark(load_fixture_bundle(FIXTURE))
    payload = result.stage_manifests[0].stages[stage_index].model_dump(mode="json")
    payload.update(status=status, error_codes=errors, warning_codes=warnings)
    with pytest.raises(ValidationError):
        StageArtifact.model_validate(payload)


def test_p4a_limit_is_a_closed_literal_contract() -> None:
    payload = json.loads(FIXTURE.read_text())
    payload["edge_matrix"][0]["p4a_limit"] = "FULL_WORKFLOW_IMPLEMENTED"
    with pytest.raises(ValidationError):
        load_fixture_bundle(payload)
