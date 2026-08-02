from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from hyc_evaluation.normalization import NormalizationSequence

CANONICAL_DECIMAL_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
SEMANTIC_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"


def _canonical_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        rendered = str(value)
    elif isinstance(value, str):
        rendered = value
    else:
        raise ValueError("golden decimals must be canonical decimal strings")
    if not re.fullmatch(CANONICAL_DECIMAL_PATTERN, rendered):
        raise ValueError("golden decimal is not canonical")
    converted = Decimal(rendered)
    if not converted.is_finite():
        raise ValueError("golden decimal must be finite")
    return converted


CanonicalDecimal = Annotated[
    Decimal,
    BeforeValidator(_canonical_decimal),
    PlainSerializer(lambda value: format(value, "f"), return_type=str),
    WithJsonSchema({"type": "string", "pattern": CANONICAL_DECIMAL_PATTERN}),
]
Identifier = Annotated[str, Field(pattern=IDENTIFIER_PATTERN)]
SemanticVersion = Annotated[str, Field(pattern=SEMANTIC_VERSION_PATTERN)]
type ApplicableVersion = SemanticVersion | Literal["not-applicable"]
type PolygonVertex = tuple[Decimal, Decimal]


def _orientation(start: PolygonVertex, end: PolygonVertex, point: PolygonVertex) -> Decimal:
    return (end[0] - start[0]) * (point[1] - start[1]) - (end[1] - start[1]) * (point[0] - start[0])


def _on_segment(start: PolygonVertex, point: PolygonVertex, end: PolygonVertex) -> bool:
    return min(start[0], end[0]) <= point[0] <= max(start[0], end[0]) and min(
        start[1], end[1]
    ) <= point[1] <= max(start[1], end[1])


def _segments_intersect(
    first_start: PolygonVertex,
    first_end: PolygonVertex,
    second_start: PolygonVertex,
    second_end: PolygonVertex,
) -> bool:
    first_start_side = _orientation(first_start, first_end, second_start)
    first_end_side = _orientation(first_start, first_end, second_end)
    second_start_side = _orientation(second_start, second_end, first_start)
    second_end_side = _orientation(second_start, second_end, first_end)

    if (first_start_side > 0 > first_end_side or first_start_side < 0 < first_end_side) and (
        second_start_side > 0 > second_end_side or second_start_side < 0 < second_end_side
    ):
        return True
    return (
        (first_start_side == 0 and _on_segment(first_start, second_start, first_end))
        or (first_end_side == 0 and _on_segment(first_start, second_end, first_end))
        or (second_start_side == 0 and _on_segment(second_start, first_start, second_end))
        or (second_end_side == 0 and _on_segment(second_start, first_end, second_end))
    )


class GoldenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class VersionBindings(GoldenModel):
    fixture_name: Identifier
    fixture_version: SemanticVersion
    provider_name: Literal["synthetic-fixture"]
    provider_version: SemanticVersion
    model_version: ApplicableVersion
    parser_version: SemanticVersion
    prompt_schema_version: ApplicableVersion
    pipeline_version: SemanticVersion
    stage_contract_version: SemanticVersion
    runner_version: SemanticVersion
    scorer_version: SemanticVersion
    report_version: SemanticVersion


class GeneratorBinding(GoldenModel):
    name: Identifier
    version: SemanticVersion
    seed: Annotated[int, Field(ge=0)]


class GoldenInput(GoldenModel):
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    mime_type: Literal["application/pdf", "image/jpeg", "image/png"]
    document_kind: Literal["supplier-coa", "supplier-inspection-report"]
    synthetic: Literal[True]
    generator: GeneratorBinding
    provenance_marker: Literal["generated-non-sensitive-synthetic"]


class GoldenPage(GoldenModel):
    page_id: Identifier
    page_number: Annotated[int, Field(ge=1)]
    rendered_dpi: Annotated[int, Field(ge=72, le=1200)]
    declared_rotation: Literal[0, 90, 180, 270]
    detected_rotation: Literal[0, 90, 180, 270]
    width: Annotated[CanonicalDecimal, Field(gt=0)]
    height: Annotated[CanonicalDecimal, Field(gt=0)]
    coordinate_system: Literal["pixels"]
    coordinate_system_version: Literal["1.0"]


class GoldenIdentity(GoldenModel):
    document_id: Identifier
    section_id: Identifier
    row_id: Identifier
    row_order: Annotated[int, Field(ge=1)]
    sample_id: Identifier | None
    sample_order: Annotated[int, Field(ge=1)] | None

    @model_validator(mode="after")
    def require_complete_sample_identity(self) -> GoldenIdentity:
        if (self.sample_id is None) != (self.sample_order is None):
            raise ValueError("sample_id and sample_order must be bound together")
        return self


