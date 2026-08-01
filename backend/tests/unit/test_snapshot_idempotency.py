from dataclasses import FrozenInstanceError
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from hyc_domain.errors import FailureCode
from hyc_domain.idempotency import (
    IdempotencyConflict,
    IdempotencyState,
    complete_idempotency,
    resolve_idempotency,
)
from hyc_domain.snapshots import CanonicalizationError, DecisionSnapshot, canonical_hash


def _approval_payload() -> dict[str, object]:
    return {
        "spec_version": {"id": "spec-v1", "semantic_version": 1},
        "spec_items": [{"id": "item-1", "operator": "GTE", "lower": "1"}],
        "mapping": [{"status": "MANUAL_CONFIRMED"}],
        "supplier_results": [{"status": "MISSING"}],
        "internal_results": [{"value": "1"}],
        "unit_conversions": {"version": "conversion-v1"},
        "item_decisions": [{"overall": "ON_HOLD"}],
        "source_policy": ["INTERNAL_ONLY"],
        "missing_policy": ["HOLD"],
        "overall_decision": "ON_HOLD",
        "document_hashes": ["a" * 64],
        "engine_version": "engine-v1",
        "policy_version": "policy-v1",
        "rounding_version": "round-v1",
        "conversion_version": "conversion-v1",
        "approver": {"actor_id": "lead-1", "role": "LEAD"},
        "sample_policy": ["ALL_SAMPLES_IN_SPEC"],
        "lot_reference": {"lot_id": "lot-1"},
        "allocation_reference": {"allocation_id": "allocation-1"},
        "decision_reasons": {"reason": "fail closed"},
    }


def test_snapshot_hash_is_canonical_immutable_and_v1_remains_distinct() -> None:
    v1 = DecisionSnapshot.freeze({"spec_version": 1, "value": Decimal("1.20"), "items": ["A"]})
    v2 = DecisionSnapshot.freeze({"spec_version": 2, "value": Decimal("1.20"), "items": ["A"]})
    assert v1.content_hash == canonical_hash({"items": ["A"], "spec_version": 1, "value": "1.20"})
    assert v1.content_hash != v2.content_hash
    with pytest.raises(FrozenInstanceError):
        v1.content_hash = "mutate"  # type: ignore[misc]


def test_snapshot_deeply_freezes_payload_and_returns_a_defensive_copy() -> None:
    payload = {"items": [{"value": Decimal("1.20")}], "when": date(2026, 7, 31)}
    frozen = DecisionSnapshot.freeze(payload)
    payload["items"][0]["value"] = Decimal("9.99")
    first_view = frozen.payload
    first_view["items"][0]["value"] = "mutated"
    assert frozen.payload == {"items": [{"value": "1.20"}], "when": "2026-07-31"}


@pytest.mark.parametrize(
    "payload",
    (
        {"float": 1.0},
        {"non_string_key": {1: "collision"}},
        {"unsupported": object()},
        {"naive": datetime(2026, 7, 31, 12, 0)},
        {"nan": Decimal("NaN")},
        {"infinity": Decimal("Infinity")},
    ),
)
def test_canonicalization_fails_closed_for_noncanonical_values(payload: dict[str, object]) -> None:
    with pytest.raises(CanonicalizationError):
        canonical_hash(payload)


def test_canonical_hash_is_order_independent_and_preserves_decimal_scale_and_utc() -> None:
    first = {"at": datetime(2026, 7, 31, 9, 0, tzinfo=UTC), "value": Decimal("1.20"), "ok": True}
    second = {"ok": True, "value": Decimal("1.20"), "at": datetime(2026, 7, 31, 9, 0, tzinfo=UTC)}
    assert canonical_hash(first) == canonical_hash(second)
    assert canonical_hash(first) != canonical_hash({**second, "value": Decimal("1.2")})


def test_snapshot_rejects_non_string_key_collision_before_key_stringification() -> None:
    with pytest.raises(CanonicalizationError):
        canonical_hash({"1": "string-key", 1: "integer-key"})  # type: ignore[dict-item]


def test_approval_snapshot_requires_value_complete_decision_evidence() -> None:
    with pytest.raises(CanonicalizationError, match="value-complete"):
        DecisionSnapshot.freeze_for_approval({"overall_decision": "ACCEPTED"})
    snapshot = DecisionSnapshot.freeze_for_approval(_approval_payload())
    assert snapshot.payload["overall_decision"] == "ON_HOLD"
    snapshot.verify()


