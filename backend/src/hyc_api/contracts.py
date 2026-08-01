from __future__ import annotations

import re
from datetime import UTC, date, datetime
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


class APIRequestModel(ContractModel):
    model_config = ConfigDict(extra="forbid", strict=False)


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


Role = Literal["INSPECTOR", "LEAD", "ADMIN"]


class LocalSessionRequest(APIRequestModel):
    fixture_principal: Literal["p3-inspector", "p3-lead", "p3-admin"]


class LocalSessionResponse(APIRequestModel):
    session_handle: str
    token_type: Literal["bearer"] = "bearer"
    actor_id: UUID
    role: Role
    auth_label: Literal["P3 fixture local identity/session — not production authentication"]


class FixtureContextResponse(APIRequestModel):
    supplier_id: UUID
    material_id: UUID
    model_id: UUID
    spec_version_id: UUID
    supplier_name: str
    material_name: str
    fixture_only: Literal[True] = True


class IntakeRequest(APIRequestModel):
    supplier_id: UUID
    material_id: UUID
    model_id: UUID | None = None
    inbound_no: Annotated[str, Field(min_length=1, max_length=64)]
    receipt_date: date
    supplier_lot_no: Annotated[str, Field(min_length=1, max_length=512)]
    quantity: DecimalString
    quantity_unit: Annotated[str, Field(min_length=1, max_length=32)]


class IntakeResponse(APIRequestModel):
    material_lot_id: UUID
    inbound_receipt_id: UUID
    allocation_id: UUID
    version: int


class DocumentResponse(APIRequestModel):
    document_id: UUID
    checksum_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    storage_key: str
    deduplicated: bool


class ExtractionFieldResponse(APIRequestModel):
    field_key: str
    original_text: str
    ocr_text: str
    confidence: DecimalString
    page_number: int
    bbox: BoundingBox
    required: bool
    status: Literal["REVIEW_REQUIRED", "CONFIRMED"]


class ExtractionRunResponse(APIRequestModel):
    run_id: UUID
    document_id: UUID
    status: Literal["REVIEW_REQUIRED", "CONFIRMED"]
    version: int
    fields: list[ExtractionFieldResponse]
    conflicts: list[dict[str, object]]


class FieldReviewInput(APIRequestModel):
    field_key: str
    manual_text: str | None = None
    final_text: Annotated[str, Field(min_length=1, max_length=4_000)]
    source: Literal["ORIGINAL", "OCR", "MANUAL"]
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]
    logic_conflict: bool = False


class ReviewRequest(APIRequestModel):
    fields: Annotated[list[FieldReviewInput], Field(min_length=1)]
    allocation_id: UUID


class InspectionCreateRequest(APIRequestModel):
    allocation_id: UUID
    extraction_run_id: UUID


class JudgmentView(APIRequestModel):
    spec_item_id: UUID
    item_code: str
    supplier_decision: str | None
    hyc_reference_decision: str | None
    internal_decision: str | None
    effective_decision: str


class InspectionResponse(APIRequestModel):
    inspection_id: UUID
    material_lot_id: UUID
    allocation_id: UUID
    spec_version_id: UUID
    spec_snapshot: dict[str, object]
    status: str
    candidate_decision: str
    final_decision: str | None
    version: int
    round_no: int
    revision_no: int
    blockers: list[str]
    judgments: list[JudgmentView]


class InternalResultItem(APIRequestModel):
    spec_item_id: UUID
    values: Annotated[list[DecimalString], Field(min_length=1)]


class InternalResultsRequest(APIRequestModel):
    results: list[InternalResultItem]


class ApprovalRequest(APIRequestModel):
    action: Literal["APPROVE", "RETURN"]
    reason: str | None = None


class LineageRequest(APIRequestModel):
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]


class LotTraceResponse(APIRequestModel):
    material_lot_id: UUID
    identity_key: str
    receipts: list[dict[str, object]]
    allocations: list[dict[str, object]]
    documents: list[dict[str, object]]
    inspections: list[dict[str, object]]
    audits: list[dict[str, object]]


def to_seoul_display(value: datetime) -> datetime:
    """Display-only conversion. Storage/API boundaries remain UTC."""
    if value.tzinfo is None:
        raise ValueError("UTC-aware datetime required")
    return value.astimezone(ZoneInfo("Asia/Seoul"))
