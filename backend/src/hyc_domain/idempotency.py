from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from hyc_domain.errors import CodedDomainError, FailureCode
from hyc_domain.snapshots import canonical_hash, canonical_json


class IdempotencyState(StrEnum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"


class IdempotencyConflict(CodedDomainError):
    code = FailureCode.IDEMPOTENCY_CONFLICT


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    principal_id: str
    scope: str
    key: str
    request_hash: str
    state: IdempotencyState
    lease_expires_at: datetime | None
    lease_owner: str | None
    response_status: int | None
    response_body: str | None
    resource_ref: str | None
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None

    def mark_retryable(self, *, now: datetime) -> IdempotencyRecord:
        if self.state is IdempotencyState.COMPLETED:
            raise IdempotencyConflict("completed idempotency record is terminal")
        return replace(
            self,
            state=IdempotencyState.FAILED_RETRYABLE,
            updated_at=now,
        )


def request_hash(request: dict[str, Any]) -> str:
    return canonical_hash(request)


def _same_identity(
    record: IdempotencyRecord, *, principal_id: str, scope: str, key: str, digest: str
) -> bool:
    return (record.principal_id, record.scope, record.key, record.request_hash) == (
        principal_id,
        scope,
        key,
        digest,
    )


def resolve_idempotency(
    existing: IdempotencyRecord | None,
    *,
    principal_id: str,
    scope: str,
    key: str,
    request: dict[str, Any],
    now: datetime,
    lease_for: timedelta,
    lease_owner: str | None = None,
    expires_at: datetime | None = None,
) -> IdempotencyRecord:
    if not principal_id or not scope or not key or lease_for <= timedelta(0):
        raise ValueError("principal, scope, key, and a positive lease are required")
    digest = request_hash(request)
    if existing is None:
        return IdempotencyRecord(
            principal_id=principal_id,
            scope=scope,
            key=key,
            request_hash=digest,
            state=IdempotencyState.PENDING,
            lease_expires_at=now + lease_for,
            lease_owner=lease_owner,
            response_status=None,
            response_body=None,
            resource_ref=None,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
        )
    if not _same_identity(existing, principal_id=principal_id, scope=scope, key=key, digest=digest):
        raise IdempotencyConflict(
            "idempotency key has a different principal, scope, or request hash"
        )
    if existing.expires_at is not None and existing.expires_at <= now:
        raise IdempotencyConflict("idempotency record has expired")
    if existing.state is IdempotencyState.COMPLETED:
        return existing
    if existing.state is IdempotencyState.PENDING:
        if existing.lease_expires_at is None or existing.lease_expires_at > now:
            if (
                existing.lease_owner is not None
                and lease_owner is not None
                and existing.lease_owner != lease_owner
            ):
                raise IdempotencyConflict("idempotency request is leased by another worker")
            return existing
        return replace(
            existing,
            lease_expires_at=now + lease_for,
            lease_owner=lease_owner,
            updated_at=now,
        )
    if existing.lease_expires_at is not None and existing.lease_expires_at > now:
        raise IdempotencyConflict("retryable idempotency lease has not expired")
    return replace(
        existing,
        state=IdempotencyState.PENDING,
        lease_expires_at=now + lease_for,
        lease_owner=lease_owner,
        updated_at=now,
    )


def complete_idempotency(
    record: IdempotencyRecord,
    *,
    status: int,
    body: dict[str, Any],
    resource_ref: str | None,
    now: datetime,
) -> IdempotencyRecord:
    if record.state is IdempotencyState.COMPLETED:
        return record
    if record.state is not IdempotencyState.PENDING:
        raise IdempotencyConflict("only a pending idempotency record may complete")
    return replace(
        record,
        state=IdempotencyState.COMPLETED,
        lease_expires_at=None,
        lease_owner=None,
        response_status=status,
        response_body=canonical_json(body),
        resource_ref=resource_ref,
        updated_at=now,
    )