@pytest.mark.parametrize("empty_value", (None, "", "   ", [], {}))
def test_approval_snapshot_rejects_null_or_empty_required_values(
    empty_value: object,
) -> None:
    payload = _approval_payload()
    payload["document_hashes"] = empty_value
    with pytest.raises(CanonicalizationError, match="null or empty"):
        DecisionSnapshot.freeze_for_approval(payload)


def test_forged_approval_snapshot_hash_is_rejected() -> None:
    real = DecisionSnapshot.freeze_for_approval(_approval_payload())
    forged = DecisionSnapshot(real.canonical_payload_json, "f" * 64)
    with pytest.raises(CanonicalizationError, match="hash"):
        forged.verify()


def test_idempotency_replays_same_hash_and_conflicts_on_different_hash() -> None:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    created = resolve_idempotency(
        None,
        principal_id="quality-a",
        scope="inspection.create",
        key="request-1",
        request={"a": 1},
        now=now,
        lease_for=timedelta(minutes=1),
    )
    assert created.state is IdempotencyState.PENDING
    assert (
        resolve_idempotency(
            created,
            principal_id="quality-a",
            scope="inspection.create",
            key="request-1",
            request={"a": 1},
            now=now,
            lease_for=timedelta(minutes=1),
        )
        == created
    )
    with pytest.raises(IdempotencyConflict):
        resolve_idempotency(
            created,
            principal_id="quality-a",
            scope="inspection.create",
            key="request-1",
            request={"a": 2},
            now=now,
            lease_for=timedelta(minutes=1),
        )
    assert IdempotencyConflict.code is FailureCode.IDEMPOTENCY_CONFLICT


def test_expired_pending_idempotency_lease_is_recoverable_by_new_worker() -> None:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    pending = resolve_idempotency(
        None,
        principal_id="quality-a",
        scope="approve",
        key="recover",
        request={"case": "synthetic"},
        now=now,
        lease_for=timedelta(seconds=5),
        lease_owner="worker-1",
    )
    with pytest.raises(IdempotencyConflict, match="another worker"):
        resolve_idempotency(
            pending,
            principal_id="quality-a",
            scope="approve",
            key="recover",
            request={"case": "synthetic"},
            now=now + timedelta(seconds=1),
            lease_for=timedelta(seconds=5),
            lease_owner="worker-2",
        )
    recovered = resolve_idempotency(
        pending,
        principal_id="quality-a",
        scope="approve",
        key="recover",
        request={"case": "synthetic"},
        now=now + timedelta(seconds=6),
        lease_for=timedelta(seconds=5),
        lease_owner="worker-2",
    )
    assert recovered.lease_owner == "worker-2"
    assert recovered.lease_expires_at == now + timedelta(seconds=11)


def test_idempotency_principal_terminal_response_and_expired_retryable_lease() -> None:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    pending = resolve_idempotency(
        None,
        principal_id="quality-a",
        scope="approve",
        key="same",
        request={"a": 1},
        now=now,
        lease_for=timedelta(seconds=10),
        lease_owner="worker-1",
    )
    completed = complete_idempotency(
        pending, status=201, body={"id": "case-1"}, resource_ref="case-1", now=now
    )
    assert (
        resolve_idempotency(
            completed,
            principal_id="quality-a",
            scope="approve",
            key="same",
            request={"a": 1},
            now=now,
            lease_for=timedelta(seconds=10),
        )
        == completed
    )
    other_principal = resolve_idempotency(
        None,
        principal_id="quality-b",
        scope="approve",
        key="same",
        request={"a": 1},
        now=now,
        lease_for=timedelta(seconds=10),
    )
    assert other_principal.principal_id == "quality-b"
    retryable = pending.mark_retryable(now=now)
    with pytest.raises(IdempotencyConflict, match="lease"):
        resolve_idempotency(
            retryable,
            principal_id="quality-a",
            scope="approve",
            key="same",
            request={"a": 1},
            now=now + timedelta(seconds=5),
            lease_for=timedelta(seconds=10),
        )
    assert (
        resolve_idempotency(
            retryable,
            principal_id="quality-a",
            scope="approve",
            key="same",
            request={"a": 1},
            now=now + timedelta(seconds=11),
            lease_for=timedelta(seconds=10),
        ).state
        is IdempotencyState.PENDING
    )
