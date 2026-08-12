from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from inspect import signature
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from hyc_data.models import (
    Approval,
    AuditLog,
    Base,
    DecisionSnapshotRow,
    Document,
    DocumentAllocationLink,
    DocumentSection,
    IdempotencyKey,
    InboundReceipt,
    InspectionCase,
    InternalResult,
    LotMergeApproval,
    Material,
    MaterialLot,
    MaterialModel,
    OutboxEvent,
    ReceiptLotAllocation,
    SampleMeasurement,
    SpecItem,
    SpecProfile,
    SpecVersion,
    StandardTestItem,
    Supplier,
    SupplierResult,
)
from hyc_data.repositories import (
    ApprovalPrecondition,
    ApprovalRepository,
    AuthorizationDenied,
    IdempotencyRepository,
    LotRepository,
    OptimisticConflict,
)
from hyc_domain.errors import CodedDomainError, FailureCode


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    with Session(engine) as value:
        yield value
        value.rollback()
    engine.dispose()


def _master(session: Session) -> tuple[Supplier, Material]:
    supplier, material = Supplier(name="Supplier"), Material(name="Material")
    session.add_all((supplier, material))
    session.commit()
    return supplier, material


def _merge_approvals() -> dict[str, object]:
    return {
        "quality_manager_id": uuid4(),
        "quality_admin_id": uuid4(),
        "reason": "synthetic duplicate identity evidence",
    }


def test_repository_conflict_and_authorization_errors_have_distinct_codes() -> None:
    assert issubclass(OptimisticConflict, CodedDomainError)
    assert OptimisticConflict.code is FailureCode.STALE_VERSION
    assert AuthorizationDenied.code is FailureCode.AUTHORIZATION_DENIED


def _spec_item(
    session: Session,
    supplier: Supplier,
    material: Material,
    *,
    status: str = "DRAFT",
) -> SpecItem:
    profile = SpecProfile(material_id=material.id, supplier_id=supplier.id, name="scope")
    session.add(profile)
    session.flush()
    version = SpecVersion(
        spec_profile_id=profile.id,
        version=1,
        status=status,
        effective_from=date(2026, 1, 1),
    )
    item = StandardTestItem(code=f"ITEM-{uuid4()}", name="item", data_type="NUMERIC")
    session.add_all((version, item))
    session.flush()
    spec_item = SpecItem(
        spec_version_id=version.id,
        standard_test_item_id=item.id,
        source_policy="INTERNAL_ONLY",
        missing_policy="HOLD",
        sample_policy="ALL_SAMPLES_IN_SPEC",
        operator="GTE",
        lower_value=Decimal("1"),
    )
    session.add(spec_item)
    session.commit()
    return spec_item


def _allocation(session: Session, supplier: Supplier, material: Material) -> ReceiptLotAllocation:
    lot = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="LOT|2026|A",
        identity_status="CANONICAL",
    )
    receipt = InboundReceipt(
        inbound_no=f"IN-{uuid4()}", supplier_id=supplier.id, receipt_date=date(2026, 1, 1)
    )
    session.add_all((lot, receipt))
    session.flush()
    allocation = ReceiptLotAllocation(
        inbound_receipt_id=receipt.id,
        material_lot_id=lot.id,
        quantity=Decimal("5"),
        quantity_unit="kg",
    )
    session.add(allocation)
    session.commit()
    return allocation


def _scoped_spec(
    session: Session,
    material: Material,
    *,
    supplier_id: UUID | None = None,
    model_id: UUID | None = None,
    version: int = 1,
    profile: SpecProfile | None = None,
) -> SpecVersion:
    if profile is None:
        profile = SpecProfile(
            material_id=material.id,
            supplier_id=supplier_id,
            model_id=model_id,
            name=f"scope-{uuid4()}",
        )
        session.add(profile)
        session.flush()
    spec = SpecVersion(
        spec_profile_id=profile.id,
        version=version,
        status="ACTIVE",
        effective_from=date(2026, 1, 1),
    )
    session.add(spec)
    session.flush()
    return spec


def _spec_selection_context(
    session: Session,
) -> tuple[
    Supplier,
    Material,
    MaterialModel,
    ReceiptLotAllocation,
    InboundReceipt,
    MaterialLot,
]:
    supplier, material = _master(session)
    model = MaterialModel(material_id=material.id, name=f"model-{uuid4()}")
    session.add(model)
    session.flush()
    allocation = _allocation(session, supplier, material)
    allocation.model_id = model.id
    session.flush()
    receipt = session.get(InboundReceipt, allocation.inbound_receipt_id)
    lot = session.get(MaterialLot, allocation.material_lot_id)
    assert receipt is not None
    assert lot is not None
    return supplier, material, model, allocation, receipt, lot


