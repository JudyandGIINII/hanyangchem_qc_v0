"""Emit a deterministic, generated-only P4 preflight public report.

The script constructs metadata in memory.  It does not read a source file, environment,
credential, or network and has no execution capability.
"""

from __future__ import annotations

import sys
from datetime import date

# ``uv run --project`` executes this standalone script without adding the project
# source directory.  This is string-only import-path setup, not filesystem access.
sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/src")


def _scope() -> dict[str, object]:
    return {
        "provider": "provider-scope-001",
        "model": "model-scope-001",
        "version": "version-scope-001",
        "endpoint": "endpoint-scope-001",
        "region": "region-scope-001",
    }


def _evidence(index: int, *, attests_dimension: str) -> dict[str, object]:
    from hyc_evaluation.preflight import ProviderScope, evidence_binding_sha256

    reference, digest, verifier = (
        f"generated-evidence-{index:03d}",
        f"{index:064x}",
        f"generated-verifier-{index:03d}",
    )
    verified_on, valid_until = date(2026, 8, 1), date(2026, 8, 3)
    binding = evidence_binding_sha256(
        attests_dimension=attests_dimension,  # type: ignore[arg-type]
        reference=reference,
        evidence_sha256=digest,
        provider_scope=ProviderScope.model_validate(_scope()),
        account_scope_ref="generated-account-001",
        verifier_reference=verifier,
        verified_on=verified_on,
        valid_until=valid_until,
    )
    return {
        "attests_dimension": attests_dimension,
        "reference": reference,
        "evidence_sha256": digest,
        "provider_scope": _scope(),
        "account_scope_ref": "generated-account-001",
        "verifier_reference": verifier,
        "verified_on": verified_on,
        "valid_until": valid_until,
        "evidence_binding_sha256": binding,
        "status": "CONFIRMED",
    }


def _synthetic_document(index: int, *, classification: str) -> dict[str, object]:
    from hyc_evaluation.local_pilot import local_pilot_binding_sha256

    source_sha = f"{1000 + index:064x}"
    label_sha = f"{2000 + index:064x}"
    review_sha = f"{3000 + index:064x}"
    source_id = f"generated-source-{index:03d}"
    return {
        "document_schema_version": "hyc.local-pilot-document.v1",
        "opaque_source_id": source_id,
        "source_sha256": source_sha,
        "classification": classification,
        "document_kind": "SUPPLIER_COA",
        "layout_traits": ["TABULAR"],
        "language_traits": ["KOREAN"],
        "scan_traits": ["SCANNED"],
        "evidence_origin": "GENERATED_SYNTHETIC",
        "label_schema_version": "hyc.local-label.v1",
        "label_authorship": "GENERATED_SYNTHETIC",
        "label_author_ref": f"generated-author-{index:03d}",
        "label_artifact_sha256": label_sha,
        "label_authored_on": date(2026, 8, 1),
        "label_review_state": "GENERATED_SYNTHETIC_UNREVIEWED",
        "independent_reviewer_ref": f"generated-reviewer-{index:03d}",
        "review_artifact_sha256": review_sha,
        "label_reviewed_on": date(2026, 8, 1),
        "evidence_binding_sha256": local_pilot_binding_sha256(
            document_schema_version="hyc.local-pilot-document.v1",
            source_sha256=source_sha,
            label_artifact_sha256=label_sha,
            review_artifact_sha256=review_sha,
            classification=classification,  # type: ignore[arg-type]
            document_kind="SUPPLIER_COA",
            layout_traits=("TABULAR",),
            language_traits=("KOREAN",),
            scan_traits=("SCANNED",),
            label_schema_version="hyc.local-label.v1",
            opaque_source_id=source_id,
            label_author_ref=f"generated-author-{index:03d}",
            independent_reviewer_ref=f"generated-reviewer-{index:03d}",
            label_authored_on=date(2026, 8, 1),
            label_reviewed_on=date(2026, 8, 1),
            evidence_origin="GENERATED_SYNTHETIC",
            label_authorship="GENERATED_SYNTHETIC",
            label_review_state="GENERATED_SYNTHETIC_UNREVIEWED",
            eligibility_status="ELIGIBLE",
            error_categories=(),
        ),
        "eligibility_status": "ELIGIBLE",
        "error_categories": [],
    }


