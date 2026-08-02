"""Offline, synthetic-only evaluation contracts."""

from hyc_evaluation.artifacts import (
    CandidateRunArtifact,
    GoldenEvaluationReport,
    StageArtifact,
    StageArtifactManifest,
    canonical_json_bytes,
    canonical_sha256,
)
from hyc_evaluation.fixture import SyntheticEdgeRecord, SyntheticFixtureBundle
from hyc_evaluation.local_pilot import (
    LocalPilotAssessment,
    LocalPilotDocument,
    LocalPilotManifest,
    PublicPilotAggregate,
    assess_local_pilot_manifest,
    build_public_pilot_aggregate,
    local_pilot_binding_sha256,
)
from hyc_evaluation.normalization import (
    NORMALIZATION_VOCABULARY_BINDINGS,
    NORMALIZATION_VOCABULARY_VERSION,
    NormalizationBinding,
    VersionedNormalizationVocabulary,
)
from hyc_evaluation.preflight import (
    EvidenceMetadata,
    PreflightDecision,
    ProviderPreflightPolicy,
    SyntheticDryRunDescriptor,
    evaluate_provider_preflight,
    evidence_binding_sha256,
)
from hyc_evaluation.runner import BenchmarkOutput, load_fixture_bundle, run_synthetic_benchmark
from hyc_evaluation.schema import GoldenDataset
from hyc_evaluation.scoring import score_candidate_runs

__all__ = [
    "NORMALIZATION_VOCABULARY_VERSION",
    "NORMALIZATION_VOCABULARY_BINDINGS",
    "CandidateRunArtifact",
    "GoldenDataset",
    "GoldenEvaluationReport",
    "EvidenceMetadata",
    "LocalPilotAssessment",
    "LocalPilotDocument",
    "LocalPilotManifest",
    "NormalizationBinding",
    "PreflightDecision",
    "ProviderPreflightPolicy",
    "PublicPilotAggregate",
    "StageArtifact",
    "StageArtifactManifest",
    "SyntheticEdgeRecord",
    "SyntheticFixtureBundle",
    "SyntheticDryRunDescriptor",
    "BenchmarkOutput",
    "VersionedNormalizationVocabulary",
    "canonical_json_bytes",
    "canonical_sha256",
    "assess_local_pilot_manifest",
    "build_public_pilot_aggregate",
    "evidence_binding_sha256",
    "evaluate_provider_preflight",
    "load_fixture_bundle",
    "run_synthetic_benchmark",
    "score_candidate_runs",
    "local_pilot_binding_sha256",
]