def _case_for_spec(
    session: Session, allocation: ReceiptLotAllocation, spec: SpecVersion
) -> InspectionCase:
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec.id,
        status="LEAD_REVIEW",
        submitted_by_id=uuid4(),
    )
    session.add(case)
    session.flush()
    return case


def test_repository_selects_exact_supplier_model_scope(session: Session) -> None:
    supplier, material, model, allocation, receipt, lot = _spec_selection_context(session)
    _scoped_spec(session, material)
    _scoped_spec(session, material, supplier_id=supplier.id)
    _scoped_spec(session, material, model_id=model.id)
    exact = _scoped_spec(
        session,
        material,
        supplier_id=supplier.id,
        model_id=model.id,
    )
    case = _case_for_spec(session, allocation, exact)
    selected, profile = ApprovalRepository()._effective_spec(
        session,
        case=case,
        allocation=allocation,
        receipt=receipt,
        lot=lot,
    )
    assert selected.id == exact.id
    assert profile.supplier_id == supplier.id
    assert profile.model_id == model.id


def test_repository_falls_back_when_model_scope_is_absent(session: Session) -> None:
    supplier, material, _, allocation, receipt, lot = _spec_selection_context(session)
    _scoped_spec(session, material)
    supplier_scope = _scoped_spec(session, material, supplier_id=supplier.id)
    case = _case_for_spec(session, allocation, supplier_scope)
    selected, profile = ApprovalRepository()._effective_spec(
        session,
        case=case,
        allocation=allocation,
        receipt=receipt,
        lot=lot,
    )
    assert selected.id == supplier_scope.id
    assert profile.supplier_id == supplier.id
    assert profile.model_id is None


def test_repository_never_selects_a_different_model_scope(session: Session) -> None:
    supplier, material, _, allocation, receipt, lot = _spec_selection_context(session)
    other_model = MaterialModel(material_id=material.id, name=f"other-{uuid4()}")
    session.add(other_model)
    session.flush()
    common = _scoped_spec(session, material)
    _scoped_spec(
        session,
        material,
        supplier_id=supplier.id,
        model_id=other_model.id,
    )
    case = _case_for_spec(session, allocation, common)
    selected, profile = ApprovalRepository()._effective_spec(
        session,
        case=case,
        allocation=allocation,
        receipt=receipt,
        lot=lot,
    )
    assert selected.id == common.id
    assert profile.model_id is None


def test_repository_denies_equal_specificity_ambiguity_and_scope_overlap(
    session: Session,
) -> None:
    supplier, material, model, allocation, receipt, lot = _spec_selection_context(session)
    supplier_scope = _scoped_spec(session, material, supplier_id=supplier.id)
    _scoped_spec(session, material, model_id=model.id)
    case = _case_for_spec(session, allocation, supplier_scope)
    with pytest.raises(ApprovalPrecondition, match="ambiguous"):
        ApprovalRepository()._effective_spec(
            session,
            case=case,
            allocation=allocation,
            receipt=receipt,
            lot=lot,
        )

    (
        second_supplier,
        second_material,
        second_model,
        second_allocation,
        second_receipt,
        second_lot,
    ) = _spec_selection_context(session)
    profile = SpecProfile(
        material_id=second_material.id,
        supplier_id=second_supplier.id,
        model_id=second_model.id,
        name="overlapping-exact-scope",
    )
    session.add(profile)
    session.flush()
    first = _scoped_spec(session, second_material, profile=profile, version=1)
    _scoped_spec(session, second_material, profile=profile, version=2)
    second_case = _case_for_spec(session, second_allocation, first)
    with pytest.raises(ApprovalPrecondition, match="ambiguous"):
        ApprovalRepository()._effective_spec(
            session,
            case=second_case,
            allocation=second_allocation,
            receipt=second_receipt,
            lot=second_lot,
        )


