from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from hyc_evaluation.artifacts import canonical_json_bytes, canonical_sha256
from hyc_evaluation.local_pilot import (
    LocalPilotDocument,
    LocalPilotManifest,
    PublicPilotAggregate,
    assess_local_pilot_manifest,
    build_public_pilot_aggregate,
    local_pilot_binding_sha256,
)


def document_payload(
    *, index: int = 1, eligibility: str = "ELIGIBLE", generated: bool = False
) -> dict[str, object]:
    source_id, source_sha = f"local-source-{index:03d}", f"{index:064x}"
    label_sha, review_sha = f"{1000 + index:064x}", f"{2000 + index:064x}"
    return {
        "document_schema_version": "hyc.local-pilot-document.v1",
        "opaque_source_id": source_id,
        "source_sha256": source_sha,
        "classification": "CONFIDENTIAL",
        "document_kind": "SUPPLIER_COA",
        "layout_traits": ["TABULAR"],
        "language_traits": ["KOREAN"],
        "scan_traits": ["SCANNED"],
        "evidence_origin": "GENERATED_SYNTHETIC" if generated else "LOCAL_HUMAN",
        "label_schema_version": "hyc.local-label.v1",
        "label_authorship": "GENERATED_SYNTHETIC" if generated else "HUMAN_AUTHORED",
        "label_author_ref": f"label-author-{index:03d}",
        "label_artifact_sha256": label_sha,
        "label_authored_on": date(2026, 8, 1),
        "label_review_state": "GENERATED_SYNTHETIC_UNREVIEWED" if generated else "HUMAN_REVIEWED",
        "independent_reviewer_ref": f"independent-reviewer-{index:03d}",
        "review_artifact_sha256": review_sha,
        "label_reviewed_on": date(2026, 8, 2),
        "evidence_binding_sha256": local_pilot_binding_sha256(
            document_schema_version="hyc.local-pilot-document.v1",
            source_sha256=source_sha,
            label_artifact_sha256=label_sha,
            review_artifact_sha256=review_sha,
            classification="CONFIDENTIAL",
            document_kind="SUPPLIER_COA",
            layout_traits=("TABULAR",),
            language_traits=("KOREAN",),
            scan_traits=("SCANNED",),
            label_schema_version="hyc.local-label.v1",
            opaque_source_id=source_id,
            label_author_ref=f"label-author-{index:03d}",
            independent_reviewer_ref=f"independent-reviewer-{index:03d}",
            label_authored_on=date(2026, 8, 1),
            label_reviewed_on=date(2026, 8, 2),
            evidence_origin="GENERATED_SYNTHETIC" if generated else "LOCAL_HUMAN",
            label_authorship="GENERATED_SYNTHETIC" if generated else "HUMAN_AUTHORED",
            label_review_state=(
                "GENERATED_SYNTHETIC_UNREVIEWED" if generated else "HUMAN_REVIEWED"
            ),
            eligibility_status=eligibility,  # type: ignore[arg-type]
            error_categories=() if eligibility == "ELIGIBLE" else ("LABEL_CONTRACT_ERROR",),
        ),
        "eligibility_status": eligibility,
        "error_categories": [] if eligibility == "ELIGIBLE" else ["LABEL_CONTRACT_ERROR"],
    }


def manifest_payload(documents: list[dict[str, object]]) -> dict[str, object]:
    return {
        "manifest_schema_version": "hyc.local-pilot-manifest.v1",
        "manifest_id": "local-pilot-manifest-001",
        "representativeness_status": "NON_REPRESENTATIVE",
        "release_gate_eligible": False,
        "transmission_authorized": False,
        "ap02_approval_status": "NOT_APPROVED",
        "documents": documents,
    }


def manifest(documents: list[dict[str, object]]) -> LocalPilotManifest:
    return LocalPilotManifest.model_validate(manifest_payload(documents))


def test_binding_algorithm_is_exact_and_human_manifest_is_only_structurally_ready() -> None:
    item = document_payload()
    assert (
        item["evidence_binding_sha256"]
        == "7d1f2139d3aebf87380b8ae86d806dcc6c59fc010efabdbcb415e6cf946c6689"
    )
    assessment = assess_local_pilot_manifest(manifest([item]))
    assert assessment.status == "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY"
    assert assessment.release_gate_eligible is False
    assert assessment.transmission_authorized is False
    assert assessment.human_review_required is True


