from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NORMALIZATION_VOCABULARY_VERSION = "hyc.normalization.v1"

type NormalizationId = Literal[
    "identity",
    "decimal.canonical",
    "date.iso8601",
    "lot.trim-upper",
    "text.nfkc",
    "text.trim",
    "text.upper",
    "unit.alias",
]
NORMALIZATION_VOCABULARY_BINDINGS: tuple[tuple[NormalizationId, Literal["1.0"]], ...] = (
    ("identity", "1.0"),
    ("decimal.canonical", "1.0"),
    ("date.iso8601", "1.0"),
    ("lot.trim-upper", "1.0"),
    ("text.nfkc", "1.0"),
    ("text.trim", "1.0"),
    ("text.upper", "1.0"),
    ("unit.alias", "1.0"),
)


class NormalizationBinding(BaseModel):
    """One explicitly approved normalization and its immutable version."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    normalization_id: NormalizationId
    normalization_version: Literal["1.0"]


NormalizationSequence = Annotated[list[NormalizationBinding], Field(min_length=1)]


class VersionedNormalizationVocabulary(BaseModel):
    """Fail-closed vocabulary declaration embedded in a golden dataset."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    vocabulary_version: Literal["hyc.normalization.v1"]
    normalizations: NormalizationSequence

    @model_validator(mode="after")
    def reject_vocabulary_drift(self) -> VersionedNormalizationVocabulary:
        identities = tuple(
            (binding.normalization_id, binding.normalization_version)
            for binding in self.normalizations
        )
        if identities != NORMALIZATION_VOCABULARY_BINDINGS:
            raise ValueError("normalization vocabulary must exactly match its version")
        return self