def _link_document(session: Session, allocation: ReceiptLotAllocation) -> None:
    document = Document(
        checksum_sha256=allocation.id.hex * 2,
        document_type="COA",
        original_filename="synthetic-coa.pdf",
    )
    session.add(document)
    session.flush()
    section = DocumentSection(
        document_id=document.id,
        section_index=0,
        page_from=1,
        page_to=1,
        status="MATCHED",
    )
    session.add(section)
    session.flush()
    session.add(
        DocumentAllocationLink(
            document_section_id=section.id,
            receipt_lot_allocation_id=allocation.id,
            match_status="CONFIRMED",
        )
    )
    session.commit()


def test_same_lot_can_reenter_and_split_across_receipts(session: Session) -> None:
    supplier, material = _master(session)
    lot = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="LOT|2026|A",
        identity_status="CANONICAL",
    )
    first, second = (
        InboundReceipt(inbound_no="IN-1", supplier_id=supplier.id, receipt_date=date(2026, 1, 1)),
        InboundReceipt(inbound_no="IN-2", supplier_id=supplier.id, receipt_date=date(2026, 1, 2)),
    )
    session.add_all((lot, first, second))
    session.flush()
    session.add_all(
        (
            ReceiptLotAllocation(
                inbound_receipt_id=first.id,
                material_lot_id=lot.id,
                quantity=Decimal("2"),
                quantity_unit="kg",
            ),
            ReceiptLotAllocation(
                inbound_receipt_id=second.id,
                material_lot_id=lot.id,
                quantity=Decimal("3"),
                quantity_unit="kg",
            ),
        )
    )
    session.commit()
    assert session.scalar(text("SELECT count(*) FROM receipt_lot_allocations")) == 2


def test_canonical_lot_unique_and_repository_get_or_create(session: Session) -> None:
    supplier, material = _master(session)
    repository = LotRepository()
    first = repository.get_or_create_canonical(
        session,
        MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key="same",
            identity_status="CANONICAL",
        ),
    )
    session.commit()
    second = repository.get_or_create_canonical(
        session,
        MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key="same",
            identity_status="CANONICAL",
        ),
    )
    assert second.id == first.id


def test_same_key_conflict_evidence_is_not_part_of_v1_identity(session: Session) -> None:
    supplier, material = _master(session)
    repository = LotRepository()
    first = repository.get_or_create_canonical(
        session,
        MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key="LOT-001",
            identity_status="CANONICAL",
            production_date_evidence="2026-01-01",
            package_mark_evidence="BAG",
        ),
    )
    session.commit()
    reentered = repository.get_or_create_canonical(
        session,
        MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key="LOT-001",
            identity_status="CANONICAL",
            production_date_evidence="2026-01-02",
            package_mark_evidence="BAG",
        ),
    )
    assert reentered.id == first.id
    assert reentered.identity_status == "CONFLICT_REVIEW"


def test_provisional_promotion_and_existing_key_resolution_are_explicit(
    session: Session,
) -> None:
    supplier, material = _master(session)
    repository = LotRepository()
    provisional = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="PROVISIONAL",
    )
    session.add(provisional)
    session.commit()
    promoted = repository.promote_provisional(
        session,
        lot_id=provisional.id,
        expected_version=1,
        supplier_lot_no_raw=" LOT-001 ",
        identity_key="LOT-001",
    )
    assert promoted.id == provisional.id
    assert promoted.identity_status == "CANONICAL"
    assert promoted.lock_version == 2

    second = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="PROVISIONAL",
    )
    session.add(second)
    session.commit()
    survivor = repository.promote_provisional(
        session,
        lot_id=second.id,
        expected_version=1,
        supplier_lot_no_raw="LOT-001",
        identity_key="LOT-001",
    )
    assert survivor.id == promoted.id
    assert second.identity_status == "CONFLICT_REVIEW"


def test_sample_xor_and_operator_required_columns_are_database_constraints(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material)
    allocation = _allocation(session, supplier, material)
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id, spec_version_id=spec_item.spec_version_id
    )
    session.add(case)
    session.flush()
    internal = InternalResult(inspection_case_id=case.id, spec_item_id=spec_item.id)
    supplier_result = SupplierResult(
        inspection_case_id=case.id, supplier_item_name="raw", mapping_status="UNMAPPED"
    )
    session.add_all((internal, supplier_result))
    session.flush()
    session.add(
        SampleMeasurement(
            internal_result_id=internal.id, supplier_result_id=supplier_result.id, sample_index=1
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    bad_item = SpecItem(
        spec_version_id=spec_item.spec_version_id,
        standard_test_item_id=spec_item.standard_test_item_id,
        source_policy="INTERNAL_ONLY",
        operator="BETWEEN_INCLUSIVE",
    )
    session.add(bad_item)
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("source_policy", "NOT_A_POLICY"),
        ("missing_policy", "NOT_A_POLICY"),
        ("sample_policy", "NOT_A_POLICY"),
    ),
)
def test_invalid_persisted_policy_is_rejected(
    session: Session,
    field: str,
    value: str,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material)
    setattr(spec_item, field, value)
    with pytest.raises(IntegrityError):
        session.commit()