@pytest.mark.parametrize(
    "field",
    [
        "source_sha256",
        "document_schema_version",
        "classification",
        "document_kind",
        "layout_traits",
        "language_traits",
        "scan_traits",
        "label_artifact_sha256",
        "review_artifact_sha256",
        "label_schema_version",
        "opaque_source_id",
        "label_author_ref",
        "independent_reviewer_ref",
        "label_authored_on",
        "label_reviewed_on",
        "evidence_origin",
        "label_authorship",
        "label_review_state",
        "eligibility_status",
        "error_categories",
    ],
)
def test_tampered_or_foreign_binding_fails_closed(field: str) -> None:
    payload = document_payload()
    if field.endswith("sha256"):
        payload[field] = "f" * 64
    elif field == "label_schema_version":
        payload[field] = "hyc.local-label.v2"
    elif field == "document_schema_version":
        payload[field] = "hyc.local-pilot-document.v2"
    elif field == "classification":
        payload[field] = "INTERNAL_RESTRICTED"
    elif field == "document_kind":
        payload[field] = "SUPPLIER_INSPECTION_REPORT"
    elif field == "layout_traits":
        payload[field] = ["FORM"]
    elif field == "language_traits":
        payload[field] = ["ENGLISH"]
    elif field == "scan_traits":
        payload[field] = ["DIGITAL_TEXT"]
    elif field == "eligibility_status":
        payload[field] = "INELIGIBLE"
    elif field == "error_categories":
        payload[field] = ["LABEL_CONTRACT_ERROR"]
    elif field == "label_authored_on":
        payload[field] = date(2026, 8, 2)
    elif field == "label_reviewed_on":
        payload[field] = date(2026, 8, 3)
    elif field in {"evidence_origin", "label_authorship", "label_review_state"}:
        payload.update(
            {
                "evidence_origin": "GENERATED_SYNTHETIC",
                "label_authorship": "GENERATED_SYNTHETIC",
                "label_review_state": "GENERATED_SYNTHETIC_UNREVIEWED",
            }
        )
    else:
        payload[field] = "foreign-reference-001"
    match = None if field == "document_schema_version" else "binding"
    with pytest.raises(ValidationError, match=match):
        LocalPilotDocument.model_validate(payload)


def test_swapped_label_or_review_binding_and_duplicate_manifest_evidence_fail_closed() -> None:
    left, right = document_payload(index=1), document_payload(index=2)
    left["label_artifact_sha256"] = right["label_artifact_sha256"]
    with pytest.raises(ValidationError, match="binding"):
        LocalPilotDocument.model_validate(left)
    duplicate = document_payload(index=2)
    duplicate["label_artifact_sha256"] = document_payload(index=1)["label_artifact_sha256"]
    duplicate["evidence_binding_sha256"] = local_pilot_binding_sha256(
        source_sha256=duplicate["source_sha256"],
        label_artifact_sha256=duplicate["label_artifact_sha256"],
        review_artifact_sha256=duplicate["review_artifact_sha256"],
        label_schema_version=duplicate["label_schema_version"],
        opaque_source_id=duplicate["opaque_source_id"],
        label_author_ref=duplicate["label_author_ref"],
        independent_reviewer_ref=duplicate["independent_reviewer_ref"],
        label_authored_on=duplicate["label_authored_on"],
        label_reviewed_on=duplicate["label_reviewed_on"],
        evidence_origin=duplicate["evidence_origin"],
        label_authorship=duplicate["label_authorship"],
        label_review_state=duplicate["label_review_state"],
        document_schema_version=duplicate["document_schema_version"],
        classification=duplicate["classification"],
        document_kind=duplicate["document_kind"],
        layout_traits=tuple(duplicate["layout_traits"]),
        language_traits=tuple(duplicate["language_traits"]),
        scan_traits=tuple(duplicate["scan_traits"]),
        eligibility_status=duplicate["eligibility_status"],
        error_categories=tuple(duplicate["error_categories"]),
    )  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="unique"):
        manifest([document_payload(index=1), duplicate])


def test_duplicate_evidence_binding_is_rejected_as_manifest_defense_in_depth() -> None:
    left, right = document_payload(index=1), document_payload(index=2)
    forged_right = LocalPilotDocument.model_construct(
        **{
            **LocalPilotDocument.model_validate(right).model_dump(),
            "evidence_binding_sha256": left["evidence_binding_sha256"],
        }
    )
    forged_manifest = LocalPilotManifest.model_construct(
        manifest_schema_version="hyc.local-pilot-manifest.v1",
        manifest_id="local-pilot-manifest-001",
        representativeness_status="NON_REPRESENTATIVE",
        release_gate_eligible=False,
        transmission_authorized=False,
        ap02_approval_status="NOT_APPROVED",
        documents=(LocalPilotDocument.model_validate(left), forged_right),
    )
    with pytest.raises(ValueError, match="unique"):
        forged_manifest.require_unique_evidence_references()


