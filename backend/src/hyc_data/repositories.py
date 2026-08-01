from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from hyc_data.models import (
    Approval,
    AuditLog,
    DecisionSnapshotRow,
    Document,
    DocumentAllocationLink,
    DocumentSection,
    IdempotencyKey,
    InboundReceipt,
    InspectionCase,
    InternalResult,
    LotMergeApproval,
    MaterialLot,
    MaterialModel,
    OutboxEvent,
    ReceiptLotAllocation,
    SampleMeasurement,
    SpecItem,
    SpecProfile,
    SpecVersion,
    SupplierResult,
)
from hyc_domain.errors import CodedDomainError, FailureCode
from hyc_domain.judgment import (
    EngineDecision,
    ItemEvaluation,
    ItemInput,
    JudgmentEngine,
    MappingStatus,
    MissingPolicy,
    SamplePolicy,
    SourcePolicy,
    WorkflowState,
)
from hyc_domain.lots import LotIdentityStatus, can_merge
from hyc_domain.snapshots import DecisionSnapshot
from hyc_domain.specs import Operator, Rule
from hyc_domain.workflow import StateTransitionError, guard_transition


class OptimisticConflict(CodedDomainError):
    code = FailureCode.STALE_VERSION


class ApprovalPrecondition(CodedDomainError):
    code = FailureCode.APPROVAL_PRECONDITION_FAILED


class AuthorizationDenied(CodedDomainError):
    code = FailureCode.AUTHORIZATION_DENIED