def test_every_quality_numeric_column_rejects_python_float(session: Session) -> None:
    strict_columns = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.type.__class__.__name__ == "StrictNumeric"
    }
    assert strict_columns == {
        # P7 traceability quantities are Decimal for the same reason every other
        # quantity here is: a float BOM quantity silently drifts on multiplication.
        "bill_of_materials.quantity",
        "extraction_field_reviews.confidence",
        "internal_results.evaluated_value",
        "material_lot_consumptions.consumed_quantity",
        "nonconformances.quantity",
        "production_lots.quantity",
        "receipt_lot_allocations.quantity",
        "sample_measurements.numeric_value",
        "spec_items.lower_value",
        "spec_items.target_value",
        "spec_items.tolerance",
        "spec_items.upper_value",
        "supplier_results.normalized_value",
    }
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if column.type.__class__.__name__ == "StrictNumeric":
                with pytest.raises(TypeError):
                    column.type.process_bind_param(0.1, session.get_bind().dialect)

    supplier, material = _master(session)
    lot = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="FLOAT",
        identity_status="CANONICAL",
    )
    receipt = InboundReceipt(
        inbound_no="FLOAT-IN",
        supplier_id=supplier.id,
        receipt_date=date(2026, 1, 1),
    )
    session.add_all((lot, receipt))
    session.flush()
    session.add(
        ReceiptLotAllocation(
            inbound_receipt_id=receipt.id,
            material_lot_id=lot.id,
            quantity=0.1 + 0.2,  # type: ignore[arg-type]
            quantity_unit="kg",
        )
    )
    with pytest.raises(StatementError):
        session.commit()