@pytest.mark.parametrize(
    "field",
    ["label_artifact_sha256", "review_artifact_sha256", "label_authored_on", "label_reviewed_on"],
)
def test_missing_human_evidence_fields_fail_closed(field: str) -> None:
    payload = document_payload()
    payload[field] = None
    with pytest.raises(ValidationError):
        LocalPilotDocument.model_validate(payload)


def test_same_author_reviewer_and_backdated_review_fail_closed() -> None:
    payload = document_payload()
    payload["independent_reviewer_ref"] = payload["label_author_ref"]
    with pytest.raises(ValidationError, match="distinct"):
        LocalPilotDocument.model_validate(payload)
    payload = document_payload()
    payload["label_reviewed_on"] = date(2026, 7, 31)
    with pytest.raises(ValidationError, match="precede"):
        LocalPilotDocument.model_validate(payload)


def test_label_and_review_artifacts_are_distinct_with_global_cross_collision_defense() -> None:
    payload = document_payload()
    payload["review_artifact_sha256"] = payload["label_artifact_sha256"]
    payload["evidence_binding_sha256"] = local_pilot_binding_sha256(
        document_schema_version=payload["document_schema_version"],
        source_sha256=payload["source_sha256"],
        label_artifact_sha256=payload["label_artifact_sha256"],
        review_artifact_sha256=payload["review_artifact_sha256"],
        classification=payload["classification"],
        document_kind=payload["document_kind"],
        layout_traits=tuple(payload["layout_traits"]),
        language_traits=tuple(payload["language_traits"]),
        scan_traits=tuple(payload["scan_traits"]),
        label_schema_version=payload["label_schema_version"],
        opaque_source_id=payload["opaque_source_id"],
        label_author_ref=payload["label_author_ref"],
        independent_reviewer_ref=payload["independent_reviewer_ref"],
        label_authored_on=payload["label_authored_on"],
        label_reviewed_on=payload["label_reviewed_on"],
        evidence_origin=payload["evidence_origin"],
        label_authorship=payload["label_authorship"],
        label_review_state=payload["label_review_state"],
        eligibility_status=payload["eligibility_status"],
        error_categories=tuple(payload["error_categories"]),
    )  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="distinct"):
        LocalPilotDocument.model_validate(payload)

    left, right = document_payload(index=1), document_payload(index=2)
    right["review_artifact_sha256"] = left["label_artifact_sha256"]
    right["evidence_binding_sha256"] = local_pilot_binding_sha256(
        document_schema_version=right["document_schema_version"],
        source_sha256=right["source_sha256"],
        label_artifact_sha256=right["label_artifact_sha256"],
        review_artifact_sha256=right["review_artifact_sha256"],
        classification=right["classification"],
        document_kind=right["document_kind"],
        layout_traits=tuple(right["layout_traits"]),
        language_traits=tuple(right["language_traits"]),
        scan_traits=tuple(right["scan_traits"]),
        label_schema_version=right["label_schema_version"],
        opaque_source_id=right["opaque_source_id"],
        label_author_ref=right["label_author_ref"],
        independent_reviewer_ref=right["independent_reviewer_ref"],
        label_authored_on=right["label_authored_on"],
        label_reviewed_on=right["label_reviewed_on"],
        evidence_origin=right["evidence_origin"],
        label_authorship=right["label_authorship"],
        label_review_state=right["label_review_state"],
        eligibility_status=right["eligibility_status"],
        error_categories=tuple(right["error_categories"]),
    )  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="globally unique"):
        manifest([left, right])


def test_author_and_reviewer_may_be_reused_across_documents() -> None:
    left, right = document_payload(index=1), document_payload(index=2)
    right["label_author_ref"] = left["label_author_ref"]
    right["independent_reviewer_ref"] = left["independent_reviewer_ref"]
    right["evidence_binding_sha256"] = local_pilot_binding_sha256(
        document_schema_version=right["document_schema_version"],
        source_sha256=right["source_sha256"],
        label_artifact_sha256=right["label_artifact_sha256"],
        review_artifact_sha256=right["review_artifact_sha256"],
        classification=right["classification"],
        document_kind=right["document_kind"],
        layout_traits=tuple(right["layout_traits"]),
        language_traits=tuple(right["language_traits"]),
        scan_traits=tuple(right["scan_traits"]),
        label_schema_version=right["label_schema_version"],
        opaque_source_id=right["opaque_source_id"],
        label_author_ref=right["label_author_ref"],
        independent_reviewer_ref=right["independent_reviewer_ref"],
        label_authored_on=right["label_authored_on"],
        label_reviewed_on=right["label_reviewed_on"],
        evidence_origin=right["evidence_origin"],
        label_authorship=right["label_authorship"],
        label_review_state=right["label_review_state"],
        eligibility_status=right["eligibility_status"],
        error_categories=tuple(right["error_categories"]),
    )  # type: ignore[arg-type]
    assert len(manifest([left, right]).documents) == 2