class PolygonPoint(GoldenModel):
    x: Annotated[CanonicalDecimal, Field(ge=0)]
    y: Annotated[CanonicalDecimal, Field(ge=0)]


class GoldenGeometry(GoldenModel):
    page_number: Annotated[int, Field(ge=1)]
    polygon: Annotated[list[PolygonPoint], Field(min_length=3)]

    @model_validator(mode="after")
    def require_non_degenerate_polygon(self) -> GoldenGeometry:
        vertices = [(point.x, point.y) for point in self.polygon]
        if len(vertices) != len(set(vertices)):
            raise ValueError("polygon vertices must be unique")
        for edge_index, edge_start in enumerate(vertices):
            edge_end = vertices[(edge_index + 1) % len(vertices)]
            for other_index in range(edge_index + 1, len(vertices)):
                if other_index in {
                    edge_index,
                    (edge_index + 1) % len(vertices),
                    (edge_index - 1) % len(vertices),
                }:
                    continue
                other_start = vertices[other_index]
                other_end = vertices[(other_index + 1) % len(vertices)]
                if _segments_intersect(edge_start, edge_end, other_start, other_end):
                    raise ValueError("polygon must not self-intersect")
        twice_area = sum(
            point.x * next_point.y - next_point.x * point.y
            for point, next_point in zip(
                self.polygon,
                self.polygon[1:] + self.polygon[:1],
                strict=True,
            )
        )
        if twice_area == 0:
            raise ValueError("polygon must have non-zero area")
        turns = [
            _orientation(
                vertices[index],
                vertices[(index + 1) % len(vertices)],
                vertices[(index + 2) % len(vertices)],
            )
            for index in range(len(vertices))
        ]
        non_zero_turns = [turn for turn in turns if turn != 0]
        if len(non_zero_turns) != len(turns) or any(
            (turn > 0) != (non_zero_turns[0] > 0) for turn in non_zero_turns[1:]
        ):
            raise ValueError("polygon must be strictly convex for deterministic IoU")
        return self


type ReviewReason = Literal[
    "HANDWRITING_REFERENCE_ONLY",
    "LOGIC_CONFLICT",
    "LOW_CONFIDENCE",
    "MISSING_REQUIRED",
    "UNMAPPED",
]


class GoldenReview(GoldenModel):
    review_required: bool
    reason_codes: list[ReviewReason]
    handwriting_reference_only: bool

    @field_validator("reason_codes", mode="before")
    @classmethod
    def order_reason_codes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        if len(value) != len(set(value)):
            raise ValueError("review reason codes must be unique")
        return sorted(value)

    @model_validator(mode="after")
    def require_consistent_review_state(self) -> GoldenReview:
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("review reason codes must be unique")
        if bool(self.reason_codes) != self.review_required:
            raise ValueError("review_required must reflect review reason codes")
        handwriting_reason = "HANDWRITING_REFERENCE_ONLY" in self.reason_codes
        if handwriting_reason != self.handwriting_reference_only:
            raise ValueError("handwriting marker must use HANDWRITING_REFERENCE_ONLY")
        return self


type ValueKind = Literal["date", "decimal", "header", "lot", "text", "unit"]


class GoldenValue(GoldenModel):
    kind: ValueKind
    raw: str | None
    normalized: CanonicalDecimal | str | None
    unit: Annotated[str, Field(min_length=1, max_length=64)] | None

    @field_validator("raw")
    @classmethod
    def reject_empty_raw_value(cls, value: str | None) -> str | None:
        if value == "":
            raise ValueError("raw value must be non-empty when present")
        return value

    @model_validator(mode="after")
    def require_value_type(self) -> GoldenValue:
        if (self.raw is None) != (self.normalized is None):
            raise ValueError("raw and normalized values must be present or missing together")
        if self.kind == "decimal":
            if self.normalized is not None and not isinstance(self.normalized, Decimal):
                raise ValueError("decimal normalized values must be canonical decimals")
        elif self.normalized is not None:
            if not isinstance(self.normalized, str):
                raise ValueError("non-decimal normalized values must be strings")
            if not self.normalized:
                raise ValueError("normalized strings must be non-empty")
            if self.kind == "date":
                try:
                    parsed_date = date.fromisoformat(self.normalized)
                except ValueError as error:
                    raise ValueError(
                        "normalized dates must use ISO 8601 calendar format"
                    ) from error
                if parsed_date.isoformat() != self.normalized:
                    raise ValueError("normalized dates must use canonical ISO 8601 format")
        return self


