from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from hyc_api.auth import Principal
from hyc_api.services.reports import create_report_job, load_report_job
from hyc_domain.reports import ReportKind

pytestmark = pytest.mark.postgres

_LEAD = Principal(UUID("22222222-2222-4222-8222-222222222222"), "LEAD", "p3-lead")


def _approved_case_id(p3) -> UUID:
    flow = p3.reviewed()
    inspection_id = flow["inspection_id"]
    ready = p3.clear_hold(inspection_id)
    submitted = p3.submit(inspection_id, ready["version"])
    approved = p3.approve(inspection_id, submitted["version"])
    assert approved.status_code == 200, approved.text
    return UUID(inspection_id)


def _unapproved_case_id(p3) -> UUID:
    flow = p3.reviewed()
    return UUID(flow["inspection_id"])


def test_successful_run_produces_one_immutable_artifact(p3, p3_engine_storage) -> None:
    case_id = _approved_case_id(p3)
    with p3_engine_storage.session_factory() as session:
        body = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=f"key-1-{uuid4().hex}",
        )
        job = load_report_job(session, body["job_id"])
        assert job.state == "SUCCEEDED"
        assert job.failure_code is None


def test_same_key_and_payload_replays_byte_identically(p3, p3_engine_storage) -> None:
    case_id = _approved_case_id(p3)
    key = f"key-2-{uuid4().hex}"
    with p3_engine_storage.session_factory() as session:
        first = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=key,
        )
    with p3_engine_storage.session_factory() as session:
        second = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=key,
        )
    assert first == second


def test_same_key_with_a_different_payload_conflicts(p3, p3_engine_storage) -> None:
    case_id1 = _approved_case_id(p3)
    case_id2 = _approved_case_id(p3)
    key = f"key-3-{uuid4().hex}"
    with p3_engine_storage.session_factory() as session:
        create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id1)},
            principal=_LEAD,
            idempotency_key=key,
        )
    with p3_engine_storage.session_factory() as session:
        with pytest.raises(HTTPException) as caught:
            create_report_job(
                session,
                kind=ReportKind.INTEGRATED_INSPECTION,
                parameters={"inspection_case_id": str(case_id2)},
                principal=_LEAD,
                idempotency_key=key,
            )
        assert caught.value.status_code == 409


def test_regenerating_the_same_case_creates_a_new_job_not_an_overwrite(
    p3, p3_engine_storage
) -> None:
    case_id = _approved_case_id(p3)
    with p3_engine_storage.session_factory() as session:
        first = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=f"key-4a-{uuid4().hex}",
        )
    with p3_engine_storage.session_factory() as session:
        second = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=f"key-4b-{uuid4().hex}",
        )
    assert first["job_id"] != second["job_id"]


def test_unapproved_case_fails_closed_with_a_failure_code(p3, p3_engine_storage) -> None:
    case_id = _unapproved_case_id(p3)
    with p3_engine_storage.session_factory() as session:
        body = create_report_job(
            session,
            kind=ReportKind.INTEGRATED_INSPECTION,
            parameters={"inspection_case_id": str(case_id)},
            principal=_LEAD,
            idempotency_key=f"key-5-{uuid4().hex}",
        )
        job = load_report_job(session, body["job_id"])
        assert job.state == "FAILED"
        assert job.failure_code == "APPROVAL_SNAPSHOT_MISSING"