def test_generated_or_unreviewed_declarations_never_claim_human_evidence() -> None:
    generated = manifest([document_payload(generated=True)])
    assert assess_local_pilot_manifest(generated).status == "HUMAN_EVIDENCE_REQUIRED"
    contradictory = document_payload(generated=True)
    contradictory["label_review_state"] = "HUMAN_REVIEWED"
    with pytest.raises(ValidationError, match="generated evidence"):
        LocalPilotDocument.model_validate(contradictory)
    unreviewed = document_payload()
    unreviewed["label_review_state"] = "GENERATED_SYNTHETIC_UNREVIEWED"
    with pytest.raises(ValidationError, match="local human evidence"):
        LocalPilotDocument.model_validate(unreviewed)


def test_zero_eligible_documents_fails_closed() -> None:
    assert (
        assess_local_pilot_manifest(manifest([document_payload(eligibility="INELIGIBLE")])).status
        == "INSUFFICIENT_ELIGIBLE_CORPUS"
    )


@pytest.mark.parametrize("count", [1, 2])
def test_small_cohorts_never_emit_exact_counts_or_document_records(count: int) -> None:
    aggregate = build_public_pilot_aggregate(
        manifest([document_payload(index=i) for i in range(1, count + 1)])
    )
    dumped = aggregate.model_dump(mode="json")
    assert aggregate.status == "NON_REPRESENTATIVE_MANIFEST_STRUCTURALLY_READY"
    assert aggregate.cohort_size_bucket == "LT_3"
    assert aggregate.small_cohort_suppressed is True
    assert all(
        not dimension.visible_cells and dimension.suppression_applied
        for dimension in aggregate.dimensions
    )
    assert {
        "total_document_count",
        "eligible_document_count",
        "ineligible_document_count",
        "suppressed_cell_count",
        "suppressed_document_count",
    }.isdisjoint(dumped)
    assert "documents" not in PublicPilotAggregate.model_fields


def test_dimension_level_suppression_never_reveals_a_subthreshold_complement() -> None:
    documents = [document_payload(index=i) for i in range(1, 8)]
    for item in documents[5:]:
        item["eligibility_status"] = "INELIGIBLE"
        item["error_categories"] = ["LABEL_CONTRACT_ERROR"]
    for item in documents[4:]:
        item["document_kind"] = "SUPPLIER_INSPECTION_REPORT"
    # Rebind all changed documents; their aggregate-driving fields are in the digest.
    for item in documents:
        item["evidence_binding_sha256"] = local_pilot_binding_sha256(
            document_schema_version=item["document_schema_version"],
            source_sha256=item["source_sha256"],
            label_artifact_sha256=item["label_artifact_sha256"],
            review_artifact_sha256=item["review_artifact_sha256"],
            classification=item["classification"],
            document_kind=item["document_kind"],
            layout_traits=tuple(item["layout_traits"]),
            language_traits=tuple(item["language_traits"]),
            scan_traits=tuple(item["scan_traits"]),
            label_schema_version=item["label_schema_version"],
            opaque_source_id=item["opaque_source_id"],
            label_author_ref=item["label_author_ref"],
            independent_reviewer_ref=item["independent_reviewer_ref"],
            label_authored_on=item["label_authored_on"],
            label_reviewed_on=item["label_reviewed_on"],
            evidence_origin=item["evidence_origin"],
            label_authorship=item["label_authorship"],
            label_review_state=item["label_review_state"],
            eligibility_status=item["eligibility_status"],
            error_categories=tuple(item["error_categories"]),
        )  # type: ignore[arg-type]
    aggregate = build_public_pilot_aggregate(manifest(documents))
    by_name = {item.dimension: item for item in aggregate.dimensions}
    assert aggregate.cohort_size_bucket == "3_TO_9"
    assert by_name["CLASSIFICATION"].visible_cells[0].count == 7
    assert not by_name["ELIGIBILITY_STATUS"].visible_cells
    assert by_name["ELIGIBILITY_STATUS"].suppression_applied is True
    assert tuple(cell.count for cell in by_name["DOCUMENT_KIND"].visible_cells) == (4, 3)
    assert by_name["DOCUMENT_KIND"].suppression_applied is False