def test_document_checksum_dedupe_sections_and_allocation_links(session: Session) -> None:
    supplier, material = _master(session)
    allocation = _allocation(session, supplier, material)
    document = Document(
        checksum_sha256="a" * 64, document_type="COA", original_filename="fixture.pdf"
    )
    session.add(document)
    session.flush()
    section = DocumentSection(document_id=document.id, section_index=0, page_from=1, page_to=1)
    session.add(section)
    session.flush()
    session.add(
        DocumentAllocationLink(
            document_section_id=section.id,
            receipt_lot_allocation_id=allocation.id,
            match_status="CONFIRMED",
        )
    )
    session.commit()
    session.add(
        Document(checksum_sha256="a" * 64, document_type="COA", original_filename="again.pdf")
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_boundary_constraints_reject_uppercase_hash_nonpositive_quantity_and_page_range(
    session: Session,
) -> None:
    supplier, material = _master(session)
    allocation = _allocation(session, supplier, material)
    session.add(
        Document(
            checksum_sha256="A" * 64,
            document_type="COA",
            original_filename="uppercase.pdf",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(
        Document(
            checksum_sha256="g" * 64,
            document_type="COA",
            original_filename="non-hex.pdf",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    receipt = InboundReceipt(
        inbound_no=f"ZERO-{uuid4()}",
        supplier_id=supplier.id,
        receipt_date=date(2026, 1, 2),
    )
    session.add(receipt)
    session.flush()
    session.add(
        ReceiptLotAllocation(
            inbound_receipt_id=receipt.id,
            material_lot_id=allocation.material_lot_id,
            quantity=Decimal("0"),
            quantity_unit="kg",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    document = Document(
        checksum_sha256="b" * 64,
        document_type="COA",
        original_filename="pages.pdf",
    )
    session.add(document)
    session.flush()
    session.add(
        DocumentSection(
            document_id=document.id,
            section_index=0,
            page_from=2,
            page_to=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_portable_mapping_decision_checksum_and_correction_constraints(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material)
    allocation = _allocation(session, supplier, material)
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
        candidate_decision="PASS",
    )
    session.add(case)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    valid_case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
    )
    session.add(valid_case)
    session.flush()
    session.add(
        SupplierResult(
            inspection_case_id=valid_case.id,
            standard_test_item_id=None,
            supplier_item_name="synthetic",
            mapping_status="MANUAL_CONFIRMED",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        Document(
            checksum_sha256="short",
            document_type="COA",
            original_filename="synthetic.pdf",
            immutable=False,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    session.add(
        InspectionCase(
            receipt_lot_allocation_id=allocation.id,
            spec_version_id=spec_item.spec_version_id,
            correction_of_case_id=valid_case.id,
            revision_no=1,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_duplicate_snapshot_hash_is_allowed_for_different_inspection_cases(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material)
    first_allocation = _allocation(session, supplier, material)
    second_receipt = InboundReceipt(
        inbound_no=f"IN-{uuid4()}", supplier_id=supplier.id, receipt_date=date(2026, 1, 2)
    )
    session.add(second_receipt)
    session.flush()
    second_allocation = ReceiptLotAllocation(
        inbound_receipt_id=second_receipt.id,
        material_lot_id=first_allocation.material_lot_id,
        quantity=Decimal("2"),
        quantity_unit="kg",
    )
    session.add(second_allocation)
    session.flush()
    first_case = InspectionCase(
        receipt_lot_allocation_id=first_allocation.id, spec_version_id=spec_item.spec_version_id
    )
    second_case = InspectionCase(
        receipt_lot_allocation_id=second_allocation.id, spec_version_id=spec_item.spec_version_id
    )
    session.add_all((first_case, second_case))
    session.flush()
    session.add_all(
        (
            DecisionSnapshotRow(
                inspection_case_id=first_case.id,
                payload={"decision": "ACCEPTED"},
                content_hash="a" * 64,
            ),
            DecisionSnapshotRow(
                inspection_case_id=second_case.id,
                payload={"decision": "ACCEPTED"},
                content_hash="a" * 64,
            ),
        )
    )
    session.commit()
    assert (
        session.scalar(
            text("SELECT count(*) FROM decision_snapshots WHERE content_hash = :hash"),
            {"hash": "a" * 64},
        )
        == 2
    )


def test_approval_repository_writes_snapshot_approval_audit_outbox_atomically(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material, status="ACTIVE")
    allocation = _allocation(session, supplier, material)
    _link_document(session, allocation)
    inspector_id = uuid4()
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
        status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    session.add(case)
    session.flush()
    session.add(
        InternalResult(
            inspection_case_id=case.id,
            spec_item_id=spec_item.id,
            evaluated_value=Decimal("2"),
            decision="ACCEPTED",
        )
    )
    session.commit()
    with pytest.raises(AuthorizationDenied):
        ApprovalRepository().finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=uuid4(),
            actor_role="INSPECTOR",
            final_decision="ACCEPTED",
        )
    with pytest.raises(AuthorizationDenied):
        ApprovalRepository().finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=uuid4(),
            actor_role="ADMIN",
            final_decision="ACCEPTED",
        )
    assert session.scalar(select(func.count()).select_from(DecisionSnapshotRow)) == 0
    lead_id = uuid4()
    finalized = ApprovalRepository().finalize(
        session,
        case_id=case.id,
        expected_version=1,
        actor_id=lead_id,
        actor_role="LEAD",
        final_decision="ACCEPTED",
    )
    session.commit()
    assert finalized.lock_version == 2
    assert session.scalar(select(func.count()).select_from(DecisionSnapshotRow)) == 1
    assert session.scalar(select(func.count()).select_from(Approval)) == 1
    assert session.scalar(select(func.count()).select_from(AuditLog)) == 1
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    snapshot_row = session.scalar(select(DecisionSnapshotRow))
    assert snapshot_row is not None
    assert snapshot_row.payload["approver"] == {"actor_id": str(lead_id), "role": "LEAD"}
    assert snapshot_row.payload["overall_decision"] == "ACCEPTED"


def test_finalize_signature_has_no_caller_authoritative_candidate_or_snapshot() -> None:
    parameters = signature(ApprovalRepository.finalize).parameters
    assert {
        "candidate_decision",
        "snapshot",
        "re_evaluated",
    }.isdisjoint(parameters)


def test_draft_spec_and_same_actor_finalization_fail_without_partial_mutation(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material, status="DRAFT")
    allocation = _allocation(session, supplier, material)
    _link_document(session, allocation)
    inspector_id = uuid4()
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
        status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    session.add(case)
    session.flush()
    session.add(
        InternalResult(
            inspection_case_id=case.id,
            spec_item_id=spec_item.id,
            evaluated_value=Decimal("2"),
        )
    )
    session.commit()
    repository = ApprovalRepository()
    with pytest.raises(AuthorizationDenied):
        repository.finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=inspector_id,
            actor_role="LEAD",
            final_decision="ACCEPTED",
        )
    session.rollback()
    with pytest.raises(ApprovalPrecondition, match="ACTIVE"):
        repository.finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=uuid4(),
            actor_role="LEAD",
            final_decision="ACCEPTED",
        )
    session.rollback()
    assert session.get(InspectionCase, case.id).final_decision is None
    for model in (DecisionSnapshotRow, Approval, AuditLog, OutboxEvent):
        assert session.scalar(select(func.count()).select_from(model)) == 0


def test_rejected_candidate_cannot_be_overridden_as_plain_accepted(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material, status="ACTIVE")
    spec_item.lower_value = Decimal("10")
    allocation = _allocation(session, supplier, material)
    _link_document(session, allocation)
    inspector_id = uuid4()
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
        status="LEAD_REVIEW",
        submitted_by_id=inspector_id,
    )
    session.add(case)
    session.flush()
    session.add(
        InternalResult(
            inspection_case_id=case.id,
            spec_item_id=spec_item.id,
            evaluated_value=Decimal("1"),
        )
    )
    session.commit()
    repository = ApprovalRepository()
    with pytest.raises(ApprovalPrecondition, match="SPECIAL_ACCEPTED"):
        repository.finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=uuid4(),
            actor_role="LEAD",
            final_decision="ACCEPTED",
            reason="attempted override",
        )
    session.rollback()
    assert session.get(InspectionCase, case.id).final_decision is None
    finalized = repository.finalize(
        session,
        case_id=case.id,
        expected_version=1,
        actor_id=uuid4(),
        actor_role="LEAD",
        final_decision="SPECIAL_ACCEPTED",
        reason="authorized special acceptance",
    )
    session.commit()
    assert finalized.candidate_decision == "REJECTED"
    assert finalized.final_decision == "SPECIAL_ACCEPTED"


def test_on_hold_candidate_cannot_be_overridden_as_plain_accepted(
    session: Session,
) -> None:
    supplier, material = _master(session)
    spec_item = _spec_item(session, supplier, material, status="ACTIVE")
    allocation = _allocation(session, supplier, material)
    _link_document(session, allocation)
    case = InspectionCase(
        receipt_lot_allocation_id=allocation.id,
        spec_version_id=spec_item.spec_version_id,
        status="LEAD_REVIEW",
        submitted_by_id=uuid4(),
    )
    session.add(case)
    session.commit()
    repository = ApprovalRepository()
    with pytest.raises(ApprovalPrecondition, match="SPECIAL_ACCEPTED"):
        repository.finalize(
            session,
            case_id=case.id,
            expected_version=1,
            actor_id=uuid4(),
            actor_role="LEAD",
            final_decision="ACCEPTED",
            reason="attempted fail-closed override",
        )
    session.rollback()
    persisted_case = session.get(InspectionCase, case.id)
    assert persisted_case is not None
    assert persisted_case.candidate_decision is None
    assert persisted_case.final_decision is None
    assert persisted_case.status == "LEAD_REVIEW"
    for model in (DecisionSnapshotRow, Approval, AuditLog, OutboxEvent):
        assert session.scalar(select(func.count()).select_from(model)) == 0

    finalized = repository.finalize(
        session,
        case_id=case.id,
        expected_version=1,
        actor_id=uuid4(),
        actor_role="LEAD",
        final_decision="SPECIAL_ACCEPTED",
        reason="authorized special acceptance of incomplete required evidence",
    )
    session.commit()
    assert finalized.candidate_decision == "ON_HOLD"
    assert finalized.final_decision == "SPECIAL_ACCEPTED"


def test_lot_merge_uses_lock_version_not_semantic_spec_version(session: Session) -> None:
    supplier, material = _master(session)
    target = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="target-lock",
        identity_status="CANONICAL",
    )
    source = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="CONFLICT_REVIEW",
    )
    session.add_all((target, source))
    session.commit()
    same_actor = uuid4()
    with pytest.raises(AuthorizationDenied):
        LotRepository().guarded_merge(
            session,
            lot_id=source.id,
            expected_version=1,
            merged_into_id=target.id,
            quality_manager_id=same_actor,
            quality_admin_id=same_actor,
            reason="same actor must fail",
        )
    with pytest.raises(OptimisticConflict):
        LotRepository().guarded_merge(
            session,
            lot_id=source.id,
            expected_version=2,
            merged_into_id=target.id,
            **_merge_approvals(),
        )
    assert (
        LotRepository()
        .guarded_merge(
            session,
            lot_id=source.id,
            expected_version=1,
            merged_into_id=target.id,
            **_merge_approvals(),
        )
        .lock_version
        == 2
    )


def test_reentry_of_merged_identity_follows_bounded_surviving_lot(
    session: Session,
) -> None:
    supplier, material = _master(session)
    survivor = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="SURVIVOR",
        identity_status="CANONICAL",
    )
    session.add(survivor)
    session.flush()
    merged = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="OLD-KEY",
        identity_status="MERGED",
        merged_into_id=survivor.id,
    )
    session.add(merged)
    session.commit()
    resolved = LotRepository().get_or_create_canonical(
        session,
        MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key="OLD-KEY",
            identity_status="CANONICAL",
        ),
    )
    assert resolved.id == survivor.id
    assert resolved.identity_status == "CANONICAL"


def test_ordinary_orm_update_bumps_lock_version_exactly_once(session: Session) -> None:
    supplier, _ = _master(session)
    assert supplier.lock_version == 1
    supplier.name = "renamed"
    session.commit()
    assert supplier.lock_version == 2
    session.commit()
    assert supplier.lock_version == 2


@pytest.mark.parametrize("identity_key", (None, "source-evidence"))
def test_guarded_merge_requires_expected_version_and_conflict_state(
    session: Session, identity_key: str | None
) -> None:
    supplier, material = _master(session)
    target = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="target",
        identity_status="CANONICAL",
    )
    source = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=identity_key,
        identity_status="CONFLICT_REVIEW",
    )
    session.add_all((target, source))
    session.commit()
    merged = LotRepository().guarded_merge(
        session,
        lot_id=source.id,
        expected_version=1,
        merged_into_id=target.id,
        **_merge_approvals(),
    )
    assert merged.identity_status == "MERGED"
    assert merged.identity_key == identity_key
    assert merged.merged_into_id == target.id
    assert merged.lock_version == 2
    assert (
        session.scalar(
            select(func.count())
            .select_from(LotMergeApproval)
            .where(LotMergeApproval.material_lot_id == source.id)
        )
        == 2
    )
    assert (
        session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.entity_id == source.id, AuditLog.action == "LOT_MERGED")
        )
        == 1
    )
    with pytest.raises(OptimisticConflict):
        LotRepository().guarded_merge(
            session,
            lot_id=source.id,
            expected_version=1,
            merged_into_id=target.id,
            **_merge_approvals(),
        )


