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
    return parse_canonical_decimal_string(value)


def parse_canonical_decimal_string(value: object) -> Decimal:
    """Parse the one canonical finite Decimal string policy used at all write gates."""

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


type ExtractionReviewReason = Literal[
    "HUMAN_REVIEW_REQUIRED",
    "LOT_CONFLICT",
    "LOW_CONFIDENCE",
    "MISSING_REQUIRED",
    "NATIVE_OCR_DISAGREEMENT",
    "NUMERIC_CONFLICT",
    "TABLE_LAYOUT_REVIEW_REQUIRED",
    "UNIT_CONFLICT",
    "VARIANT_DISAGREEMENT",
]
type ExtractionRecipe = Literal[
    "adaptive-threshold",
    "grayscale-clahe",
    "native-text",
    "original",
    "otsu-denoise-sharpen",
]
EXTRACTION_REASON_ORDER: tuple[ExtractionReviewReason, ...] = (
    "HUMAN_REVIEW_REQUIRED",
    "LOW_CONFIDENCE",
    "MISSING_REQUIRED",
    "NATIVE_OCR_DISAGREEMENT",
    "VARIANT_DISAGREEMENT",
    "NUMERIC_CONFLICT",
    "UNIT_CONFLICT",
    "LOT_CONFLICT",
    "TABLE_LAYOUT_REVIEW_REQUIRED",
)


class ExtractionValue(ContractModel):
    item_key: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")]
    raw_text: Annotated[str, Field(min_length=1, max_length=4_000)]
    normalized_value: DecimalString | None = None
    unit: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    provenance: SourceReference
    confidence: Annotated[float, Field(ge=0, le=1)]
    review_required: bool
    reading_order: Annotated[int, Field(ge=1)] | None = None
    recipe_id: ExtractionRecipe | None = None
    variant_id: Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{0,63}$")] | None = None
    rotation_degrees: Literal[0, 90, 180, 270] | None = None
    deskew_millidegrees: Annotated[int, Field(ge=-10_000, le=10_000)] | None = None
    deskew_status: Literal["NOT_NEEDED", "APPLIED", "OUT_OF_BOUNDS"] | None = None
    perspective_corrected: bool | None = None
    reason_codes: list[ExtractionReviewReason] = Field(default_factory=list)

    @field_validator("reason_codes", mode="before")
    @classmethod
    def canonicalize_reason_codes(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        if len(value) != len(set(value)):
            raise ValueError("extraction reason codes must be unique")
        present = set(value)
        return [reason for reason in EXTRACTION_REASON_ORDER if reason in present]

    @model_validator(mode="after")
    def confidence_requires_review(self) -> ExtractionValue:
        if self.confidence < 1 and not self.review_required:
            raise ValueError("confidence below 1 requires review")
        if self.reason_codes and not self.review_required:
            raise ValueError("extraction reason codes require review")
        return self


class ExtractionCandidate(ContractModel):
    schema_version: Literal["1.0"]
    candidate_id: UUID
    created_at: datetime
    document: SourceReference
    provider_name: Literal["local-paddleocr", "synthetic-fixture"]
    values: Annotated[list[ExtractionValue], Field(min_length=1, max_length=500)]
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
        if self.provider_name == "local-paddleocr" and not self.review_required:
            raise ValueError("local OCR candidates always require human review")
        if self.provider_name == "local-paddleocr":
            if any(not value.review_required for value in self.values):
                raise ValueError("all local OCR values require human review")
            if any(
                value.reading_order is None
                or value.recipe_id is None
                or value.variant_id is None
                or value.rotation_degrees is None
                or value.deskew_millidegrees is None
                or value.deskew_status is None
                or value.perspective_corrected is None
                for value in self.values
            ):
                raise ValueError("local OCR values require complete transform provenance")
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
    mapping_item_codes: list[str]
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
    field_id: UUID
    field_key: str
    source_field_key: str
    original_text: str
    ocr_text: str
    final_text: str | None = None
    source: Literal["ORIGINAL", "OCR", "MANUAL"] | None = None
    reason: str | None = None
    confidence: DecimalString
    page_number: int
    bbox: BoundingBox
    required: bool
    status: Literal["REVIEW_REQUIRED", "CONFIRMED"]
    mapping_disposition: Literal["MAP", "UNMAPPED"] | None = None
    mapped_field_key: str | None = None
    review_reasons: list[str] = Field(default_factory=list)
    provenance: dict[str, object] = Field(default_factory=dict)


class ExtractionRunResponse(APIRequestModel):
    run_id: UUID
    document_id: UUID
    status: Literal["REVIEW_REQUIRED", "CONFIRMED"]
    version: int
    provider_name: str
    fields: list[ExtractionFieldResponse]
    conflicts: list[dict[str, object]]


class FieldReviewInput(APIRequestModel):
    field_id: UUID | None = None
    field_key: str
    manual_text: str | None = None
    final_text: Annotated[str, Field(min_length=1, max_length=4_000)]
    source: Literal["ORIGINAL", "OCR", "MANUAL"]
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]
    logic_conflict: bool = False
    mapping_disposition: Literal["MAP", "UNMAPPED"] | None = None
    mapped_field_key: Annotated[str, Field(min_length=1, max_length=64)] | None = None

    @field_validator("field_key", "final_text", "reason", mode="before")
    @classmethod
    def require_string_review_scalars(cls, value: object) -> object:
        if not isinstance(value, str):
            raise ValueError("review scalar values must be strings")
        return value

    @field_validator("manual_text", "mapped_field_key", mode="before")
    @classmethod
    def require_optional_string_review_scalars(cls, value: object) -> object:
        if value is not None and not isinstance(value, str):
            raise ValueError("optional review scalar values must be strings")
        return value


