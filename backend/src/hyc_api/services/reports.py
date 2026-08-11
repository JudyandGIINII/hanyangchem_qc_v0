from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from hyc_api.auth import Principal
from hyc_api.config import Settings
from hyc_api.reports.integrated import render_integrated_inspection_report
from hyc_api.reports.raw_data import render_raw_data_report
from hyc_api.reports.sources import (
    ReportSourceUnavailable,
    load_frozen_decision,
    load_reference_information,
)
from hyc_api.reports.statistics import (
    build_statistics_rows,
    period_bounds_utc,
    render_supplier_quality_statistics_report,
)
from hyc_api.services.p3 import complete_idempotency, reserve_idempotency
from hyc_api.storage import HashAddressedStorage, StoredObject
from hyc_data.models import ReportArtifact, ReportJob
from hyc_domain.reports import ReportKind, canonical_report_parameters


def _store_bytes_sync(storage: HashAddressedStorage, payload: bytes) -> StoredObject:
    async def _async_store() -> StoredObject:
        async def _chunks() -> AsyncGenerator[bytes, None]:
            yield payload

        return await storage.put_stream(_chunks())

    try:
        return asyncio.run(_async_store())
    except RuntimeError:
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(_async_store())).result()


class ReportRunner(Protocol):
    def run(self, session: Session, job: ReportJob) -> ReportArtifact: ...


class InProcessReportRunner:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def run(self, session: Session, job: ReportJob) -> ReportArtifact:
        include_audit = bool(job.parameters.get("include_audit", False))
        try:
            kind = ReportKind(job.kind)
        except ValueError as error:
            raise ReportSourceUnavailable("UNSUPPORTED_REPORT_KIND") from error

        if kind is ReportKind.SUPPLIER_QUALITY_STATISTICS:
            workbook_bytes = self._render_statistics(session, job)
        elif kind in (ReportKind.INTEGRATED_INSPECTION, ReportKind.RAW_DATA):
            workbook_bytes = self._render_case_report(
                session, job, kind=kind, include_audit=include_audit
            )
        else:
            # LOT_TRACE is registered but not yet runnable: its generator reads a
            # frozen.payload["allocations"] key that the approval snapshot does not
            # carry, so its split-receipt sheet could only ever render empty.
            raise ReportSourceUnavailable("REPORT_KIND_NOT_IMPLEMENTED")

        storage = HashAddressedStorage(self._settings.p6_report_storage_root)
        stored = _store_bytes_sync(storage, workbook_bytes)

        artifact = ReportArtifact(
            report_job_id=job.id,
            content_digest=stored.digest,
            storage_key=stored.storage_key,
            byte_size=stored.size_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        session.add(artifact)
        session.flush()
        return artifact

    def _render_case_report(
        self, session: Session, job: ReportJob, *, kind: ReportKind, include_audit: bool
    ) -> bytes:
        raw_case_id = job.parameters.get("inspection_case_id")
        if not raw_case_id:
            raise ReportSourceUnavailable("INVALID_PARAMETERS")
        case_id = UUID(str(raw_case_id))
        frozen = load_frozen_decision(session, case_id)
        reference = load_reference_information(session, case_id)
        if kind is ReportKind.RAW_DATA:
            return render_raw_data_report(frozen, reference, include_audit=include_audit)
        return render_integrated_inspection_report(frozen, reference, include_audit=include_audit)

    def _render_statistics(self, session: Session, job: ReportJob) -> bytes:
        period_start = str(job.parameters.get("period_start", ""))
        period_end = str(job.parameters.get("period_end", ""))
        if not period_start or not period_end:
            raise ReportSourceUnavailable("INVALID_PARAMETERS")
        start_utc, end_utc = period_bounds_utc(period_start, period_end)
        rows = build_statistics_rows(session, start_utc, end_utc)
        return render_supplier_quality_statistics_report(
            rows, period_start, period_end, datetime.now(UTC)
        )


def create_report_job(
    session: Session,
    *,
    kind: ReportKind,
    parameters: Mapping[str, Any],
    principal: Principal,
    idempotency_key: str,
    runner: ReportRunner | None = None,
) -> dict[str, Any]:
    canonical = canonical_report_parameters(kind, parameters)
    payload = {"kind": kind.value, "parameters": canonical}

    record, replay = reserve_idempotency(
        session,
        principal=principal,
        scope="p6.reports",
        key=idempotency_key,
        payload=payload,
    )
    if replay is not None:
        return replay

    job = ReportJob(
        kind=kind.value,
        parameters=canonical,
        state="QUEUED",
        requested_by_id=principal.actor_id,
        actor_role=principal.role,
    )
    session.add(job)
    session.flush()

    active_runner = runner or InProcessReportRunner()
    body = _execute(session, job_id=job.id, runner=active_runner)

    complete_idempotency(
        record, status=202, body=body, resource_ref=f"report_jobs/{job.id}"
    )
    session.commit()
    return body


def _execute(session: Session, *, job_id: UUID, runner: ReportRunner) -> dict[str, Any]:
    job = session.scalar(
        select(ReportJob).where(ReportJob.id == job_id).with_for_update()
    )
    if job is None:
        raise RuntimeError("report job not found")

    job.state = "RUNNING"
    job.started_at = datetime.now(UTC)
    session.flush()

    try:
        runner.run(session, job)
        job.state = "SUCCEEDED"
        job.finished_at = datetime.now(UTC)
        session.flush()
    except ReportSourceUnavailable as error:
        job.state = "FAILED"
        job.failure_code = error.code
        job.finished_at = datetime.now(UTC)
        session.flush()

    return {
        "job_id": str(job.id),
        "state": job.state,
        "failure_code": job.failure_code,
    }


def load_report_job(session: Session, job_id: UUID | str) -> ReportJob:
    uid = UUID(str(job_id)) if isinstance(job_id, str) else job_id
    job = session.scalar(select(ReportJob).where(ReportJob.id == uid))
    if job is None:
        raise RuntimeError(f"report job {job_id} not found")
    return job
