from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    and_,
)
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.sql.type_api import TypeEngine
from sqlalchemy.types import TypeDecorator


def utc_now() -> datetime:
    return datetime.now(UTC)


def lower_hex_check(column: str) -> str:
    expression = column
    for character in "0123456789abcdef":
        expression = f"replace({expression},'{character}','')"
    return f"{column} = lower({column}) AND length({expression}) = 0"


class Base(DeclarativeBase):
    pass


class StrictNumeric(TypeDecorator[Decimal]):
    """NUMERIC persistence boundary that never accepts binary floating point."""

    impl = Numeric
    cache_ok = True

    def __init__(self, precision: int = 24, scale: int = 12) -> None:
        super().__init__(precision=precision, scale=scale, asdecimal=True)

    def process_bind_param(
        self,
        value: Decimal | int | str | float | None,
        dialect: Dialect,
    ) -> Decimal | int | str | None:
        del dialect
        if isinstance(value, float):
            raise TypeError("quality-bearing NUMERIC values must never be Python float")
        return value

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Decimal]:
        return dialect.type_descriptor(Numeric(24, 12, asdecimal=True))


class Versioned:
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @declared_attr.directive
    def __mapper_args__(cls) -> dict[str, Any]:
        return {
            "version_id_col": cls.lock_version,
            "version_id_generator": lambda version: (version or 0) + 1,
        }


class Supplier(Base, Versioned):
    __tablename__ = "suppliers"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    supplier_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Material(Base, Versioned):
    __tablename__ = "materials"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    material_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    default_unit: Mapped[str | None] = mapped_column(String(32))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MaterialModel(Base, Versioned):
    __tablename__ = "material_models"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id"), nullable=False)
    model_code: Mapped[str | None] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class SpecProfile(Base, Versioned):
    __tablename__ = "spec_profiles"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id"), nullable=False)
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    model_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_models.id"))
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class SpecVersion(Base, Versioned):
    __tablename__ = "spec_versions"
    __table_args__ = (
        UniqueConstraint("spec_profile_id", "version", name="uq_spec_versions_profile_version"),
        CheckConstraint(
            "status IN ('DRAFT','ACTIVE','RETIRED')",
            name="ck_spec_versions_status",
        ),
        CheckConstraint(
            "version > 0",
            name="ck_spec_versions_semantic_version",
        ),
        CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name="ck_spec_versions_effective_dates",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    spec_profile_id: Mapped[UUID] = mapped_column(ForeignKey("spec_profiles.id"), nullable=False)
    # This is the PRD semantic specification version, not an optimistic-lock token.
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date)
    revision_reason: Mapped[str | None] = mapped_column(Text)