@pytest.mark.parametrize(
    ("identity_status", "identity_key", "merged_into_id", "is_valid"),
    (
        ("PROVISIONAL", None, None, True),
        ("PROVISIONAL", "source-evidence", None, True),
        ("CONFLICT_REVIEW", None, None, True),
        ("CONFLICT_REVIEW", "source-evidence", None, True),
        ("CANONICAL", "canonical", None, True),
        ("MERGED", None, uuid4(), True),
        ("MERGED", "original-evidence", uuid4(), True),
        ("PROVISIONAL", None, uuid4(), False),
        ("CONFLICT_REVIEW", None, uuid4(), False),
        ("CANONICAL", None, None, False),
        ("CANONICAL", "canonical", uuid4(), False),
        ("MERGED", None, None, False),
        ("MERGED", "original-evidence", None, False),
    ),
)
def test_material_lot_identity_status_constraint_is_portable(
    session: Session,
    identity_status: str,
    identity_key: str | None,
    merged_into_id: UUID | None,
    is_valid: bool,
) -> None:
    supplier, material = _master(session)
    target_id = merged_into_id
    if target_id is not None:
        target = MaterialLot(
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key=f"target-{uuid4()}",
            identity_status="CANONICAL",
        )
        session.add(target)
        session.flush()
        target_id = target.id
    lot = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=identity_key,
        identity_status=identity_status,
        merged_into_id=target_id,
    )
    session.add(lot)
    if is_valid:
        session.commit()
    else:
        with pytest.raises(IntegrityError):
            session.commit()


