from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from uuid import NAMESPACE_URL, uuid5

from pydantic import Field, field_validator, model_validator

from hyc_api.contracts import BoundingBox, ExtractionCandidate, ExtractionValue, SourceReference
from hyc_api.extraction import ExtractionProvider
from hyc_evaluation.artifacts import (
    STAGE_ORDER,
    ArtifactModel,
    CandidateRunArtifact,
    GoldenEvaluationReport,
    StageArtifact,
    StageArtifactManifest,
    StageErrorCode,
    StageName,
    StageStatus,
    StageWarningCode,
    canonical_json_bytes,
    canonical_sha256,
)
from hyc_evaluation.fixture import (
    SyntheticCandidateCase,
    SyntheticEdgeRecord,
    SyntheticFixtureBundle,
)
from hyc_evaluation.schema import GoldenCase
from hyc_evaluation.scoring import score_candidate_runs

FIXED_CLOCK_TOKENS = tuple(f"clock-{index:04d}" for index in range(1, 9))
SUPPORTED_VERSION = "1.0.0"


class DeterministicSyntheticFixtureProvider:
    """Deterministic adapter for the existing synthetic-only extraction port."""

    def extract(
        self,
        document_id: str,
        source_reference: str,
        *,
        document_bytes: bytes | None = None,
    ) -> ExtractionCandidate:
        del document_bytes
        stable_document_id = uuid5(NAMESPACE_URL, f"hyc:{document_id}")
        reference = SourceReference(
            document_id=stable_document_id,
            source_reference=source_reference,
            page_number=1,
            bbox=BoundingBox(left=0.0, top=0.0, right=1.0, bottom=1.0),
        )
        return ExtractionCandidate(
            schema_version="1.0",
            candidate_id=uuid5(NAMESPACE_URL, f"hyc:{document_id}:candidate"),
            created_at=datetime(2026, 8, 2, tzinfo=UTC),
            document=reference,
            provider_name="synthetic-fixture",
            values=[
                ExtractionValue(
                    item_key="SYNTHETIC_VALUE",
                    raw_text="GENERATED_NON_SENSITIVE_SYNTHETIC",
                    normalized_value=Decimal("1"),
                    provenance=reference,
                    confidence=1.0,
                    review_required=False,
                )
            ],
            review_required=False,
        )