def _complete_policy() -> dict[str, object]:
    return {
        "policy_schema_version": "hyc.provider-preflight-policy.v2",
        "assessment_date": date(2026, 8, 2),
        "external_execution_enabled": False,
        "provider_scope": _scope(),
        "account_scope_ref": "generated-account-001",
        "residency": {
            "data_residency_decision": "APPROVED_IN_REGION",
            "cross_border_transfer_decision": "PROHIBITED",
            "evidence": _evidence(1, attests_dimension="residency"),
        },
        "retention": {
            "retention_days": 30,
            "retention_start_event": "REQUEST_COMPLETED",
            "exceptional_retention": "NOT_PERMITTED",
            "deletion_method": "ATTESTED_DELETION",
            "deletion_sla_days": 7,
            "retention_evidence": _evidence(2, attests_dimension="retention"),
            "deletion_evidence": _evidence(3, attests_dimension="deletion"),
        },
        "training": {
            "training_use": "PROHIBITED",
            "service_improvement_use": "PROHIBITED",
            "opt_out_state": "CONFIRMED",
            "evidence": _evidence(4, attests_dimension="training"),
        },
        "third_party": {
            "subprocessors_reference": "generated-subprocessors-001",
            "subprocessor_evidence": _evidence(5, attests_dimension="subprocessors"),
            "dpa_evidence": _evidence(6, attests_dimension="dpa"),
            "security_evidence": _evidence(7, attests_dimension="security"),
        },
        "credentials": {
            "credential_owner_ref": "generated-credential-owner-001",
            "secret_reference": "generated-secret-ref-001",
            "secret_reference_type": "SECRET_STORE_REFERENCE",
            "rotation_period_days": 30,
            "least_privilege_scopes": ["generated-scope-submit-001"],
            "revocation_reference": "generated-revocation-001",
            "credential_evidence": _evidence(8, attests_dimension="credentials"),
            "value_loaded": False,
        },
        "pricing": {
            "pricing_version": "generated-pricing-001",
            "effective_on": date(2026, 8, 1),
            "currency": "USD",
            "unit_pricing_model": "PER_REQUEST",
            "per_unit_cost": "1.50",
            "hard_budget_cap": "10.00",
            "evidence": _evidence(9, attests_dimension="pricing"),
        },
        "audit": {
            "audit_event_allow_list": ["event_type"],
            "prohibited_log_fields": ["raw_ocr"],
            "raw_response_policy": "NOT_STORED",
            "audit_retention_days": 30,
            "access_policy": "ROLE_LIMITED",
            "deletion_policy": "ATTESTED_DELETION",
            "evidence": _evidence(10, attests_dimension="audit"),
        },
        "incident": {
            "incident_owner_ref": "generated-incident-owner-001",
            "escalation_reference": "generated-escalation-001",
            "containment_control": "KILL_SWITCH",
            "revocation_control": "CREDENTIAL_REVOCATION",
            "evidence": _evidence(11, attests_dimension="incident"),
        },
        "destination": {
            "approved_destination": "generated-destination-001",
            "p4b_packet_id": "generated-p4b-packet-001",
            "pilot_manifest_id": "generated-local-pilot-manifest-001",
            "pilot_manifest_version": "hyc.local-pilot-manifest.v1",
            "intersection_evidence": _evidence(12, attests_dimension="destination_intersection"),
        },
        "payload_policy": {
            "redaction_method": "FIELD_ALLOWLIST_REDACTION",
            "redaction_version": "generated-redaction-v1",
            "redaction_evidence": _evidence(13, attests_dimension="payload_redaction"),
            "allow_list": ["document_kind", "synthetic_case_id"],
            "forbidden_fields": ["raw_ocr"],
            "max_request_bytes": 1024,
            "max_batch_size": 2,
            "max_rate_per_minute": 4,
            "max_concurrency": 1,
        },
        "provider_approval": {
            "approved_scope": _scope(),
            "approver_reference": "generated-approver-001",
            "approval_date": date(2026, 8, 2),
            "approval_evidence": _evidence(14, attests_dimension="provider_approval"),
            "final_status": "APPROVED",
        },
    }