def test_material_lot_identity_status_constraint_rejects_self_merge(session: Session) -> None:
    supplier, material = _master(session)
    lot_id = uuid4()
    session.add(
        MaterialLot(
            id=lot_id,
            supplier_id=supplier.id,
            material_id=material.id,
            identity_policy_version="v1",
            identity_key=None,
            identity_status="MERGED",
            merged_into_id=lot_id,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_guarded_merge_rejects_invalid_source_and_target_combinations(session: Session) -> None:
    supplier, material = _master(session)
    repository = LotRepository()
    canonical = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="canonical",
        identity_status="CANONICAL",
    )
    conflict = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="CONFLICT_REVIEW",
    )
    provisional = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="PROVISIONAL",
    )
    deleted = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key="deleted",
        identity_status="CANONICAL",
        deleted_at=datetime.now(UTC),
    )
    session.add_all((canonical, conflict, provisional, deleted))
    session.flush()
    merged_target = MaterialLot(
        supplier_id=supplier.id,
        material_id=material.id,
        identity_policy_version="v1",
        identity_key=None,
        identity_status="MERGED",
        merged_into_id=canonical.id,
    )
    session.add(merged_target)
    session.commit()
    for lot_id, expected_version, target_id in (
        (conflict.id, 1, conflict.id),
        (conflict.id, 1, uuid4()),
        (conflict.id, 2, canonical.id),
        (provisional.id, 1, canonical.id),
        (conflict.id, 1, provisional.id),
        (conflict.id, 1, merged_target.id),
        (conflict.id, 1, deleted.id),
    ):
        with pytest.raises(OptimisticConflict):
            repository.guarded_merge(
                session,
                lot_id=lot_id,
                expected_version=expected_version,
                merged_into_id=target_id,
                **_merge_approvals(),
            )
    conflict.deleted_at = datetime.now(UTC)
    session.commit()
    with pytest.raises(OptimisticConflict):
        repository.guarded_merge(
            session,
            lot_id=conflict.id,
            expected_version=1,
            merged_into_id=canonical.id,
            **_merge_approvals(),
        )