class BenchmarkOutput(ArtifactModel):
    output_schema_version: Literal["hyc.benchmark-output.v1"]
    provider_name: Literal["synthetic-fixture"]
    dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    stage_manifests: tuple[StageArtifactManifest, ...]
    candidate_artifacts: tuple[CandidateRunArtifact, ...]
    report: GoldenEvaluationReport
    report_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("stage_manifests", "candidate_artifacts", mode="before")
    @classmethod
    def freeze_sequences(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def bind_all_digests_and_order(self) -> BenchmarkOutput:
        if self.dataset_sha256 != self.report.dataset_sha256:
            raise ValueError("benchmark dataset digest must match report")
        if self.report_sha256 != canonical_sha256(self.report):
            raise ValueError("benchmark report digest must match canonical report")
        candidate_case_ids = tuple(item.case_id for item in self.candidate_artifacts)
        report_case_ids = tuple(item.case_id for item in self.report.cases)
        if len(self.candidate_artifacts) != len(self.report.cases):
            raise ValueError("benchmark candidates must match report cardinality")
        if candidate_case_ids != report_case_ids:
            raise ValueError("benchmark candidate order must match report case order")
        if tuple(item.case_id for item in self.stage_manifests) != candidate_case_ids:
            raise ValueError("stage and candidate case order must match")
        if tuple(canonical_sha256(item) for item in self.stage_manifests) != tuple(
            item.stage_manifest_sha256 for item in self.candidate_artifacts
        ):
            raise ValueError("candidate artifacts must bind their exact stage manifests")
        candidate_digests = tuple(canonical_sha256(item) for item in self.candidate_artifacts)
        if candidate_digests != self.report.candidate_artifact_sha256:
            raise ValueError("benchmark candidates must bind exact report artifact digests")
        if tuple(canonical_sha256(item) for item in self.stage_manifests) != (
            self.report.stage_manifest_sha256
        ):
            raise ValueError("benchmark stages must bind exact report manifest digests")
        for candidate, case in zip(
            self.candidate_artifacts, self.report.cases, strict=True
        ):
            if (
                candidate.provider_name != self.provider_name
                or candidate.dataset_id != self.report.dataset_id
                or candidate.dataset_version != self.report.dataset_version
                or candidate.dataset_sha256 != self.dataset_sha256
                or candidate.golden_schema_version != self.report.golden_schema_version
                or candidate.bindings != self.report.bindings
                or candidate.case_id != case.case_id
                or candidate.input_sha256 != case.input_sha256
            ):
                raise ValueError("benchmark candidate bindings must match report exactly")
        return self


def load_fixture_bundle(
    source: Path | str | Mapping[str, Any],
) -> SyntheticFixtureBundle:
    if isinstance(source, Mapping):
        payload: Any = dict(source)
    else:
        fixture_path = Path(source)
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    return SyntheticFixtureBundle.model_validate(payload)


def _stage_failure(edge: SyntheticEdgeRecord) -> tuple[StageName | None, StageErrorCode | None]:
    return edge.failure_stage, edge.failure_code


def _make_stage_manifest(
    case: GoldenCase,
    edge: SyntheticEdgeRecord,
    provider_candidate: ExtractionCandidate,
    observed_warning_codes: tuple[StageWarningCode, ...],
    clock_tokens: tuple[str, ...],
) -> StageArtifactManifest:
    if len(clock_tokens) != len(STAGE_ORDER) or len(clock_tokens) != len(set(clock_tokens)):
        raise ValueError("clock tokens must provide eight unique deterministic values")
    if len(observed_warning_codes) != len(set(observed_warning_codes)):
        raise ValueError("observed stage warning codes must be unique")
    canonical_observed_warnings = tuple(sorted(observed_warning_codes))
    failure_stage, failure_code = _stage_failure(edge)
    extraction_index = STAGE_ORDER.index("SYNTHETIC_FIXTURE_EXTRACTION")
    extraction_will_succeed = failure_stage is None or (
        STAGE_ORDER.index(failure_stage) > extraction_index
    )
    if canonical_observed_warnings and not extraction_will_succeed:
        raise ValueError("non-successful extraction cannot claim observed warnings")
    input_ref = f"synthetic-input:{case.case_id}"
    previous_ref = input_ref
    previous_digest = case.input.source_sha256
    upstream_failed = False
    stages: list[StageArtifact] = []
    provider_digest = canonical_sha256(provider_candidate)
    for index, (stage_name, clock_token) in enumerate(
        zip(STAGE_ORDER, clock_tokens, strict=True), start=1
    ):
        artifact_ref = f"{case.case_id}:stage:{index:02d}"
        if upstream_failed:
            status: StageStatus = "SKIPPED_UPSTREAM_FAILURE"
            errors: tuple[StageErrorCode, ...] = ("SKIPPED_UPSTREAM_FAILURE",)
        elif stage_name == failure_stage:
            status = "FAILED"
            if failure_code is None:
                raise ValueError("failure stage requires a structured failure code")
            errors = (failure_code,)
            upstream_failed = True
        else:
            status = "SUCCESS"
            errors = ()
        warnings = (
            canonical_observed_warnings
            if stage_name == "SYNTHETIC_FIXTURE_EXTRACTION" and status == "SUCCESS"
            else ()
        )
        output_sha256 = canonical_sha256(
            {
                "case_id": case.case_id,
                "stage_name": stage_name,
                "stage_order": index,
                "status": status,
                "input_ref": previous_ref,
                "input_sha256": previous_digest,
                "provider_candidate_sha256": (
                    provider_digest if stage_name == "SYNTHETIC_FIXTURE_EXTRACTION" else None
                ),
                "warning_codes": warnings,
                "error_codes": errors,
            }
        )
        stages.append(
            StageArtifact(
                stage_schema_version="hyc.stage-artifact.v1",
                artifact_ref=artifact_ref,
                stage_name=stage_name,
                stage_version=SUPPORTED_VERSION,
                stage_order=index,
                ordering_marker=f"order-{index:04d}",
                stable_clock_marker=clock_token,
                input_refs=(previous_ref,),
                input_digests=(previous_digest,),
                output_sha256=output_sha256,
                upstream_artifact_refs=() if index == 1 else (previous_ref,),
                status=status,
                warning_codes=warnings,
                error_codes=errors,
            )
        )
        previous_ref = artifact_ref
        previous_digest = output_sha256
    return StageArtifactManifest(
        manifest_schema_version="hyc.stage-manifest.v1",
        case_id=case.case_id,
        input_ref=input_ref,
        input_sha256=case.input.source_sha256,
        stages=tuple(stages),
    )


def build_success_stage_manifest(
    case: GoldenCase,
    *,
    observed_warning_codes: tuple[StageWarningCode, ...] = (),
    clock_tokens: tuple[str, ...] = FIXED_CLOCK_TOKENS,
) -> StageArtifactManifest:
    """Build the same deterministic successful chain used by fixture-run tests."""

    edge = SyntheticEdgeRecord(
        edge_id="P4-EDGE-001",
        prd_edge_number=1,
        title="synthetic successful stage test",
        synthetic_fixture_ref="p4a_edge_dataset.v1.json",
        case_id=case.case_id,
        expected_value_or_failure="SYNTHETIC_SUCCESS",
        expected_confidence=Decimal("1"),
        expected_reason_codes=(),
        expected_stage_warning_codes=(),
        expected_disposition="CANDIDATE_ONLY",
        owner_phase="P4-A",
        executable_test_path="backend/tests/golden/test_artifacts_and_scoring.py",
        p4a_signal="Deterministic successful stage chain",
        p4a_limit="OFFLINE_SYNTHETIC_ONLY_NO_REAL_CORPUS_OR_PROVIDER",
        failure_stage=None,
        failure_code=None,
    )
    provider = DeterministicSyntheticFixtureProvider()
    provider_candidate = provider.extract(case.case_id, f"synthetic://generated/{case.case_id}")
    return _make_stage_manifest(
        case,
        edge,
        provider_candidate,
        observed_warning_codes,
        clock_tokens,
    )


def _candidate_for(
    bundle: SyntheticFixtureBundle,
    case: GoldenCase,
    edge: SyntheticEdgeRecord,
    candidate_case: SyntheticCandidateCase,
    provider: ExtractionProvider,
    clock_tokens: tuple[str, ...],
) -> CandidateRunArtifact:
    source_reference = f"synthetic://generated/{case.case_id}"
    provider_candidate = provider.extract(case.case_id, source_reference)
    if provider_candidate.provider_name != "synthetic-fixture":
        raise ValueError("unsupported provider identity")
    manifest = _make_stage_manifest(
        case,
        edge,
        provider_candidate,
        candidate_case.observed_stage_warning_codes,
        clock_tokens,
    )
    stage_failed = any(stage.status != "SUCCESS" for stage in manifest.stages)
    if candidate_case.case_id != case.case_id:
        raise ValueError("candidate fixture case must match golden case")
    values = list(candidate_case.values) if not stage_failed else []
    run_reasons = {reason for value in values for reason in value.reason_codes}
    if stage_failed:
        run_reasons.add("UPSTREAM_FAILURE")
    review_required = bool(run_reasons)
    manifest_digest = canonical_sha256(manifest)
    return CandidateRunArtifact(
        artifact_schema_version="hyc.candidate-run.v1",
        golden_schema_version=bundle.dataset.golden_schema_version,
        dataset_id=bundle.dataset.dataset_id,
        dataset_version=bundle.dataset.dataset_version,
        dataset_sha256=canonical_sha256(bundle.dataset),
        case_id=case.case_id,
        input_sha256=case.input.source_sha256,
        provider_name="synthetic-fixture",
        document_kind=case.input.document_kind,
        bindings=bundle.dataset.bindings,
        stage_manifest=manifest,
        stage_manifest_sha256=manifest_digest,
        final_stage_artifact_ref=manifest.stages[-1].artifact_ref,
        values=tuple(values),
        reason_codes=tuple(run_reasons),
        review_required=review_required,
        escalation_required=review_required,
    )


def _validate_supported_bindings(bundle: SyntheticFixtureBundle) -> None:
    bindings = bundle.dataset.bindings
    if bindings.provider_name != "synthetic-fixture":
        raise ValueError("unsupported provider identity")
    if bindings.provider_version != SUPPORTED_VERSION:
        raise ValueError("unsupported provider version")
    checked = {
        "fixture": bindings.fixture_version,
        "parser": bindings.parser_version,
        "pipeline": bindings.pipeline_version,
        "stage contract": bindings.stage_contract_version,
        "runner": bindings.runner_version,
        "scorer": bindings.scorer_version,
        "report": bindings.report_version,
    }
    unknown = [name for name, version in checked.items() if version != SUPPORTED_VERSION]
    if unknown:
        raise ValueError(f"unsupported version binding: {', '.join(unknown)}")


def _validate_edge_dispositions(
    bundle: SyntheticFixtureBundle,
    report: GoldenEvaluationReport,
) -> None:
    for edge, case in zip(bundle.edge_matrix, report.cases, strict=True):
        if case.reason_codes != edge.expected_reason_codes:
            raise ValueError(
                f"{edge.edge_id} executable reasons do not match its declared contract"
            )
        reasons = set(case.reason_codes)
        if not reasons:
            actual_disposition = "CANDIDATE_ONLY"
            valid_state = not case.review_required and case.acceptance_eligible
        elif "UPSTREAM_FAILURE" in reasons:
            actual_disposition = "STABLE_FAILURE"
            valid_state = case.review_required and not case.acceptance_eligible
        elif "MISSING_REQUIRED" in reasons:
            actual_disposition = "MANUAL_FALLBACK"
            valid_state = case.review_required and not case.acceptance_eligible
        else:
            actual_disposition = "REVIEW_REQUIRED"
            valid_state = case.review_required and not case.acceptance_eligible
        if not valid_state or edge.expected_disposition != actual_disposition:
            raise ValueError(
                f"{edge.edge_id} outcome contradicts expected disposition "
                f"{edge.expected_disposition}; executable disposition is "
                f"{actual_disposition}"
            )


def _validate_stage_warnings(
    bundle: SyntheticFixtureBundle,
    candidates: tuple[CandidateRunArtifact, ...],
) -> None:
    for edge, candidate in zip(bundle.edge_matrix, candidates, strict=True):
        extraction = next(
            stage
            for stage in candidate.stage_manifest.stages
            if stage.stage_name == "SYNTHETIC_FIXTURE_EXTRACTION"
        )
        if extraction.warning_codes != edge.expected_stage_warning_codes:
            raise ValueError(
                f"{edge.edge_id} observed stage warnings do not match its declared contract"
            )


def run_synthetic_benchmark(
    bundle: SyntheticFixtureBundle,
    *,
    clock_tokens: tuple[str, ...] = FIXED_CLOCK_TOKENS,
) -> BenchmarkOutput:
    _validate_supported_bindings(bundle)
    provider: ExtractionProvider = DeterministicSyntheticFixtureProvider()
    candidates = tuple(
        _candidate_for(bundle, case, edge, candidate_case, provider, clock_tokens)
        for case, edge, candidate_case in zip(
            bundle.dataset.cases,
            bundle.edge_matrix,
            bundle.candidate_cases,
            strict=True,
        )
    )
    _validate_stage_warnings(bundle, candidates)
    report = score_candidate_runs(bundle.dataset, candidates)
    _validate_edge_dispositions(bundle, report)
    return BenchmarkOutput(
        output_schema_version="hyc.benchmark-output.v1",
        provider_name="synthetic-fixture",
        dataset_sha256=canonical_sha256(bundle.dataset),
        stage_manifests=tuple(candidate.stage_manifest for candidate in candidates),
        candidate_artifacts=candidates,
        report=report,
        report_sha256=canonical_sha256(report),
    )


def write_benchmark_output(output: BenchmarkOutput, output_path: Path) -> None:
    output_path.write_bytes(canonical_json_bytes(output) + b"\n")