class LotRepository:
    MAX_MERGE_DEPTH = 16

    def _surviving_lot(self, session: Session, lot: MaterialLot) -> MaterialLot:
        visited: set[UUID] = set()
        current = lot
        for _ in range(self.MAX_MERGE_DEPTH):
            if current.id in visited:
                raise ApprovalPrecondition("LOT merge chain contains a cycle")
            visited.add(current.id)
            if current.identity_status != "MERGED":
                if current.identity_status != "CANONICAL" or current.merged_into_id is not None:
                    raise ApprovalPrecondition(
                        "LOT identity does not resolve to a canonical survivor"
                    )
                return current
            if current.merged_into_id is None:
                raise ApprovalPrecondition("merged LOT has no surviving canonical reference")
            next_lot = session.get(MaterialLot, current.merged_into_id)
            if next_lot is None or next_lot.deleted_at is not None:
                raise ApprovalPrecondition("merged LOT survivor is unavailable")
            current = next_lot
        raise ApprovalPrecondition("LOT merge chain exceeds the bounded resolution depth")

    @staticmethod
    def _apply_conflict_evidence(existing: MaterialLot, candidate: MaterialLot) -> None:
        for attribute in ("production_date_evidence", "package_mark_evidence"):
            old = getattr(existing, attribute)
            new = getattr(candidate, attribute)
            if old is None and new is not None:
                setattr(existing, attribute, new)
            elif old is not None and new is not None and old != new:
                existing.identity_status = "CONFLICT_REVIEW"

    def get_or_create_canonical(self, session: Session, candidate: MaterialLot) -> MaterialLot:
        if candidate.identity_key is None or candidate.identity_status != "CANONICAL":
            session.add(candidate)
            session.flush()
            return candidate
        try:
            with session.begin_nested():
                session.add(candidate)
                session.flush()
            return candidate
        except IntegrityError:
            existing = session.scalar(
                select(MaterialLot).where(
                    MaterialLot.supplier_id == candidate.supplier_id,
                    MaterialLot.material_id == candidate.material_id,
                    MaterialLot.identity_policy_version == candidate.identity_policy_version,
                    MaterialLot.identity_key == candidate.identity_key,
                )
            )
            if existing is None:
                raise
            survivor = (
                self._surviving_lot(session, existing)
                if existing.identity_status == "MERGED"
                else existing
            )
            self._apply_conflict_evidence(survivor, candidate)
            session.flush()
            return survivor

    def promote_provisional(
        self,
        session: Session,
        *,
        lot_id: UUID,
        expected_version: int,
        supplier_lot_no_raw: str,
        identity_key: str,
        production_date_evidence: str | None = None,
        package_mark_evidence: str | None = None,
    ) -> MaterialLot:
        lot = session.get(MaterialLot, lot_id, with_for_update=True)
        if (
            lot is None
            or lot.deleted_at is not None
            or lot.lock_version != expected_version
            or lot.identity_status != "PROVISIONAL"
            or lot.identity_key is not None
            or not supplier_lot_no_raw.strip()
            or not identity_key.strip()
        ):
            raise OptimisticConflict("provisional LOT promotion version/state does not match")
        existing = session.scalar(
            select(MaterialLot).where(
                MaterialLot.id != lot.id,
                MaterialLot.supplier_id == lot.supplier_id,
                MaterialLot.material_id == lot.material_id,
                MaterialLot.identity_policy_version == lot.identity_policy_version,
                MaterialLot.identity_key == identity_key,
                MaterialLot.deleted_at.is_(None),
            )
        )
        if existing is not None:
            lot.identity_status = "CONFLICT_REVIEW"
            lot.supplier_lot_no_raw = supplier_lot_no_raw
            lot.production_date_evidence = production_date_evidence
            lot.package_mark_evidence = package_mark_evidence
            session.flush()
            return self._surviving_lot(session, existing)
        lot.identity_key = identity_key
        lot.identity_status = "CANONICAL"
        lot.supplier_lot_no_raw = supplier_lot_no_raw
        lot.production_date_evidence = production_date_evidence
        lot.package_mark_evidence = package_mark_evidence
        session.flush()
        return lot

    def guarded_merge(
        self,
        session: Session,
        *,
        lot_id: UUID,
        expected_version: int,
        merged_into_id: UUID,
        quality_manager_id: UUID,
        quality_admin_id: UUID,
        reason: str,
    ) -> MaterialLot:
        if not can_merge(
            status=LotIdentityStatus.CONFLICT_REVIEW,
            expected_version=expected_version,
            current_version=expected_version,
            lead_actor_id=quality_manager_id,
            admin_actor_id=quality_admin_id,
            reason=reason,
        ):
            raise AuthorizationDenied(
                "LOT merge requires distinct LEAD quality and ADMIN master-data actors"
            )
        if session.bind is not None and session.bind.dialect.name == "postgresql":
            session.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": "|".join(sorted((str(lot_id), str(merged_into_id))))},
            )
        lot = session.get(MaterialLot, lot_id, with_for_update=True)
        if (
            lot is None
            or lot.deleted_at is not None
            or lot.lock_version != expected_version
            or lot.identity_status != "CONFLICT_REVIEW"
            or lot.merged_into_id is not None
            or lot_id == merged_into_id
        ):
            raise OptimisticConflict("lot merge expected version/state does not match")
        target = session.get(MaterialLot, merged_into_id, with_for_update=True)
        if (
            target is None
            or target.deleted_at is not None
            or target.identity_status != "CANONICAL"
            or target.identity_key is None
            or target.merged_into_id is not None
            or target.supplier_id != lot.supplier_id
            or target.material_id != lot.material_id
            or target.identity_policy_version != lot.identity_policy_version
        ):
            raise OptimisticConflict("lot merge target is not an active canonical lot")
        session.add_all(
            (
                LotMergeApproval(
                    material_lot_id=lot.id,
                    role="LEAD",
                    actor_id=quality_manager_id,
                ),
                LotMergeApproval(
                    material_lot_id=lot.id,
                    role="ADMIN",
                    actor_id=quality_admin_id,
                ),
                AuditLog(
                    entity_type="material_lot",
                    entity_id=lot.id,
                    action="LOT_MERGED",
                    reason=reason.strip(),
                    payload={"merged_into_id": str(target.id)},
                ),
            )
        )
        lot.identity_status = "MERGED"
        lot.merged_into_id = merged_into_id
        session.flush()
        return lot