class GoldenExpectedField(GoldenModel):
    identity: GoldenIdentity
    field_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    required: bool
    ignored: bool
    value: GoldenValue
    geometry: GoldenGeometry
    review: GoldenReview
    allowed_normalizations: NormalizationSequence

    @model_validator(mode="after")
    def fail_closed_on_ignored_or_missing_values(self) -> GoldenExpectedField:
        if self.required and self.ignored:
            raise ValueError("required fields cannot be ignored")
        if self.value.raw is None and self.value.normalized is None:
            if self.required and "MISSING_REQUIRED" not in self.review.reason_codes:
                raise ValueError("missing required fields must require review")
        identities = [
            (binding.normalization_id, binding.normalization_version)
            for binding in self.allowed_normalizations
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("allowed normalization identities must be unique")
        return self


class GoldenCase(GoldenModel):
    case_id: Identifier
    ordering_key: Identifier
    input: GoldenInput
    pages: Annotated[list[GoldenPage], Field(min_length=1)]
    expected_fields: Annotated[list[GoldenExpectedField], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_identities_and_geometry(self) -> GoldenCase:
        page_numbers = [page.page_number for page in self.pages]
        page_ids = [page.page_id for page in self.pages]
        if len(page_numbers) != len(set(page_numbers)) or len(page_ids) != len(set(page_ids)):
            raise ValueError("page identities must be unique")
        pages_by_number = {page.page_number: page for page in self.pages}

        field_identities: set[tuple[str, str, str, str | None, str]] = set()
        row_order_by_id: dict[tuple[str, str, str], int] = {}
        row_id_by_order: dict[tuple[str, str, int], str] = {}
        sample_order_by_id: dict[tuple[str, str, str, str], int] = {}
        sample_id_by_order: dict[tuple[str, str, str, int], str] = {}

        for field in self.expected_fields:
            identity = field.identity
            field_identity = (
                identity.document_id,
                identity.section_id,
                identity.row_id,
                identity.sample_id,
                field.field_key,
            )
            if field_identity in field_identities:
                raise ValueError("field identities must be unique")
            field_identities.add(field_identity)

            row_id = (identity.document_id, identity.section_id, identity.row_id)
            row_order = (identity.document_id, identity.section_id, identity.row_order)
            if row_id in row_order_by_id and row_order_by_id[row_id] != identity.row_order:
                raise ValueError("row identity has conflicting ordering")
            if row_order in row_id_by_order and row_id_by_order[row_order] != identity.row_id:
                raise ValueError("row ordering must be unique within its parent")
            row_order_by_id[row_id] = identity.row_order
            row_id_by_order[row_order] = identity.row_id

            if identity.sample_id is not None and identity.sample_order is not None:
                sample_id = (*row_id, identity.sample_id)
                sample_order = (*row_id, identity.sample_order)
                if (
                    sample_id in sample_order_by_id
                    and sample_order_by_id[sample_id] != identity.sample_order
                ):
                    raise ValueError("sample identity has conflicting ordering")
                if (
                    sample_order in sample_id_by_order
                    and sample_id_by_order[sample_order] != identity.sample_id
                ):
                    raise ValueError("sample ordering must be unique within its parent")
                sample_order_by_id[sample_id] = identity.sample_order
                sample_id_by_order[sample_order] = identity.sample_id

            page = pages_by_number.get(field.geometry.page_number)
            if page is None:
                raise ValueError("geometry references an unknown page")
            if any(
                point.x > page.width or point.y > page.height for point in field.geometry.polygon
            ):
                raise ValueError("polygon must remain within its declared page")
        return self


class GoldenDataset(GoldenModel):
    golden_schema_version: Literal["hyc.golden.v1"]
    dataset_id: Identifier
    dataset_version: SemanticVersion
    normalization_vocabulary_version: Literal["hyc.normalization.v1"]
    bindings: VersionBindings
    cases: Annotated[list[GoldenCase], Field(min_length=1)]

    @model_validator(mode="after")
    def reject_duplicate_case_and_document_identities(self) -> GoldenDataset:
        case_ids = [case.case_id for case in self.cases]
        ordering_keys = [case.ordering_key for case in self.cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("case identities must be unique")
        if len(ordering_keys) != len(set(ordering_keys)):
            raise ValueError("case ordering keys must be unique")

        document_ids_by_case = [
            {field.identity.document_id for field in case.expected_fields} for case in self.cases
        ]
        if any(len(document_ids) != 1 for document_ids in document_ids_by_case):
            raise ValueError("each case must bind exactly one document identity")
        document_ids = [next(iter(document_ids)) for document_ids in document_ids_by_case]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document identities must be unique across cases")
        return self