def test_ninety_nine_plus_one_and_every_dimension_use_only_boolean_suppression() -> None:
    documents = [document_payload(index=i) for i in range(1, 101)]
    documents[-1]["classification"] = "INTERNAL_RESTRICTED"
    item = documents[-1]
    item["evidence_binding_sha256"] = local_pilot_binding_sha256(
        document_schema_version=item["document_schema_version"],
        source_sha256=item["source_sha256"],
        label_artifact_sha256=item["label_artifact_sha256"],
        review_artifact_sha256=item["review_artifact_sha256"],
        classification=item["classification"],
        document_kind=item["document_kind"],
        layout_traits=tuple(item["layout_traits"]),
        language_traits=tuple(item["language_traits"]),
        scan_traits=tuple(item["scan_traits"]),
        label_schema_version=item["label_schema_version"],
        opaque_source_id=item["opaque_source_id"],
        label_author_ref=item["label_author_ref"],
        independent_reviewer_ref=item["independent_reviewer_ref"],
        label_authored_on=item["label_authored_on"],
        label_reviewed_on=item["label_reviewed_on"],
        evidence_origin=item["evidence_origin"],
        label_authorship=item["label_authorship"],
        label_review_state=item["label_review_state"],
        eligibility_status=item["eligibility_status"],
        error_categories=tuple(item["error_categories"]),
    )  # type: ignore[arg-type]
    aggregate = build_public_pilot_aggregate(manifest(documents))
    classification = next(
        item for item in aggregate.dimensions if item.dimension == "CLASSIFICATION"
    )
    assert aggregate.cohort_size_bucket == "10_PLUS"
    assert not classification.visible_cells
    assert classification.suppression_applied is True
    assert all(
        set(item.model_dump()) == {"dimension", "visible_cells", "suppression_applied"}
        for item in aggregate.dimensions
    )


def test_public_aggregate_rejects_leaks_and_is_deterministic() -> None:
    first = build_public_pilot_aggregate(manifest([document_payload(index=i) for i in range(1, 4)]))
    payload = first.model_dump(mode="json")
    payload["dimensions"][0]["visible_cells"] = [{"category": "/private/source.pdf", "count": 3}]
    with pytest.raises(ValidationError):
        PublicPilotAggregate.model_validate(payload)
    payload = first.model_dump(mode="json")
    payload["dimensions"][0]["visible_cells"] = [{"category": "SUPPLIER_COA", "count": 3}]
    with pytest.raises(ValidationError, match="does not match"):
        PublicPilotAggregate.model_validate(payload)
    foreign_categories = (
        "SUPPLIER_COA",
        "CONFIDENTIAL",
        "SUPPLIER_COA",
        "CONFIDENTIAL",
        "CONFIDENTIAL",
        "CONFIDENTIAL",
        "CONFIDENTIAL",
    )
    for index, category in enumerate(foreign_categories):
        payload = first.model_dump(mode="json")
        payload["dimensions"][index].update(
            visible_cells=[{"category": category, "count": 3}], suppression_applied=False
        )
        with pytest.raises(ValidationError, match="does not match"):
            PublicPilotAggregate.model_validate(payload)
    payload = first.model_dump(mode="json")
    payload["dimensions"][0]["suppression_applied"] = True
    with pytest.raises(ValidationError, match="cannot expose"):
        PublicPilotAggregate.model_validate(payload)
    second = build_public_pilot_aggregate(
        manifest(list(reversed([document_payload(index=i) for i in range(1, 4)])))
    )
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert canonical_sha256(first) == canonical_sha256(second)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_empty_and_zero_eligible_small_cohorts_preserve_failure_status(count: int) -> None:
    aggregate = build_public_pilot_aggregate(
        manifest([document_payload(index=i, eligibility="INELIGIBLE") for i in range(1, count + 1)])
    )
    assert aggregate.status == "INSUFFICIENT_ELIGIBLE_CORPUS"
    assert aggregate.small_cohort_suppressed is True
    assert all(not dimension.visible_cells for dimension in aggregate.dimensions)


def test_public_disclosure_threshold_is_fixed() -> None:
    with pytest.raises(ValueError, match="fixed"):
        build_public_pilot_aggregate(manifest([document_payload()]), disclosure_threshold=4)