def main() -> int:
    from hyc_evaluation.artifacts import canonical_json_bytes, canonical_sha256
    from hyc_evaluation.local_pilot import (
        LocalPilotManifest,
        assess_local_pilot_manifest,
        build_public_pilot_aggregate,
    )
    from hyc_evaluation.preflight import (
        ProviderPreflightPolicy,
        PublicPreflightReport,
        SyntheticDryRunDescriptor,
        evaluate_provider_preflight,
    )

    manifest_base = {
        "manifest_schema_version": "hyc.local-pilot-manifest.v1",
        "manifest_id": "generated-local-pilot-manifest-001",
        "representativeness_status": "NON_REPRESENTATIVE",
        "release_gate_eligible": False,
        "transmission_authorized": False,
        "ap02_approval_status": "NOT_APPROVED",
    }
    empty = LocalPilotManifest.model_validate({**manifest_base, "documents": []})
    manifest = LocalPilotManifest.model_validate(
        {
            **manifest_base,
            "documents": [
                _synthetic_document(
                    i, classification="CONFIDENTIAL" if i <= 3 else "INTERNAL_RESTRICTED"
                )
                for i in range(1, 5)
            ],
        }
    )
    small_manifest = LocalPilotManifest.model_validate(
        {
            **manifest_base,
            "documents": [
                _synthetic_document(i, classification="CONFIDENTIAL") for i in range(1, 3)
            ],
        }
    )
    aggregate = build_public_pilot_aggregate(manifest)
    small_aggregate = build_public_pilot_aggregate(small_manifest)
    request = SyntheticDryRunDescriptor.model_validate(
        {
            "descriptor_schema_version": "hyc.synthetic-dry-run-descriptor.v2",
            "scope": _scope(),
            "account_scope_ref": "generated-account-001",
            "approved_destination": "generated-destination-001",
            "p4b_packet_id": "generated-p4b-packet-001",
            "pilot_manifest_id": "generated-local-pilot-manifest-001",
            "pilot_manifest_version": "hyc.local-pilot-manifest.v1",
            "payload_fields": ["document_kind", "synthetic_case_id"],
            "request_payload_bytes": 512,
            "batch_size": 2,
            "requested_rate_per_minute": 4,
            "requested_concurrency": 1,
            "billable_unit_count": 2,
            "currency": "USD",
            "unit_pricing_model": "PER_REQUEST",
            "per_unit_cost": "1.50",
            "caller_projected_total": "3.00",
            "provenance_marker": "generated-non-sensitive-synthetic",
        }
    )
    default_decision = evaluate_provider_preflight(ProviderPreflightPolicy(), request)
    complete_decision = evaluate_provider_preflight(
        ProviderPreflightPolicy.model_validate(_complete_policy()), request
    )
    classification = next(
        item for item in aggregate.dimensions if item.dimension == "CLASSIFICATION"
    )
    small_cohort_suppression_verified = (
        small_aggregate.cohort_size_bucket == "LT_3"
        and small_aggregate.small_cohort_suppressed
        and all(
            not dimension.visible_cells and dimension.suppression_applied
            for dimension in small_aggregate.dimensions
        )
    )
    if (
        assess_local_pilot_manifest(empty).status != "INSUFFICIENT_ELIGIBLE_CORPUS"
        or not classification.suppression_applied
        or not small_cohort_suppression_verified
        or default_decision.status != "DENY"
        or complete_decision.status != "STRUCTURALLY_EVIDENTIAL_COMPLETE_AWAITING_EXTERNAL_EXECUTOR"
    ):
        raise RuntimeError("generated preflight invariant failed")
    report = PublicPreflightReport.model_validate(
        {
            "check_schema_version": "hyc.synthetic-p4-preflight-check.v2",
            "markers": (
                "GENERATED_SYNTHETIC_EVIDENCE",
                "HUMAN_REVIEW_REQUIRED",
                "NON_REPRESENTATIVE",
                "NOT_A_RELEASE_GATE",
            ),
            "local_pilot": {
                "aggregate_sha256": canonical_sha256(aggregate),
                "cohort_size_bucket": aggregate.cohort_size_bucket,
                "empty_status": assess_local_pilot_manifest(empty).status,
                "small_cohort_suppression_verified": small_cohort_suppression_verified,
            },
            "ap02": {
                "complete_status": complete_decision.status,
                "default_deny_reason_count": len(default_decision.reason_codes),
                "default_status": default_decision.status,
                "execution_effect": complete_decision.authorization_effect,
                "side_effects": complete_decision.side_effects,
            },
        }
    )
    sys.stdout.buffer.write(canonical_json_bytes(report) + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