class IdempotencyRepository:
    def reserve(
        self,
        session: Session,
        *,
        principal_id: str,
        scope: str,
        key: str,
        request_hash: str,
        now: datetime,
        lease_for: timedelta,
        lease_owner: str | None = None,
    ) -> IdempotencyKey:
        record = session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.principal_id == principal_id,
                IdempotencyKey.scope == scope,
                IdempotencyKey.key == key,
            )
        )
        if record is not None:
            if record.request_hash != request_hash:
                raise OptimisticConflict("idempotency key reused with different request hash")
            if record.state == "COMPLETED":
                return record
            comparison_now = (
                now
                if record.lease_expires_at is None or record.lease_expires_at.tzinfo is not None
                else now.replace(tzinfo=None)
            )
            if (
                record.state == "PENDING"
                and record.lease_expires_at is not None
                and record.lease_expires_at > comparison_now
            ):
                if (
                    record.lease_owner is not None
                    and lease_owner is not None
                    and record.lease_owner != lease_owner
                ):
                    raise OptimisticConflict("idempotency lease is owned by another worker")
                return record
            record.state = "PENDING"
            record.lease_expires_at = now + lease_for
            record.lease_owner = lease_owner
            record.updated_at = now
            session.flush()
            return record
        candidate = IdempotencyKey(
            principal_id=principal_id,
            scope=scope,
            key=key,
            request_hash=request_hash,
            state="PENDING",
            lease_expires_at=now + lease_for,
            lease_owner=lease_owner,
        )
        try:
            with session.begin_nested():
                session.add(candidate)
                session.flush()
            return candidate
        except IntegrityError as error:
            record = session.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.principal_id == principal_id,
                    IdempotencyKey.scope == scope,
                    IdempotencyKey.key == key,
                )
            )
            if record is None:
                raise
            if record.request_hash != request_hash:
                raise OptimisticConflict(
                    "idempotency key reused with different request hash"
                ) from error
            return record