class StandardTestItem(Base, Versioned):
    __tablename__ = "standard_test_items"
    __table_args__ = (
        CheckConstraint(
            "data_type IN ('NUMERIC','TEXT','PASS_FAIL')",
            name="ck_standard_test_item_data_type",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    default_unit: Mapped[str | None] = mapped_column(String(32))


class StandardTestItemAlias(Base, Versioned):
    __tablename__ = "standard_test_item_aliases"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    standard_test_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("standard_test_items.id"), nullable=False
    )
    alias_text: Mapped[str] = mapped_column(String(256), nullable=False)
    supplier_id: Mapped[UUID | None] = mapped_column(ForeignKey("suppliers.id"))
    material_id: Mapped[UUID | None] = mapped_column(ForeignKey("materials.id"))
    model_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_models.id"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class SpecItem(Base, Versioned):
    __tablename__ = "spec_items"
    __table_args__ = (
        CheckConstraint(
            "operator IN ('GTE','GT','LTE','LT','BETWEEN_INCLUSIVE',"
            "'BETWEEN_EXCLUSIVE','TARGET_PLUS_MINUS','EQUAL','IN_SET',"
            "'CONTAINS','MANUAL_PASS_FAIL')",
            name="ck_spec_item_operator_allowlist",
        ),
        CheckConstraint(
            "(operator IN ('GTE','GT','EQUAL') AND lower_value IS NOT NULL "
            "AND upper_value IS NULL AND target_value IS NULL AND tolerance IS NULL "
            "AND allowed_values IS NULL) OR "
            "(operator IN ('LTE','LT') AND lower_value IS NULL AND upper_value IS NOT NULL "
            "AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL) OR "
            "(operator IN ('BETWEEN_INCLUSIVE','BETWEEN_EXCLUSIVE') "
            "AND lower_value IS NOT NULL AND upper_value IS NOT NULL "
            "AND lower_value <= upper_value AND target_value IS NULL "
            "AND tolerance IS NULL AND allowed_values IS NULL) OR "
            "(operator = 'TARGET_PLUS_MINUS' AND lower_value IS NULL AND upper_value IS NULL "
            "AND target_value IS NOT NULL AND tolerance IS NOT NULL AND tolerance >= 0 "
            "AND allowed_values IS NULL) OR "
            "(operator IN ('IN_SET','CONTAINS') AND lower_value IS NULL "
            "AND upper_value IS NULL AND target_value IS NULL AND tolerance IS NULL "
            "AND allowed_values IS NOT NULL) OR "
            "(operator = 'MANUAL_PASS_FAIL' AND lower_value IS NULL AND upper_value IS NULL "
            "AND target_value IS NULL AND tolerance IS NULL AND allowed_values IS NULL)",
            name="ck_spec_item_operator_columns",
        ),
        CheckConstraint(
            "source_policy IN ('SUPPLIER_ONLY','INTERNAL_ONLY','BOTH_INTERNAL_PRIORITY',"
            "'BOTH_ALL_MUST_PASS','SUPPLIER_REFERENCE_INTERNAL_FINAL')",
            name="ck_spec_item_source_policy",
        ),
        CheckConstraint(
            "missing_policy IN ('REQUEST_SUPPLEMENT','INTERNAL_SUBSTITUTE',"
            "'SPECIAL_ACCEPTANCE','HOLD','REJECT')",
            name="ck_spec_item_missing_policy",
        ),
        CheckConstraint(
            "sample_policy IN ('ALL_SAMPLES_IN_SPEC','AVERAGE_IN_SPEC',"
            "'WORST_CASE_IN_SPEC','MIN_IN_SPEC','MAX_IN_SPEC','MANUAL')",
            name="ck_spec_item_sample_policy",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    spec_version_id: Mapped[UUID] = mapped_column(ForeignKey("spec_versions.id"), nullable=False)
    standard_test_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("standard_test_items.id"), nullable=False
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    source_policy: Mapped[str] = mapped_column(String(48), nullable=False)
    missing_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="HOLD")
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    lower_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    upper_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    target_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    tolerance: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    allowed_values: Mapped[list[str] | None] = mapped_column(JSON)
    unit: Mapped[str | None] = mapped_column(String(32))
    precision: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    sample_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")


class MaterialLot(Base, Versioned):
    __tablename__ = "material_lots"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id",
            "material_id",
            "identity_policy_version",
            "identity_key",
            name="uq_material_lot_canonical_key",
        ),
        CheckConstraint(
            "(identity_status IN ('PROVISIONAL','CONFLICT_REVIEW') "
            "AND merged_into_id IS NULL) OR "
            "(identity_status = 'CANONICAL' AND identity_key IS NOT NULL "
            "AND merged_into_id IS NULL) OR "
            "(identity_status = 'MERGED' AND merged_into_id IS NOT NULL)",
            name="ck_material_lot_identity_status",
        ),
        CheckConstraint(
            "merged_into_id IS NULL OR merged_into_id <> id",
            name="ck_material_lot_no_self_merge",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    material_id: Mapped[UUID] = mapped_column(ForeignKey("materials.id"), nullable=False)
    identity_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_key: Mapped[str | None] = mapped_column(String(512))
    supplier_lot_no_raw: Mapped[str | None] = mapped_column(String(512))
    production_date_evidence: Mapped[str | None] = mapped_column(String(64))
    package_mark_evidence: Mapped[str | None] = mapped_column(String(256))
    identity_status: Mapped[str] = mapped_column(String(32), nullable=False)
    merged_into_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_lots.id"))


class InboundReceipt(Base, Versioned):
    __tablename__ = "inbound_receipts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','RECEIVED','CLOSED','CANCELLED')",
            name="ck_inbound_receipt_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inbound_no: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    supplier_id: Mapped[UUID] = mapped_column(ForeignKey("suppliers.id"), nullable=False)
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")


class ReceiptLotAllocation(Base, Versioned):
    __tablename__ = "receipt_lot_allocations"
    __table_args__ = (
        UniqueConstraint("inbound_receipt_id", "material_lot_id", name="uq_receipt_lot_allocation"),
        CheckConstraint("quantity > 0", name="ck_receipt_lot_allocation_quantity_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inbound_receipt_id: Mapped[UUID] = mapped_column(
        ForeignKey("inbound_receipts.id"), nullable=False
    )
    material_lot_id: Mapped[UUID] = mapped_column(ForeignKey("material_lots.id"), nullable=False)
    model_id: Mapped[UUID | None] = mapped_column(ForeignKey("material_models.id"))
    quantity: Mapped[Decimal] = mapped_column(StrictNumeric(), nullable=False)
    quantity_unit: Mapped[str] = mapped_column(String(32), nullable=False)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_documents_storage_key"),
        CheckConstraint(
            "length(checksum_sha256) = 64",
            name="ck_documents_sha256_length",
        ),
        CheckConstraint(
            lower_hex_check("checksum_sha256"),
            name="ck_documents_sha256_lowercase",
        ),
        CheckConstraint("immutable", name="ck_documents_always_immutable"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    checksum_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    document_type: Mapped[str] = mapped_column(String(32), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512))
    media_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentSection(Base, Versioned):
    __tablename__ = "document_sections"
    __table_args__ = (
        UniqueConstraint("document_id", "section_index", name="uq_document_section_index"),
        CheckConstraint(
            "page_from >= 1 AND page_to >= page_from",
            name="ck_document_section_page_range",
        ),
        CheckConstraint(
            "status IN ('UNMATCHED','MATCHED','REVIEW_REQUIRED')",
            name="ck_document_section_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    section_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_from: Mapped[int] = mapped_column(Integer, nullable=False)
    page_to: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNMATCHED")


class DocumentAllocationLink(Base, Versioned):
    __tablename__ = "document_allocation_links"
    __table_args__ = (
        UniqueConstraint(
            "document_section_id", "receipt_lot_allocation_id", name="uq_document_allocation_link"
        ),
        CheckConstraint(
            "match_status IN ('PENDING','CONFIRMED','REJECTED')",
            name="ck_document_allocation_match_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_section_id: Mapped[UUID] = mapped_column(
        ForeignKey("document_sections.id"), nullable=False
    )
    receipt_lot_allocation_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_lot_allocations.id"), nullable=False
    )
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)


class ExtractionRun(Base, Versioned):
    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('REVIEW_REQUIRED','CONFIRMED')",
            name="ck_extraction_runs_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW_REQUIRED")
    candidate_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    conflicts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)


class ExtractionFieldReview(Base, Versioned):
    __tablename__ = "extraction_field_reviews"
    __table_args__ = (
        UniqueConstraint("extraction_run_id", "field_key", name="uq_extraction_review_field"),
        CheckConstraint(
            "status IN ('REVIEW_REQUIRED','CONFIRMED')",
            name="ck_extraction_field_reviews_status",
        ),
        CheckConstraint("page_number >= 1", name="ck_extraction_review_page"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    extraction_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("extraction_runs.id"), nullable=False
    )
    field_key: Mapped[str] = mapped_column(String(64), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    ocr_text: Mapped[str] = mapped_column(Text, nullable=False)
    manual_text: Mapped[str | None] = mapped_column(Text)
    final_text: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(32))
    reason: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[Decimal] = mapped_column(StrictNumeric(), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    logic_conflict: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW_REQUIRED")


class InspectionCase(Base, Versioned):
    __tablename__ = "inspection_cases"
    __table_args__ = (
        CheckConstraint(
            "candidate_decision IS NULL OR candidate_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_inspection_candidate_decision",
        ),
        CheckConstraint(
            "final_decision IS NULL OR final_decision IN "
            "('ACCEPTED','REJECTED','ON_HOLD','RETEST','SPECIAL_ACCEPTED')",
            name="ck_inspection_final_decision",
        ),
        CheckConstraint(
            "(correction_of_case_id IS NULL AND revision_no = 1) OR "
            "(correction_of_case_id IS NOT NULL AND revision_no > 1)",
            name="ck_inspection_correction_revision",
        ),
        CheckConstraint(
            "status IN ('DRAFT','DOCUMENT_PENDING','MATCH_REVIEW','SUPPLIER_REVIEW',"
            "'INTERNAL_TEST_PENDING','READY_FOR_REVIEW','LEAD_REVIEW','RETURNED',"
            "'ACCEPTED','REJECTED','RETEST','SPECIAL_ACCEPTED','ON_HOLD','CLOSED',"
            "'CANCELLED')",
            name="ck_inspection_status",
        ),
        UniqueConstraint(
            "correction_of_case_id",
            "revision_no",
            name="uq_inspection_correction_revision",
        ),
        UniqueConstraint(
            "lineage_root_id",
            "round_no",
            "revision_no",
            name="uq_inspection_lineage_round_revision",
        ),
        CheckConstraint("round_no > 0", name="ck_inspection_round_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    receipt_lot_allocation_id: Mapped[UUID] = mapped_column(
        ForeignKey("receipt_lot_allocations.id"), nullable=False
    )
    spec_version_id: Mapped[UUID] = mapped_column(ForeignKey("spec_versions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    candidate_decision: Mapped[str | None] = mapped_column(String(16))
    final_decision: Mapped[str | None] = mapped_column(String(16))
    submitted_by_id: Mapped[UUID | None] = mapped_column(Uuid)
    correction_of_case_id: Mapped[UUID | None] = mapped_column(ForeignKey("inspection_cases.id"))
    retest_of_case_id: Mapped[UUID | None] = mapped_column(ForeignKey("inspection_cases.id"))
    lineage_root_id: Mapped[UUID | None] = mapped_column(ForeignKey("inspection_cases.id"))
    round_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    lineage_reason: Mapped[str | None] = mapped_column(Text)
    spec_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class InspectionReturnReason(Base):
    __tablename__ = "inspection_return_reasons"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    target_spec_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("spec_items.id"))
    returned_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class SupplierResult(Base, Versioned):
    __tablename__ = "supplier_results"
    __table_args__ = (
        CheckConstraint(
            "mapping_status IN ('UNMAPPED','ALIAS_MATCHED','MANUAL_CONFIRMED')",
            name="ck_supplier_result_mapping_status",
        ),
        CheckConstraint(
            "(mapping_status = 'UNMAPPED' AND standard_test_item_id IS NULL) OR "
            "(mapping_status IN ('ALIAS_MATCHED','MANUAL_CONFIRMED') "
            "AND standard_test_item_id IS NOT NULL)",
            name="ck_supplier_result_mapping_target",
        ),
        CheckConstraint(
            "supplier_decision IS NULL OR supplier_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_supplier_result_supplier_decision",
        ),
        CheckConstraint(
            "hyc_decision IS NULL OR hyc_decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_supplier_result_hyc_decision",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), nullable=False
    )
    standard_test_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("standard_test_items.id"))
    supplier_item_name: Mapped[str] = mapped_column(String(256), nullable=False)
    normalized_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    normalized_text: Mapped[str | None] = mapped_column(Text)
    mapping_status: Mapped[str] = mapped_column(String(32), nullable=False)
    supplier_spec_text: Mapped[str | None] = mapped_column(Text)
    supplier_decision: Mapped[str | None] = mapped_column(String(16))
    hyc_decision: Mapped[str | None] = mapped_column(String(16))


class InternalResult(Base, Versioned):
    __tablename__ = "internal_results"
    __table_args__ = (
        UniqueConstraint(
            "inspection_case_id",
            "spec_item_id",
            name="uq_internal_result_case_spec_item",
        ),
        CheckConstraint(
            "decision IS NULL OR decision IN ('ACCEPTED','REJECTED','ON_HOLD')",
            name="ck_internal_result_decision",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), nullable=False
    )
    spec_item_id: Mapped[UUID] = mapped_column(ForeignKey("spec_items.id"), nullable=False)
    evaluated_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    evaluated_text: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(16))


class SampleMeasurement(Base, Versioned):
    __tablename__ = "sample_measurements"
    __table_args__ = (
        UniqueConstraint(
            "supplier_result_id",
            "sample_index",
            name="uq_sample_supplier_result_index",
        ),
        UniqueConstraint(
            "internal_result_id",
            "sample_index",
            name="uq_sample_internal_result_index",
        ),
        CheckConstraint(
            "(supplier_result_id IS NOT NULL AND internal_result_id IS NULL) OR "
            "(supplier_result_id IS NULL AND internal_result_id IS NOT NULL)",
            name="ck_sample_exactly_one_result",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    supplier_result_id: Mapped[UUID | None] = mapped_column(ForeignKey("supplier_results.id"))
    internal_result_id: Mapped[UUID | None] = mapped_column(ForeignKey("internal_results.id"))
    sample_index: Mapped[int] = mapped_column(Integer, nullable=False)
    numeric_value: Mapped[Decimal | None] = mapped_column(StrictNumeric())
    text_value: Mapped[str | None] = mapped_column(Text)


class DecisionSnapshotRow(Base):
    __tablename__ = "decision_snapshots"
    __table_args__ = (
        CheckConstraint(
            "length(content_hash) = 64",
            name="ck_decision_snapshot_hash_length",
        ),
        CheckConstraint(
            lower_hex_check("content_hash"),
            name="ck_decision_snapshot_hash_lowercase",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), unique=True, nullable=False
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Approval(Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint("actor_role = 'LEAD'", name="ck_approval_actor_role_lead"),
        CheckConstraint("action = 'APPROVE'", name="ck_approval_action"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class NonconformanceDisposition(Base, Versioned):
    __tablename__ = "nonconformance_dispositions"
    __table_args__ = (UniqueConstraint("code", name="uq_nonconformance_dispositions_code"),)
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)


class Nonconformance(Base, Versioned):
    __tablename__ = "nonconformances"
    __table_args__ = (
        UniqueConstraint("ncr_number", name="uq_nonconformances_ncr_number"),
        CheckConstraint(
            "severity IS NULL OR severity IN ('MAJOR','MINOR')",
            name="ck_nonconformances_severity",
        ),
        CheckConstraint("quantity > 0", name="ck_nonconformances_quantity_positive"),
        CheckConstraint(
            "status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED','CLOSED')",
            name="ck_nonconformances_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    ncr_number: Mapped[str] = mapped_column(String(64), nullable=False)
    inspection_case_id: Mapped[UUID] = mapped_column(
        ForeignKey("inspection_cases.id"), nullable=False
    )
    spec_item_id: Mapped[UUID | None] = mapped_column(ForeignKey("spec_items.id"))
    severity: Mapped[str | None] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(StrictNumeric(), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    cause: Mapped[str | None] = mapped_column(Text)
    disposition_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("nonconformance_dispositions.id")
    )
    disposition_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    target_completion_date: Mapped[date | None] = mapped_column(Date)
    completion_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    retest_case_id: Mapped[UUID | None] = mapped_column(ForeignKey("inspection_cases.id"))


class NonconformanceApproval(Base):
    __tablename__ = "nonconformance_approvals"
    __table_args__ = (
        CheckConstraint(
            "actor_role = 'LEAD'", name="ck_nonconformance_approvals_actor_role_lead"
        ),
        CheckConstraint(
            "action IN ('APPROVE','REJECT')", name="ck_nonconformance_approvals_action"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    nonconformance_id: Mapped[UUID] = mapped_column(
        ForeignKey("nonconformances.id"), nullable=False
    )
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class NonconformanceAttachment(Base):
    __tablename__ = "nonconformance_attachments"
    __table_args__ = (
        UniqueConstraint(
            "nonconformance_id",
            "document_id",
            name="uq_nonconformance_attachment_document",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    nonconformance_id: Mapped[UUID] = mapped_column(
        ForeignKey("nonconformances.id"), nullable=False
    )
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"), nullable=False)


class LotMergeApproval(Base):
    __tablename__ = "lot_merge_approvals"
    __table_args__ = (
        UniqueConstraint(
            "material_lot_id",
            "role",
            name="uq_lot_merge_approvals_role",
        ),
        CheckConstraint(
            "role IN ('LEAD','ADMIN')",
            name="ck_lot_merge_approvals_role",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    material_lot_id: Mapped[UUID] = mapped_column(ForeignKey("material_lots.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ReportJob(Base):
    __tablename__ = "report_jobs"
    __table_args__ = (
        CheckConstraint(
            "state IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')",
            name="ck_report_job_state_allowlist",
        ),
        CheckConstraint(
            "(state <> 'FAILED') OR (failure_code IS NOT NULL)",
            name="ck_report_job_failure_code_present",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(64))
    requested_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"
    __table_args__ = (
        CheckConstraint("length(content_digest) = 64", name="ck_report_artifact_digest_length"),
        CheckConstraint(
            lower_hex_check("content_digest"), name="ck_report_artifact_digest_lowercase"
        ),
        CheckConstraint("byte_size > 0", name="ck_report_artifact_byte_size_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    report_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("report_jobs.id"), unique=True, nullable=False
    )
    content_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class NonconformanceAction(Base):
    __tablename__ = "nonconformance_actions"
    __table_args__ = (
        CheckConstraint(
            "action_type IN ('CORRECTIVE','PREVENTIVE','VERIFICATION','COMPLETION')",
            name="ck_nonconformance_actions_type",
        ),
        CheckConstraint(
            "length(trim(description)) > 0",
            name="ck_nonconformance_actions_description_nonempty",
        ),
        CheckConstraint(
            "action_type <> 'COMPLETION' OR actor_role = 'LEAD'",
            name="ck_nonconformance_actions_completion_lead",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    nonconformance_id: Mapped[UUID] = mapped_column(
        ForeignKey("nonconformances.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str | None] = mapped_column(Text)
    performed_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class IngestCursor(Base):
    __tablename__ = "ingest_cursors"
    __table_args__ = (
        UniqueConstraint("source_id", "entry_id", name="uq_ingest_cursors_source_entry"),
        CheckConstraint(
            "status IN ('PENDING_STABILITY','INGESTED','FAILED','VANISHED')",
            name="ck_ingest_cursors_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_id: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_STABILITY")
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    modified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    document_id: Mapped[UUID | None] = mapped_column(ForeignKey("documents.id"))
    checksum_sha256: Mapped[str | None] = mapped_column(String(64))
    error_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MasterImportBatch(Base):
    __tablename__ = "master_import_batches"
    __table_args__ = (
        CheckConstraint(
            "entity IN ('MATERIAL','SUPPLIER','MATERIAL_MODEL')",
            name="ck_master_import_entity",
        ),
        CheckConstraint(
            "state IN ('PREVIEWED','APPLIED','REVERTED')",
            name="ck_master_import_state",
        ),
        CheckConstraint(
            "(state <> 'REVERTED') OR (reverted_at IS NOT NULL)",
            name="ck_master_import_reverted_at_present",
        ),
        CheckConstraint("length(source_digest) = 64", name="ck_master_import_digest_length"),
        CheckConstraint(
            lower_hex_check("source_digest"), name="ck_master_import_digest_lower"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity: Mapped[str] = mapped_column(String(32), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PREVIEWED")
    requested_by_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    reverted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class MasterImportRow(Base):
    __tablename__ = "master_import_rows"
    __table_args__ = (
        UniqueConstraint("batch_id", "row_number", name="uq_master_import_row_number"),
        CheckConstraint(
            "action IN ('CREATE','UPDATE','UNCHANGED','REJECT')",
            name="ck_master_import_row_action",
        ),
        CheckConstraint("row_number >= 1", name="ck_master_import_row_number_positive"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("master_import_batches.id"), nullable=False
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    code: Mapped[str | None] = mapped_column(String(64))
    name: Mapped[str | None] = mapped_column(String(256))
    errors: Mapped[list[Any]] = mapped_column(JSON, nullable=False, default=list)
    target_id: Mapped[UUID | None] = mapped_column(Uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint("principal_id", "scope", "key", name="uq_idempotency_principal_scope_key"),
        CheckConstraint(
            "state IN ('PENDING','COMPLETED','FAILED_RETRYABLE')",
            name="ck_idempotency_state_allowlist",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    principal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    scope: Mapped[str] = mapped_column(String(128), nullable=False)
    key: Mapped[str] = mapped_column(String(256), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(256))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[str | None] = mapped_column(Text)
    resource_ref: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_documents_checksum_sha256", Document.checksum_sha256)
Index("ix_decision_snapshots_content_hash", DecisionSnapshotRow.content_hash)
for name, columns, predicate in (
    (
        "uq_standard_alias_scope_000",
        (StandardTestItemAlias.alias_text,),
        and_(
            StandardTestItemAlias.supplier_id.is_(None),
            StandardTestItemAlias.material_id.is_(None),
            StandardTestItemAlias.model_id.is_(None),
        ),
    ),
    (
        "uq_standard_alias_scope_100",
        (StandardTestItemAlias.alias_text, StandardTestItemAlias.supplier_id),
        and_(
            StandardTestItemAlias.supplier_id.is_not(None),
            StandardTestItemAlias.material_id.is_(None),
            StandardTestItemAlias.model_id.is_(None),
        ),
    ),
    (
        "uq_standard_alias_scope_010",
        (StandardTestItemAlias.alias_text, StandardTestItemAlias.material_id),
        and_(
            StandardTestItemAlias.supplier_id.is_(None),
            StandardTestItemAlias.material_id.is_not(None),
            StandardTestItemAlias.model_id.is_(None),
        ),
    ),
    (
        "uq_standard_alias_scope_001",
        (StandardTestItemAlias.alias_text, StandardTestItemAlias.model_id),
        and_(
            StandardTestItemAlias.supplier_id.is_(None),
            StandardTestItemAlias.material_id.is_(None),
            StandardTestItemAlias.model_id.is_not(None),
        ),
    ),
    (
        "uq_standard_alias_scope_110",
        (
            StandardTestItemAlias.alias_text,
            StandardTestItemAlias.supplier_id,
            StandardTestItemAlias.material_id,
        ),
        and_(
            StandardTestItemAlias.supplier_id.is_not(None),
            StandardTestItemAlias.material_id.is_not(None),
            StandardTestItemAlias.model_id.is_(None),
        ),
    ),
    (
        "uq_standard_alias_scope_101",
        (
            StandardTestItemAlias.alias_text,
            StandardTestItemAlias.supplier_id,
            StandardTestItemAlias.model_id,
        ),
        and_(
            StandardTestItemAlias.supplier_id.is_not(None),
            StandardTestItemAlias.material_id.is_(None),
            StandardTestItemAlias.model_id.is_not(None),
        ),
    ),
    (
        "uq_standard_alias_scope_011",
        (
            StandardTestItemAlias.alias_text,
            StandardTestItemAlias.material_id,
            StandardTestItemAlias.model_id,
        ),
        and_(
            StandardTestItemAlias.supplier_id.is_(None),
            StandardTestItemAlias.material_id.is_not(None),
            StandardTestItemAlias.model_id.is_not(None),
        ),
    ),
    (
        "uq_standard_alias_scope_111",
        (
            StandardTestItemAlias.alias_text,
            StandardTestItemAlias.supplier_id,
            StandardTestItemAlias.material_id,
            StandardTestItemAlias.model_id,
        ),
        and_(
            StandardTestItemAlias.supplier_id.is_not(None),
            StandardTestItemAlias.material_id.is_not(None),
            StandardTestItemAlias.model_id.is_not(None),
        ),
    ),
):
    Index(name, *columns, unique=True, postgresql_where=predicate, sqlite_where=predicate)
Index(
    "ix_standard_test_item_alias_lookup_order",
    StandardTestItemAlias.priority,
    StandardTestItemAlias.alias_text,
)
Index(
    "uq_document_section_one_confirmed_allocation",
    DocumentAllocationLink.document_section_id,
    unique=True,
    postgresql_where=DocumentAllocationLink.match_status == "CONFIRMED",
    sqlite_where=DocumentAllocationLink.match_status == "CONFIRMED",
)
Index(
    "uq_document_one_confirmed_extraction_run",
    ExtractionRun.document_id,
    unique=True,
    postgresql_where=ExtractionRun.status == "CONFIRMED",
    sqlite_where=ExtractionRun.status == "CONFIRMED",
)
