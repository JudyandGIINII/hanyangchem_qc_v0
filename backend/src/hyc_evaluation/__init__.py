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
from hyc_evaluation.normalization import (
    NORMALIZATION_VOCABULARY_BINDINGS,
    NORMALIZATION_VOCABULARY_VERSION,
    NormalizationBinding,
    VersionedNormalizationVocabulary,
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
    "NormalizationBinding",
    "StageArtifact",
    "StageArtifactManifest",
    "SyntheticEdgeRecord",
    "SyntheticFixtureBundle",
    "BenchmarkOutput",
    "VersionedNormalizationVocabulary",
    "canonical_json_bytes",
    "canonical_sha256",
    "load_fixture_bundle",
    "run_synthetic_benchmark",
    "score_candidate_runs",
]
