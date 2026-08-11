from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from hyc_data.models import AuditLog, ReportJob

pytestmark = pytest.mark.postgres


def _approved_case_id(p3) -> UUID:
    flow = p3.reviewed(suffix=f"report-api-{uuid4().hex}")
    inspection_id = str(flow["inspection_id"])
    ready = p3.clear_hold(inspection_id)
    submitted = p3.submit(inspection_id, int(ready["version"]))
    approved = p3.approve(inspection_id, int(submitted["version"]))
    assert approved.status_code == 200, approved.text
    return UUID(inspection_id)


def _create_report(p3, case_id: UUID) -> dict[str, object]:
    response = p3.client.post(
        "/api/v1/reports",
        headers=p3.inspector | {"Idempotency-Key": f"report-api-{uuid4().hex}"},
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(case_id)},
        },
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_create_returns_202_with_a_job_id_and_get_returns_its_state(p3) -> None:
    created = _create_report(p3, _approved_case_id(p3))
    assert created["job_id"]
    status_response = p3.client.get(
        f"/api/v1/reports/{created['job_id']}", headers=p3.inspector
    )
    assert status_response.status_code == 200, status_response.text
    assert status_response.json()["job_id"] == created["job_id"]
    assert status_response.json()["state"] == "SUCCEEDED"
    assert status_response.json()["artifact_digest"]


def test_missing_idempotency_key_is_422(p3) -> None:
    response = p3.client.post(
        "/api/v1/reports",
        headers=p3.inspector,
        json={
            "kind": "INTEGRATED_INSPECTION",
            "parameters": {"inspection_case_id": str(_approved_case_id(p3))},
        },
    )
    assert response.status_code == 422


def test_download_before_completion_is_409(p3, p3_engine_storage) -> None:
    case_id = _approved_case_id(p3)
    job = ReportJob(
        kind="INTEGRATED_INSPECTION",
        parameters={"inspection_case_id": str(case_id)},
        state="QUEUED",
        requested_by_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_role="INSPECTOR",
    )
    with p3_engine_storage.session_factory() as session:
        session.add(job)
        session.commit()
        job_id = job.id
    response = p3.client.get(f"/api/v1/reports/{job_id}/download", headers=p3.inspector)
    assert response.status_code == 409


def test_download_streams_the_artifact_and_writes_one_audit_row(p3, p3_engine_storage) -> None:
    created = _create_report(p3, _approved_case_id(p3))
    with p3_engine_storage.session_factory() as session:
        before = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "REPORT_DOWNLOADED")
        )
    response = p3.client.get(
        f"/api/v1/reports/{created['job_id']}/download", headers=p3.inspector
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.content[:2] == b"PK"
    with p3_engine_storage.session_factory() as session:
        after = session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "REPORT_DOWNLOADED")
        )
    assert after == before + 1


def test_unknown_job_is_404(p3) -> None:
    response = p3.client.get(
        "/api/v1/reports/00000000-0000-4000-8000-000000000000", headers=p3.inspector
    )
    assert response.status_code == 404


def test_inspector_may_generate_and_download(p3) -> None:
    created = _create_report(p3, _approved_case_id(p3))
    response = p3.client.get(
        f"/api/v1/reports/{created['job_id']}/download", headers=p3.inspector
    )
    assert response.status_code == 200, response.text