def test_idempotency_db_replays_same_hash_and_conflicts_on_hash_change(session: Session) -> None:
    repository = IdempotencyRepository()
    now = datetime.now(UTC)
    first = repository.reserve(
        session,
        principal_id="quality-a",
        scope="inspection.create",
        key="key-1",
        request_hash="a" * 64,
        now=now,
        lease_for=timedelta(minutes=1),
    )
    session.commit()
    assert (
        repository.reserve(
            session,
            principal_id="quality-a",
            scope="inspection.create",
            key="key-1",
            request_hash="a" * 64,
            now=now,
            lease_for=timedelta(minutes=1),
        ).id
        == first.id
    )
    with pytest.raises(OptimisticConflict):
        repository.reserve(
            session,
            principal_id="quality-a",
            scope="inspection.create",
            key="key-1",
            request_hash="b" * 64,
            now=now,
            lease_for=timedelta(minutes=1),
        )
    assert (
        repository.reserve(
            session,
            principal_id="quality-b",
            scope="inspection.create",
            key="key-1",
            request_hash="a" * 64,
            now=now,
            lease_for=timedelta(minutes=1),
        ).principal_id
        == "quality-b"
    )
    session.add(
        IdempotencyKey(
            principal_id="quality-a",
            scope="inspection.create",
            key="key-1",
            request_hash="c" * 64,
            state="PENDING",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_idempotency_row_preserves_optional_expiry_timestamp(session: Session) -> None:
    expires_at = datetime(2026, 8, 1, tzinfo=UTC)
    record = IdempotencyKey(
        principal_id="quality-a",
        scope="inspection.create",
        key="expires-at",
        request_hash="a" * 64,
        state="PENDING",
        expires_at=expires_at,
    )
    session.add(record)
    session.commit()
    stored = session.get(IdempotencyKey, record.id).expires_at
    assert stored is not None
    # SQLite stores DateTime values without an offset; the canonical test value is UTC.
    assert stored.replace(tzinfo=UTC) == expires_at


def test_idempotency_database_rejects_noncanonical_state(session: Session) -> None:
    session.add(
        IdempotencyKey(
            principal_id="quality-a",
            scope="inspection.create",
            key="invalid-state",
            request_hash="a" * 64,
            state="UNKNOWN",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