class ReviewRequest(APIRequestModel):
    fields: Annotated[list[FieldReviewInput], Field(min_length=1, max_length=500)]
    allocation_id: UUID
    spec_version_id: UUID | None = None


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


class SupplierCreateRequest(APIRequestModel):
    supplier_code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=256)]
    active: bool = True


class SupplierUpdateRequest(SupplierCreateRequest):
    pass


class SupplierResponse(APIRequestModel):
    id: UUID
    supplier_code: str | None
    name: str
    active: bool
    lock_version: int
    created_at: datetime
    updated_at: datetime


class MaterialCreateRequest(APIRequestModel):
    material_code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=256)]
    default_unit: Annotated[str, Field(min_length=1, max_length=32)] | None = None
    active: bool = True


class MaterialUpdateRequest(MaterialCreateRequest):
    pass


class MaterialResponse(APIRequestModel):
    id: UUID
    material_code: str | None
    name: str
    default_unit: str | None
    active: bool
    lock_version: int
    created_at: datetime
    updated_at: datetime


class MaterialModelCreateRequest(APIRequestModel):
    material_id: UUID
    model_code: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    name: Annotated[str, Field(min_length=1, max_length=256)]


class MaterialModelUpdateRequest(MaterialModelCreateRequest):
    pass


class MaterialModelResponse(APIRequestModel):
    id: UUID
    material_id: UUID
    model_code: str | None
    name: str
    lock_version: int
    created_at: datetime
    updated_at: datetime


class SpecProfileCreateRequest(APIRequestModel):
    material_id: UUID
    supplier_id: UUID | None = None
    model_id: UUID | None = None
    name: Annotated[str, Field(min_length=1, max_length=256)]


class SpecProfileUpdateRequest(SpecProfileCreateRequest):
    pass


class SpecProfileResponse(APIRequestModel):
    id: UUID
    material_id: UUID
    supplier_id: UUID | None
    model_id: UUID | None
    name: str
    lock_version: int
    created_at: datetime
    updated_at: datetime


class SpecVersionCreateRequest(APIRequestModel):
    version: Annotated[int, Field(gt=0)]
    effective_from: date
    effective_to: date | None = None
    revision_reason: str | None = None


class SpecVersionUpdateRequest(SpecVersionCreateRequest):
    pass


class SpecVersionResponse(APIRequestModel):
    id: UUID
    spec_profile_id: UUID
    version: int
    status: Literal["DRAFT", "ACTIVE", "RETIRED"]
    effective_from: date
    effective_to: date | None
    revision_reason: str | None
    lock_version: int
    created_at: datetime
    updated_at: datetime


def to_seoul_display(value: datetime) -> datetime:
    """Display-only conversion. Storage/API boundaries remain UTC."""
    if value.tzinfo is None:
        raise ValueError("UTC-aware datetime required")
    return value.astimezone(ZoneInfo("Asia/Seoul"))