class ApprovalRepository:
    ENGINE_VERSION = "P2_JUDGMENT_ENGINE_V1"
    POLICY_VERSION = "P2_FAIL_CLOSED_POLICY_V1"
    ROUNDING_VERSION = "P2_HALF_EVEN_V1"
    CONVERSION_VERSION = "P2_NORMALIZED_PERSISTENCE_V1"
    FINAL_DECISIONS = frozenset(
        {"ACCEPTED", "REJECTED", "ON_HOLD", "RETEST", "SPECIAL_ACCEPTED"}
    )

    @staticmethod
    def _rule(item: SpecItem) -> Rule:
        try:
            operator = Operator(item.operator)
        except ValueError as error:
            raise ApprovalPrecondition("persisted specification operator is invalid") from error
        allowed = frozenset(item.allowed_values or ())
        rule = Rule(
            operator,
            lower=item.lower_value,
            upper=item.upper_value,
            target=item.target_value,
            tolerance=item.tolerance,
            allowed=allowed,
        )
        try:
            rule.validate()
        except ValueError as error:
            raise ApprovalPrecondition("persisted specification rule is invalid") from error
        return rule

    @staticmethod
    def _enum(enum_type: type[Any], value: str, label: str) -> Any:
        try:
            return enum_type(value)
        except ValueError as error:
            raise ApprovalPrecondition(f"persisted {label} is invalid") from error

    def _effective_spec(
        self,
        session: Session,
        *,
        case: InspectionCase,
        allocation: ReceiptLotAllocation,
        receipt: InboundReceipt,
        lot: MaterialLot,
    ) -> tuple[SpecVersion, SpecProfile]:
        if allocation.model_id is not None:
            model = session.get(MaterialModel, allocation.model_id)
            if (
                model is None
                or model.deleted_at is not None
                or model.material_id != lot.material_id
            ):
                raise ApprovalPrecondition(
                    "inspection allocation model does not belong to its LOT material"
                )
        candidates = list(
            session.execute(
                select(SpecVersion, SpecProfile)
                .join(SpecProfile, SpecProfile.id == SpecVersion.spec_profile_id)
                .where(
                    SpecVersion.status == "ACTIVE",
                    SpecVersion.effective_from <= receipt.receipt_date,
                    (SpecVersion.effective_to.is_(None))
                    | (SpecVersion.effective_to >= receipt.receipt_date),
                    SpecProfile.material_id == lot.material_id,
                    (SpecProfile.supplier_id.is_(None))
                    | (SpecProfile.supplier_id == lot.supplier_id),
                    (SpecProfile.model_id.is_(None))
                    | (SpecProfile.model_id == allocation.model_id),
                )
            ).all()
        )
        if not candidates:
            raise ApprovalPrecondition("no ACTIVE effective specification is available")
        candidates.sort(
            key=lambda row: (
                int(row[1].supplier_id is not None) + int(row[1].model_id is not None),
                row[0].version,
                str(row[0].id),
            ),
            reverse=True,
        )
        selected_specificity = int(candidates[0][1].supplier_id is not None) + int(
            candidates[0][1].model_id is not None
        )
        if (
            len(candidates) > 1
            and int(candidates[1][1].supplier_id is not None)
            + int(candidates[1][1].model_id is not None)
            == selected_specificity
        ):
            raise ApprovalPrecondition("ambiguous ACTIVE effective specification scope")
        selected, profile = candidates[0]
        if selected.id != case.spec_version_id:
            raise ApprovalPrecondition(
                "case is not bound to the selected ACTIVE effective specification"
            )
        if allocation.material_lot_id != lot.id:
            raise ApprovalPrecondition("case allocation and canonical LOT do not match")
        return selected, profile

    @staticmethod
    def _numeric_samples(
        session: Session,
        *,
        supplier_result: SupplierResult | None = None,
        internal_result: InternalResult | None = None,
    ) -> tuple[Decimal, ...]:
        query = select(SampleMeasurement.numeric_value).where(
            SampleMeasurement.numeric_value.is_not(None)
        )
        fallback: Decimal | None
        if supplier_result is not None:
            query = query.where(SampleMeasurement.supplier_result_id == supplier_result.id)
            fallback = supplier_result.normalized_value
        elif internal_result is not None:
            query = query.where(SampleMeasurement.internal_result_id == internal_result.id)
            fallback = internal_result.evaluated_value
        else:
            return ()
        samples = tuple(value for value in session.scalars(query) if value is not None)
        if samples:
            return samples
        return () if fallback is None else (fallback,)

    def _persisted_inputs(
        self,
        session: Session,
        *,
        case: InspectionCase,
        spec_version: SpecVersion,
    ) -> tuple[
        tuple[SpecItem, ...],
        tuple[SupplierResult, ...],
        tuple[InternalResult, ...],
        tuple[ItemInput, ...],
        tuple[ItemEvaluation, ...],
    ]:
        spec_items = tuple(
            session.scalars(
                select(SpecItem)
                .where(
                    SpecItem.spec_version_id == spec_version.id,
                    SpecItem.deleted_at.is_(None),
                )
                .order_by(SpecItem.id)
            )
        )
        if not spec_items:
            raise ApprovalPrecondition("effective specification contains no items")
        supplier_results = tuple(
            session.scalars(
                select(SupplierResult)
                .where(
                    SupplierResult.inspection_case_id == case.id,
                    SupplierResult.deleted_at.is_(None),
                )
                .order_by(SupplierResult.id)
            )
        )
        internal_results = tuple(
            session.scalars(
                select(InternalResult)
                .where(
                    InternalResult.inspection_case_id == case.id,
                    InternalResult.deleted_at.is_(None),
                )
                .order_by(InternalResult.id)
            )
        )
        inputs: list[ItemInput] = []
        for item in spec_items:
            supplier = next(
                (
                    result
                    for result in supplier_results
                    if result.standard_test_item_id == item.standard_test_item_id
                ),
                None,
            )
            internal = next(
                (result for result in internal_results if result.spec_item_id == item.id),
                None,
            )
            source_policy = self._enum(
                SourcePolicy,
                item.source_policy,
                "source policy",
            )
            mapping_status = (
                self._enum(MappingStatus, supplier.mapping_status, "mapping status")
                if supplier is not None
                else (
                    MappingStatus.ALIAS_MATCHED
                    if source_policy is SourcePolicy.INTERNAL_ONLY
                    else MappingStatus.UNMAPPED
                )
            )
            supplier_values = self._numeric_samples(
                session,
                supplier_result=supplier,
            )
            internal_values = self._numeric_samples(
                session,
                internal_result=internal,
            )
            inputs.append(
                ItemInput(
                    rule=self._rule(item),
                    source_policy=source_policy,
                    missing_policy=self._enum(
                        MissingPolicy,
                        item.missing_policy,
                        "missing policy",
                    ),
                    sample_policy=self._enum(
                        SamplePolicy,
                        item.sample_policy,
                        "sample policy",
                    ),
                    supplier_values=supplier_values,
                    internal_values=internal_values,
                    mapping_status=mapping_status,
                    mapped=(
                        source_policy is SourcePolicy.INTERNAL_ONLY
                        or mapping_status.confirmed
                    ),
                    internal_required=source_policy
                    in {
                        SourcePolicy.INTERNAL_ONLY,
                        SourcePolicy.BOTH_ALL_MUST_PASS,
                        SourcePolicy.SUPPLIER_REFERENCE_INTERNAL_FINAL,
                    },
                    rounding_scale=item.precision,
                    rounding_version=self.ROUNDING_VERSION,
                )
            )
        engine = JudgmentEngine()
        input_tuple = tuple(inputs)
        evaluations = tuple(engine.evaluate_item_details(item) for item in input_tuple)
        return spec_items, supplier_results, internal_results, input_tuple, evaluations

    @staticmethod
    def _rule_payload(item: SpecItem) -> dict[str, Any]:
        return {
            "id": str(item.id),
            "standard_test_item_id": str(item.standard_test_item_id),
            "required": item.required,
            "source_policy": item.source_policy,
            "missing_policy": item.missing_policy,
            "sample_policy": item.sample_policy,
            "operator": item.operator,
            "lower": item.lower_value,
            "upper": item.upper_value,
            "target": item.target_value,
            "tolerance": item.tolerance,
            "allowed": item.allowed_values,
            "unit": item.unit,
            "precision": item.precision,
        }

    def _snapshot(
        self,
        session: Session,
        *,
        case: InspectionCase,
        actor_id: UUID,
        reason: str | None,
        final_decision: str,
        candidate: EngineDecision,
        spec_version: SpecVersion,
        profile: SpecProfile,
        allocation: ReceiptLotAllocation,
        lot: MaterialLot,
        spec_items: tuple[SpecItem, ...],
        supplier_results: tuple[SupplierResult, ...],
        internal_results: tuple[InternalResult, ...],
        evaluations: tuple[ItemEvaluation, ...],
    ) -> DecisionSnapshot:
        document_hashes = tuple(
            session.scalars(
                select(Document.checksum_sha256)
                .join(DocumentSection, DocumentSection.document_id == Document.id)
                .join(
                    DocumentAllocationLink,
                    DocumentAllocationLink.document_section_id == DocumentSection.id,
                )
                .where(
                    DocumentAllocationLink.receipt_lot_allocation_id == allocation.id,
                    Document.deleted_at.is_(None),
                )
                .order_by(Document.checksum_sha256)
            )
        )
        if not document_hashes:
            raise ApprovalPrecondition("approval requires linked immutable document hashes")
        supplier_payload = [
            {
                "id": str(result.id),
                "standard_test_item_id": (
                    str(result.standard_test_item_id)
                    if result.standard_test_item_id is not None
                    else "UNMAPPED"
                ),
                "value": result.normalized_value,
                "text": result.normalized_text or "",
                "mapping_status": result.mapping_status,
                "supplier_decision": result.supplier_decision or "NOT_EVALUATED",
                "hyc_decision": result.hyc_decision or "NOT_EVALUATED",
            }
            for result in supplier_results
        ] or [{"status": "MISSING"}]
        internal_payload = [
            {
                "id": str(result.id),
                "spec_item_id": str(result.spec_item_id),
                "value": result.evaluated_value,
                "text": result.evaluated_text or "",
                "decision": result.decision or "NOT_EVALUATED",
            }
            for result in internal_results
        ] or [{"status": "MISSING"}]
        item_decisions = [
            {
                "spec_item_id": str(item.id),
                "supplier": (
                    evaluation.supplier_decision.value
                    if evaluation.supplier_decision is not None
                    else "NOT_AVAILABLE"
                ),
                "hyc_supplier": (
                    evaluation.hyc_supplier_decision.value
                    if evaluation.hyc_supplier_decision is not None
                    else "NOT_AVAILABLE"
                ),
                "internal": (
                    evaluation.internal_decision.value
                    if evaluation.internal_decision is not None
                    else "NOT_AVAILABLE"
                ),
                "overall": evaluation.overall.value,
                "completed_stages": evaluation.completed_stages,
                "failure_codes": [code.value for code in evaluation.failure_codes]
                or ["NONE"],
                "aggregations": [
                    {
                        "source": aggregation.source,
                        "policy": aggregation.policy.value,
                        "pre_round": aggregation.pre_round,
                        "result": aggregation.result,
                        "rounding_scale": aggregation.rounding_scale,
                        "rounding_version": aggregation.rounding_version,
                        "arithmetic_version": aggregation.arithmetic_version,
                    }
                    for aggregation in evaluation.aggregations
                ],
            }
            for item, evaluation in zip(spec_items, evaluations, strict=True)
        ]
        snapshot = DecisionSnapshot.freeze_for_approval(
            {
                "spec_version": {
                    "id": str(spec_version.id),
                    "profile_id": str(profile.id),
                    "semantic_version": spec_version.version,
                    "status": spec_version.status,
                    "effective_from": spec_version.effective_from,
                    "effective_to": spec_version.effective_to or "OPEN",
                },
                "spec_items": [self._rule_payload(item) for item in spec_items],
                "mapping": [
                    {
                        "supplier_result_id": str(result.id),
                        "status": result.mapping_status,
                        "standard_test_item_id": (
                            str(result.standard_test_item_id)
                            if result.standard_test_item_id is not None
                            else "UNMAPPED"
                        ),
                    }
                    for result in supplier_results
                ]
                or [{"status": "NO_SUPPLIER_MAPPING_INTERNAL_ONLY"}],
                "supplier_results": supplier_payload,
                "internal_results": internal_payload,
                "unit_conversions": {
                    "version": self.CONVERSION_VERSION,
                    "mode": "persisted normalized Decimal values",
                },
                "item_decisions": item_decisions,
                "source_policy": [item.source_policy for item in spec_items],
                "missing_policy": [item.missing_policy for item in spec_items],
                "overall_decision": candidate.value,
                "document_hashes": list(document_hashes),
                "engine_version": self.ENGINE_VERSION,
                "policy_version": self.POLICY_VERSION,
                "rounding_version": self.ROUNDING_VERSION,
                "conversion_version": self.CONVERSION_VERSION,
                "approver": {"actor_id": str(actor_id), "role": "LEAD"},
                "sample_policy": [item.sample_policy for item in spec_items],
                "lot_reference": {
                    "lot_id": str(lot.id),
                    "identity_policy_version": lot.identity_policy_version,
                    "identity_key": lot.identity_key or "PROVISIONAL",
                },
                "allocation_reference": {
                    "allocation_id": str(allocation.id),
                    "model_id": str(allocation.model_id) if allocation.model_id else "COMMON",
                },
                "decision_reasons": {
                    "candidate": candidate.value,
                    "final": final_decision,
                    "reason": reason.strip() if reason and reason.strip() else "ENGINE_MATCH",
                    "hold_precedence": "ON_HOLD_OVER_REJECTED_V1",
                },
            }
        )
        snapshot.verify()
        return snapshot

    def finalize(
        self,
        session: Session,
        *,
        case_id: UUID,
        expected_version: int,
        actor_id: UUID,
        actor_role: str,
        final_decision: str,
        reason: str | None = None,
    ) -> InspectionCase:
        if actor_role != "LEAD":
            raise AuthorizationDenied("only LEAD may approve a quality decision")
        if final_decision not in self.FINAL_DECISIONS:
            raise ApprovalPrecondition("final decision is not an allowed workflow result")
        case = session.get(InspectionCase, case_id, with_for_update=True)
        if case is None or case.deleted_at is not None:
            raise ApprovalPrecondition("inspection case is unavailable")
        if case.lock_version != expected_version:
            raise OptimisticConflict("approval expected version/state does not match")
        if case.final_decision is not None or case.status != "LEAD_REVIEW":
            raise ApprovalPrecondition("inspection case is not awaiting LEAD review")
        if case.submitted_by_id is None:
            raise ApprovalPrecondition("inspection submission actor is not frozen")
        if case.submitted_by_id == actor_id:
            raise AuthorizationDenied("inspector and LEAD approver must be different actors")
        allocation = session.get(ReceiptLotAllocation, case.receipt_lot_allocation_id)
        if allocation is None or allocation.deleted_at is not None:
            raise ApprovalPrecondition("inspection allocation is unavailable")
        receipt = session.get(InboundReceipt, allocation.inbound_receipt_id)
        lot = session.get(MaterialLot, allocation.material_lot_id)
        if receipt is None or receipt.deleted_at is not None or lot is None:
            raise ApprovalPrecondition("inspection receipt or LOT is unavailable")
        if lot.identity_status != "CANONICAL" or lot.merged_into_id is not None:
            raise ApprovalPrecondition("inspection must resolve to a surviving canonical LOT")
        spec_version, profile = self._effective_spec(
            session,
            case=case,
            allocation=allocation,
            receipt=receipt,
            lot=lot,
        )
        (
            spec_items,
            supplier_results,
            internal_results,
            inputs,
            evaluations,
        ) = self._persisted_inputs(
            session,
            case=case,
            spec_version=spec_version,
        )
        candidate = JudgmentEngine().evaluate_case(inputs)
        if final_decision != candidate.value and not (reason and reason.strip()):
            raise ApprovalPrecondition("decision deviation requires a non-empty reason")
        if candidate is not EngineDecision.ACCEPTED and final_decision == "ACCEPTED":
            raise ApprovalPrecondition(
                "non-accepted candidate may only be accepted as SPECIAL_ACCEPTED"
            )
        try:
            guard_transition(
                current=WorkflowState.LEAD_REVIEW,
                target=WorkflowState(final_decision),
                role=actor_role,
                reason=reason,
                re_evaluated=True,
            )
        except (StateTransitionError, ValueError) as error:
            raise ApprovalPrecondition("final workflow transition is not permitted") from error
        snapshot = self._snapshot(
            session,
            case=case,
            actor_id=actor_id,
            reason=reason,
            final_decision=final_decision,
            candidate=candidate,
            spec_version=spec_version,
            profile=profile,
            allocation=allocation,
            lot=lot,
            spec_items=spec_items,
            supplier_results=supplier_results,
            internal_results=internal_results,
            evaluations=evaluations,
        )
        case.candidate_decision = candidate.value
        case.final_decision = final_decision
        case.status = final_decision
        session.add_all(
            (
                DecisionSnapshotRow(
                    inspection_case_id=case.id,
                    payload=snapshot.payload,
                    content_hash=snapshot.content_hash,
                ),
                Approval(
                    inspection_case_id=case.id,
                    action="APPROVE",
                    actor_id=actor_id,
                    actor_role="LEAD",
                ),
                AuditLog(
                    entity_type="inspection_case",
                    entity_id=case.id,
                    action="FINALIZE",
                    payload={
                        "candidate_decision": candidate.value,
                        "final_decision": final_decision,
                        "snapshot_hash": snapshot.content_hash,
                    },
                    reason=reason.strip() if reason and reason.strip() else None,
                ),
                OutboxEvent(
                    topic="inspection.finalized",
                    payload={
                        "inspection_case_id": str(case.id),
                        "snapshot_hash": snapshot.content_hash,
                    },
                ),
            )
        )
        session.flush()
        return case
