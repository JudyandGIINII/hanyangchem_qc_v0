from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    WithJsonSchema,
    field_serializer,
    field_validator,
    model_validator,
)

CANONICAL_DECIMAL_STRING_PATTERN = r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


def reject_binary_float(value: object) -> object:
    if isinstance(value, Decimal):
        if not value.is_finite() or not re.fullmatch(CANONICAL_DECIMAL_STRING_PATTERN, str(value)):
            raise ValueError("candidate decimal value is not canonical")
        return value
    if not isinstance(value, str):
        raise ValueError("candidate decimal values must be canonical decimal strings")
    if not re.fullmatch(CANONICAL_DECIMAL_STRING_PATTERN, value):
        raise ValueError("candidate decimal value is not canonical")
    decimal_value = Decimal(value)
    if not decimal_value.is_finite():
        raise ValueError("candidate decimal value must be finite")
    return decimal_value


DecimalString = Annotated[
    Decimal,
    BeforeValidator(reject_binary_float),
    PlainSerializer(lambda value: format(value, "f"), return_type=str),
    WithJsonSchema({"type": "string", "pattern": CANONICAL_DECIMAL_STRING_PATTERN}),
]


class BoundingBox(ContractModel):
    left: Annotated[float, Field(ge=0)]
    top: Annotated[float, Field(ge=0)]
    right: Annotated[float, Field(ge=0)]
    bottom: Annotated[float, Field(ge=0)]

    @model_validator(mode="after")
    def has_positive_area(self) -> BoundingBox:
        if self.right <= self.left or self.bottom <= self.top:
            raise ValueError("bbox must have positive area")
        return self


class SourceReference(ContractModel):
    document_id: UUID
    source_reference: Annotated[str, Field(min_length=1, max_length=512)]
    page_number: Annotated[int, Field(ge=1)]
    bbox: BoundingBox


class ExtractionValue(ContractModel):
    item_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    raw_text: Annotated[str, Field(min_length=1, max_length=4_000)]
    normalized_value: DecimalString | None = None
    unit: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    provenance: SourceReference
    confidence: Annotated[float, Field(ge=0, le=1)]
    review_required: bool

    @model_validator(mode="after")
    def confidence_requires_review(self) -> ExtractionValue:
        if self.confidence < 1 and not self.review_required:
            raise ValueError("confidence below 1 requires review")
        return self

class ExtractionCandidate(ContractModel):
    schema_version: Literal["1.0"]
    candidate_id: UUID
    created_at: datetime
    document: SourceReference
    provider_name: Literal["synthetic-fixture"]
    values: Annotated[list[ExtractionValue], Field(min_length=1)]
    review_required: bool

    @field_validator("created_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("created_at must be UTC-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_review_for_child(self) -> ExtractionCandidate:
        if any(value.review_required for value in self.values) and not self.review_required:
            raise ValueError("candidate review_required must include value review requirements")
        return self

    @field_serializer("created_at", when_used="json")
    def serialize_utc(self, value: datetime) -> str:
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ErrorEnvelope(ContractModel):
    schema_version: Literal["1.0"]
    code: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")]
    message: Annotated[str, Field(min_length=1, max_length=512)]
    correlation_id: UUID


class HealthEnvelope(ContractModel):
    status: Literal["live", "ready"]


def to_seoul_display(value: datetime) -> datetime:
    """Display-only conversion. Storage/API boundaries remain UTC."""
    if value.tzinfo is None:
        raise ValueError("UTC-aware datetime required")
    return value.astimezone(ZoneInfo("Asia/Seoul"))
