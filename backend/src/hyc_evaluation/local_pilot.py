"""Pure local-pilot metadata contracts and non-reversible public aggregates.

The models intentionally bind caller-supplied evidence but never discover, open, or
transmit a document or evidence artifact.  A binding proves only structural
consistency of supplied metadata; it cannot establish that a caller told the truth.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Annotated, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from hyc_evaluation.schema import Identifier

SHA256_PATTERN = r"^[0-9a-f]{64}$"
PUBLIC_DISCLOSURE_THRESHOLD = 3

_PROHIBITED_PUBLIC_KEYS = (
    "body_bytes",
    "credential",
    "file_name",
    "filename",
    "filesystem_path",
    "ocr_payload",
    "path",
    "raw_ocr",
    "raw_value",
    "source_body",
    "source_hash",
    "source_sha256",
    "token",
    "uri",
    "url",
)
_PROHIBITED_PUBLIC_VALUE_PATTERN = (
    r"(?ix)(?:^[0-9a-f]{64}$|^[a-z][a-z0-9+.-]*:|^(?:/|\./|\.\./|~[/\\]|[a-z]:[/\\])|[/\\]|"
    r"\b[^/\\\s]+\.(?:csv|docx?|hwp|hwpx|jpe?g|pdf|png|pptx?|tiff?|xls[mbx]?)\b|"
    r"\braw[\s_-]*(?:document[\s_-]*)?(?:ocr|value|payload)\b|\bocr[\s_-]*payload\b|"
    r"\bbearer\b)"
)


def validate_public_safe_tree(value: object) -> object:
    """Reject public-contract keys and arbitrary values that resemble protected data.

    Typed public status/reason fields are validated by their own Literal contracts;
    this generic guard therefore does not maintain a string exemption allowlist.
    """

    def visit(item: object) -> None:
        if isinstance(item, Mapping):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("public output keys must be strings")
                normalized = key.casefold().replace("-", "_")
                if any(marker in normalized for marker in _PROHIBITED_PUBLIC_KEYS):
                    raise ValueError("public output contains a prohibited key")
                visit(child)
        elif isinstance(item, str):
            normalized = re.sub(r"[_-]+", " ", item.casefold())
            if re.search(_PROHIBITED_PUBLIC_VALUE_PATTERN, item) or re.search(
                r"\b(?:token)\b", normalized
            ):
                raise ValueError("public output contains a prohibited value")
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)):
            for child in item:
                visit(child)

    visit(value)
    return value


class LocalPilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)


type DocumentClassification = Literal["CONFIDENTIAL", "INTERNAL_RESTRICTED"]
type PilotDocumentKind = Literal["SUPPLIER_COA", "SUPPLIER_INSPECTION_REPORT"]
type LayoutTrait = Literal["FORM", "MIXED", "TABULAR"]
type LanguageTrait = Literal["ENGLISH", "KOREAN", "MIXED_KOREAN_ENGLISH"]
type ScanTrait = Literal["DIGITAL_TEXT", "SCANNED", "SKEWED", "LOW_CONTRAST"]
type PilotErrorCategory = Literal[
    "DOCUMENT_CONTRACT_ERROR",
    "LABEL_CONTRACT_ERROR",
    "MANUAL_REVIEW_REQUIRED",
    "UNSUPPORTED_LAYOUT",
]
type PublicAggregateCategory = Literal[
    "CONFIDENTIAL",
    "INTERNAL_RESTRICTED",
    "SUPPLIER_COA",
    "SUPPLIER_INSPECTION_REPORT",
    "ELIGIBLE",
    "INELIGIBLE",
    "DOCUMENT_CONTRACT_ERROR",
    "LABEL_CONTRACT_ERROR",
    "MANUAL_REVIEW_REQUIRED",
    "UNSUPPORTED_LAYOUT",
    "FORM",
    "MIXED",
    "TABULAR",
    "ENGLISH",
    "KOREAN",
    "MIXED_KOREAN_ENGLISH",
    "DIGITAL_TEXT",
    "SCANNED",
    "SKEWED",
    "LOW_CONTRAST",
]
type LocalEvidenceOrigin = Literal["LOCAL_HUMAN", "GENERATED_SYNTHETIC"]
type LocalPilotStatus = Literal[
    "INSUFFICIENT_ELIGIBLE_CORPUS",
    "HUMAN_EVIDENCE_REQUIRED",
    "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY",
]


def local_pilot_binding_sha256(
    *,
    document_schema_version: str,
    source_sha256: str,
    label_artifact_sha256: str,
    review_artifact_sha256: str,
    classification: DocumentClassification,
    document_kind: PilotDocumentKind,
    layout_traits: tuple[LayoutTrait, ...],
    language_traits: tuple[LanguageTrait, ...],
    scan_traits: tuple[ScanTrait, ...],
    label_schema_version: str,
    opaque_source_id: str,
    label_author_ref: str,
    independent_reviewer_ref: str,
    label_authored_on: date,
    label_reviewed_on: date,
    evidence_origin: LocalEvidenceOrigin,
    label_authorship: Literal["HUMAN_AUTHORED", "GENERATED_SYNTHETIC"],
    label_review_state: Literal["HUMAN_REVIEWED", "GENERATED_SYNTHETIC_UNREVIEWED"],
    eligibility_status: Literal["ELIGIBLE", "INELIGIBLE"],
    error_categories: tuple[PilotErrorCategory, ...],
) -> str:
    """SHA-256 of UTF-8 JSON with sorted keys and compact separators.

    The compact, sorted preimage includes the source, label and review artifact
    identifiers plus every document field that drives the public aggregate and every
    local human-authorship and review declaration. Tuple categories are sorted in
    the preimage. This is a deterministic binding, not a provenance claim.
    """
    preimage = {
        "label_artifact_sha256": label_artifact_sha256,
        "label_authored_on": label_authored_on.isoformat(),
        "label_author_ref": label_author_ref,
        "label_authorship": label_authorship,
        "label_schema_version": label_schema_version,
        "label_reviewed_on": label_reviewed_on.isoformat(),
        "label_review_state": label_review_state,
        "evidence_origin": evidence_origin,
        "classification": classification,
        "document_kind": document_kind,
        "document_schema_version": document_schema_version,
        "eligibility_status": eligibility_status,
        "error_categories": sorted(error_categories),
        "independent_reviewer_ref": independent_reviewer_ref,
        "language_traits": sorted(language_traits),
        "layout_traits": sorted(layout_traits),
        "opaque_source_id": opaque_source_id,
        "review_artifact_sha256": review_artifact_sha256,
        "scan_traits": sorted(scan_traits),
        "source_sha256": source_sha256,
    }
    return hashlib.sha256(
        json.dumps(preimage, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()


class LocalPilotDocument(LocalPilotModel):
    document_schema_version: Literal["hyc.local-pilot-document.v1"]
    opaque_source_id: Identifier
    source_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    classification: DocumentClassification
    document_kind: PilotDocumentKind
    layout_traits: tuple[LayoutTrait, ...]
    language_traits: tuple[LanguageTrait, ...]
    scan_traits: tuple[ScanTrait, ...]
    evidence_origin: LocalEvidenceOrigin
    label_schema_version: Annotated[str, Field(pattern=r"^hyc\.local-label\.v[1-9][0-9]*$")]
    label_authorship: Literal["HUMAN_AUTHORED", "GENERATED_SYNTHETIC"]
    label_author_ref: Identifier
    label_artifact_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    label_authored_on: date
    label_review_state: Literal["HUMAN_REVIEWED", "GENERATED_SYNTHETIC_UNREVIEWED"]
    independent_reviewer_ref: Identifier
    review_artifact_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    label_reviewed_on: date
    evidence_binding_sha256: Annotated[str, Field(pattern=SHA256_PATTERN)]
    eligibility_status: Literal["ELIGIBLE", "INELIGIBLE"]
    error_categories: tuple[PilotErrorCategory, ...]

    @field_validator(
        "opaque_source_id", "label_author_ref", "independent_reviewer_ref", mode="after"
    )
    @classmethod
    def reject_filename_or_path_references(cls, value: str) -> str:
        validate_public_safe_tree(value)
        return value

    @field_validator(
        "layout_traits", "language_traits", "scan_traits", "error_categories", mode="before"
    )
    @classmethod
    def freeze_and_order_categories(cls, value: object) -> object:
        if isinstance(value, (list, tuple)):
            if len(value) != len(set(value)):
                raise ValueError("local pilot categorical metadata must be unique")
            return tuple(sorted(value))
        return value

    @model_validator(mode="after")
    def bind_evidence_and_fail_closed(self) -> LocalPilotDocument:
        if self.label_author_ref == self.independent_reviewer_ref:
            raise ValueError("label author and independent reviewer must be distinct")
        if self.label_artifact_sha256 == self.review_artifact_sha256:
            raise ValueError("label and review artifact digests must be distinct")
        if self.label_reviewed_on < self.label_authored_on:
            raise ValueError("label review date cannot precede authored date")
        if self.evidence_origin == "LOCAL_HUMAN":
            if (
                self.label_authorship != "HUMAN_AUTHORED"
                or self.label_review_state != "HUMAN_REVIEWED"
            ):
                raise ValueError(
                    "local human evidence requires authored and independently reviewed declarations"
                )
        elif (
            self.label_authorship != "GENERATED_SYNTHETIC"
            or self.label_review_state != "GENERATED_SYNTHETIC_UNREVIEWED"
        ):
            raise ValueError("generated evidence must be explicitly synthetic and unreviewed")
        expected = local_pilot_binding_sha256(
            document_schema_version=self.document_schema_version,
            source_sha256=self.source_sha256,
            label_artifact_sha256=self.label_artifact_sha256,
            review_artifact_sha256=self.review_artifact_sha256,
            classification=self.classification,
            document_kind=self.document_kind,
            layout_traits=self.layout_traits,
            language_traits=self.language_traits,
            scan_traits=self.scan_traits,
            label_schema_version=self.label_schema_version,
            opaque_source_id=self.opaque_source_id,
            label_author_ref=self.label_author_ref,
            independent_reviewer_ref=self.independent_reviewer_ref,
            label_authored_on=self.label_authored_on,
            label_reviewed_on=self.label_reviewed_on,
            evidence_origin=self.evidence_origin,
            label_authorship=self.label_authorship,
            label_review_state=self.label_review_state,
            eligibility_status=self.eligibility_status,
            error_categories=self.error_categories,
        )
        if self.evidence_binding_sha256 != expected:
            raise ValueError("local pilot evidence binding digest mismatch")
        if self.eligibility_status == "INELIGIBLE" and not self.error_categories:
            raise ValueError("ineligible local pilot documents require a coarse error category")
        return self


class LocalPilotManifest(LocalPilotModel):
    manifest_schema_version: Literal["hyc.local-pilot-manifest.v1"]
    manifest_id: Identifier
    representativeness_status: Literal["NON_REPRESENTATIVE"]
    release_gate_eligible: Literal[False]
    transmission_authorized: Literal[False]
    ap02_approval_status: Literal["NOT_APPROVED"]
    documents: tuple[LocalPilotDocument, ...]

    @field_validator("manifest_id", mode="after")
    @classmethod
    def reject_filename_or_path_manifest_id(cls, value: str) -> str:
        validate_public_safe_tree(value)
        return value

    @field_validator("documents", mode="before")
    @classmethod
    def freeze_documents(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_unique_evidence_references(self) -> LocalPilotManifest:
        artifact_digests = tuple(
            digest
            for item in self.documents
            for digest in (item.label_artifact_sha256, item.review_artifact_sha256)
        )
        if len(artifact_digests) != len(set(artifact_digests)):
            raise ValueError(
                "local pilot label and review artifact digests must be globally unique"
            )
        for values in (
            tuple(item.opaque_source_id for item in self.documents),
            tuple(item.source_sha256 for item in self.documents),
            tuple(item.label_artifact_sha256 for item in self.documents),
            tuple(item.review_artifact_sha256 for item in self.documents),
            tuple(item.evidence_binding_sha256 for item in self.documents),
        ):
            if len(values) != len(set(values)):
                raise ValueError("local pilot evidence references and digests must be unique")
        return self


class LocalPilotAssessment(LocalPilotModel):
    assessment_schema_version: Literal["hyc.local-pilot-assessment.v1"]
    status: LocalPilotStatus
    total_document_count: Annotated[int, Field(ge=0)]
    eligible_document_count: Annotated[int, Field(ge=0)]
    representativeness_status: Literal["NON_REPRESENTATIVE"]
    release_gate_eligible: Literal[False]
    human_review_required: Literal[True]
    transmission_authorized: Literal[False]


def assess_local_pilot_manifest(manifest: LocalPilotManifest) -> LocalPilotAssessment:
    eligible = sum(item.eligibility_status == "ELIGIBLE" for item in manifest.documents)
    human_evidenced = all(
        item.evidence_origin == "LOCAL_HUMAN"
        and item.label_authorship == "HUMAN_AUTHORED"
        and item.label_review_state == "HUMAN_REVIEWED"
        for item in manifest.documents
    )
    status: LocalPilotStatus = (
        "INSUFFICIENT_ELIGIBLE_CORPUS"
        if eligible == 0
        else "HUMAN_EVIDENCE_REQUIRED"
        if not human_evidenced
        else "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY"
    )
    return LocalPilotAssessment(
        assessment_schema_version="hyc.local-pilot-assessment.v1",
        status=status,
        total_document_count=len(manifest.documents),
        eligible_document_count=eligible,
        representativeness_status="NON_REPRESENTATIVE",
        release_gate_eligible=False,
        human_review_required=True,
        transmission_authorized=False,
    )


class PublicPilotModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, validate_default=True)

    @model_validator(mode="before")
    @classmethod
    def reject_protected_material(cls, value: object) -> object:
        return validate_public_safe_tree(value)


type AggregateDimensionName = Literal[
    "CLASSIFICATION",
    "DOCUMENT_KIND",
    "ELIGIBILITY_STATUS",
    "ERROR_CATEGORY",
    "LAYOUT_TRAIT",
    "LANGUAGE_TRAIT",
    "SCAN_TRAIT",
]
type CohortSizeBucket = Literal["LT_3", "3_TO_9", "10_PLUS"]
type PublicAggregateStatus = Literal[
    "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY",
    "HUMAN_EVIDENCE_REQUIRED",
    "INSUFFICIENT_ELIGIBLE_CORPUS",
]


class PublicAggregateCell(PublicPilotModel):
    category: PublicAggregateCategory
    count: Annotated[int, Field(ge=PUBLIC_DISCLOSURE_THRESHOLD)]


class PublicAggregateDimension(PublicPilotModel):
    dimension: AggregateDimensionName
    visible_cells: tuple[PublicAggregateCell, ...]
    suppression_applied: bool

    @field_validator("visible_cells", mode="before")
    @classmethod
    def freeze_cells(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_canonical_cell_order(self) -> PublicAggregateDimension:
        categories = tuple(cell.category for cell in self.visible_cells)
        if categories != tuple(sorted(categories)) or len(categories) != len(set(categories)):
            raise ValueError("public aggregate cells must be unique and canonically ordered")
        expected_categories: dict[AggregateDimensionName, frozenset[PublicAggregateCategory]] = {
            "CLASSIFICATION": frozenset(("CONFIDENTIAL", "INTERNAL_RESTRICTED")),
            "DOCUMENT_KIND": frozenset(("SUPPLIER_COA", "SUPPLIER_INSPECTION_REPORT")),
            "ELIGIBILITY_STATUS": frozenset(("ELIGIBLE", "INELIGIBLE")),
            "ERROR_CATEGORY": frozenset(
                (
                    "DOCUMENT_CONTRACT_ERROR",
                    "LABEL_CONTRACT_ERROR",
                    "MANUAL_REVIEW_REQUIRED",
                    "UNSUPPORTED_LAYOUT",
                )
            ),
            "LAYOUT_TRAIT": frozenset(("FORM", "MIXED", "TABULAR")),
            "LANGUAGE_TRAIT": frozenset(("ENGLISH", "KOREAN", "MIXED_KOREAN_ENGLISH")),
            "SCAN_TRAIT": frozenset(("DIGITAL_TEXT", "SCANNED", "SKEWED", "LOW_CONTRAST")),
        }
        if not set(categories).issubset(expected_categories[self.dimension]):
            raise ValueError("public aggregate category does not match its dimension")
        if self.suppression_applied and self.visible_cells:
            raise ValueError("suppressed public aggregate dimensions cannot expose cells")
        return self


class PublicPilotAggregate(PublicPilotModel):
    aggregate_schema_version: Literal["hyc.public-local-pilot-aggregate.v1"]
    representativeness_status: Literal["NON_REPRESENTATIVE"]
    release_marker: Literal["NOT_A_RELEASE_GATE"]
    review_marker: Literal["HUMAN_REVIEW_REQUIRED"]
    status: PublicAggregateStatus
    disclosure_threshold: Literal[3]
    cohort_size_bucket: CohortSizeBucket
    small_cohort_suppressed: Literal[True, False]
    dimensions: tuple[PublicAggregateDimension, ...]

    @field_validator("dimensions", mode="before")
    @classmethod
    def freeze_dimensions(cls, value: object) -> object:
        return tuple(value) if isinstance(value, list) else value

    @model_validator(mode="after")
    def require_fixed_dimension_order(self) -> PublicPilotAggregate:
        expected: tuple[AggregateDimensionName, ...] = (
            "CLASSIFICATION",
            "DOCUMENT_KIND",
            "ELIGIBILITY_STATUS",
            "ERROR_CATEGORY",
            "LAYOUT_TRAIT",
            "LANGUAGE_TRAIT",
            "SCAN_TRAIT",
        )
        if tuple(item.dimension for item in self.dimensions) != expected:
            raise ValueError("public aggregate dimensions must use the fixed canonical order")
        if self.cohort_size_bucket == "LT_3" and (
            not self.small_cohort_suppressed or any(item.visible_cells for item in self.dimensions)
        ):
            raise ValueError("small cohorts must suppress every public dimension")
        if self.cohort_size_bucket != "LT_3" and self.small_cohort_suppressed:
            raise ValueError("only small cohorts may claim full-cohort suppression")
        return self


def _bucket(count: int) -> CohortSizeBucket:
    return "LT_3" if count < 3 else "3_TO_9" if count < 10 else "10_PLUS"


def _aggregate_dimension(
    dimension: AggregateDimensionName, values: Sequence[str], threshold: int, *, suppress_all: bool
) -> PublicAggregateDimension:
    counts = Counter(values)
    suppress_dimension = suppress_all or any(value < threshold for value in counts.values())
    visible = (
        ()
        if suppress_dimension
        else tuple(
            PublicAggregateCell(category=cast(PublicAggregateCategory, key), count=value)
            for key, value in sorted(counts.items())
        )
    )
    return PublicAggregateDimension(
        dimension=dimension,
        visible_cells=visible,
        suppression_applied=suppress_dimension,
    )


def build_public_pilot_aggregate(
    manifest: LocalPilotManifest, disclosure_threshold: int = PUBLIC_DISCLOSURE_THRESHOLD
) -> PublicPilotAggregate:
    if disclosure_threshold != PUBLIC_DISCLOSURE_THRESHOLD:
        raise ValueError("public disclosure threshold is fixed at 3")
    assessment = assess_local_pilot_manifest(manifest)
    documents = manifest.documents
    small = len(documents) < PUBLIC_DISCLOSURE_THRESHOLD
    dimensions = (
        _aggregate_dimension(
            "CLASSIFICATION",
            [x.classification for x in documents],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "DOCUMENT_KIND",
            [x.document_kind for x in documents],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "ELIGIBILITY_STATUS",
            [x.eligibility_status for x in documents],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "ERROR_CATEGORY",
            [y for x in documents for y in x.error_categories],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "LAYOUT_TRAIT",
            [y for x in documents for y in x.layout_traits],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "LANGUAGE_TRAIT",
            [y for x in documents for y in x.language_traits],
            disclosure_threshold,
            suppress_all=small,
        ),
        _aggregate_dimension(
            "SCAN_TRAIT",
            [y for x in documents for y in x.scan_traits],
            disclosure_threshold,
            suppress_all=small,
        ),
    )
    return PublicPilotAggregate(
        aggregate_schema_version="hyc.public-local-pilot-aggregate.v1",
        representativeness_status="NON_REPRESENTATIVE",
        release_marker="NOT_A_RELEASE_GATE",
        review_marker="HUMAN_REVIEW_REQUIRED",
        status=assessment.status,
        disclosure_threshold=3,
        cohort_size_bucket=_bucket(len(documents)),
        small_cohort_suppressed=small,
        dimensions=dimensions,
    )


__all__ = [
    "PUBLIC_DISCLOSURE_THRESHOLD",
    "LocalPilotAssessment",
    "LocalPilotDocument",
    "LocalPilotManifest",
    "PublicPilotAggregate",
    "assess_local_pilot_manifest",
    "build_public_pilot_aggregate",
    "local_pilot_binding_sha256",
    "validate_public_safe_tree",
]
