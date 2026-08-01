from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from hyc_domain.errors import CodedDomainError, FailureCode


class CanonicalizationError(CodedDomainError):
    """Raised when a value cannot be represented by the frozen snapshot contract."""

    code = FailureCode.INVALID_SNAPSHOT


APPROVAL_SNAPSHOT_REQUIRED_KEYS = frozenset(
    {
        "spec_version",
        "spec_items",
        "mapping",
        "supplier_results",
        "internal_results",
        "unit_conversions",
        "item_decisions",
        "source_policy",
        "missing_policy",
        "overall_decision",
        "document_hashes",
        "engine_version",
        "policy_version",
        "rounding_version",
        "conversion_version",
        "approver",
        "sample_policy",
        "lot_reference",
        "allocation_reference",
        "decision_reasons",
    }
)


def _normalise(value: Any) -> Any:
    if value is None or isinstance(value, (bool, str, int)):
        return value
    if isinstance(value, float):
        raise CanonicalizationError(
            "binary floating-point values are not canonical snapshot values"
        )
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise CanonicalizationError("snapshot Decimal values must be finite")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalizationError("snapshot datetimes must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise CanonicalizationError("snapshot mapping keys must be strings")
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_normalise(item) for item in value]
    raise CanonicalizationError(f"unsupported snapshot value type: {type(value).__name__}")


def canonical_json(payload: dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        raise CanonicalizationError("snapshot payload must be a mapping")
    return json.dumps(
        _normalise(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _is_empty_required_value(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (dict, list, tuple)):
        return not value
    return False


@dataclass(frozen=True, slots=True)
class DecisionSnapshot:
    """A value snapshot stored as canonical JSON, never as caller-owned mutable objects."""

    _canonical_json: str
    content_hash: str

    @property
    def payload(self) -> dict[str, Any]:
        """Return a fresh decoded view so external mutation cannot change the snapshot."""
        decoded = json.loads(self._canonical_json)
        if not isinstance(decoded, dict):  # Defensive: canonical_json always emits an object here.
            raise CanonicalizationError("stored snapshot is not an object")
        return decoded

    @property
    def canonical_payload_json(self) -> str:
        return self._canonical_json

    @classmethod
    def freeze(cls, payload: dict[str, Any]) -> DecisionSnapshot:
        canonical = canonical_json(payload)
        return cls(
            _canonical_json=canonical,
            content_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )

    @classmethod
    def freeze_for_approval(cls, payload: dict[str, Any]) -> DecisionSnapshot:
        missing = APPROVAL_SNAPSHOT_REQUIRED_KEYS.difference(payload)
        if missing:
            raise CanonicalizationError(
                "approval snapshot is not value-complete: " + ",".join(sorted(missing))
            )
        empty = sorted(
            key
            for key in APPROVAL_SNAPSHOT_REQUIRED_KEYS
            if _is_empty_required_value(payload[key])
        )
        if empty:
            raise CanonicalizationError(
                "approval snapshot has null or empty required values: "
                + ",".join(empty)
            )
        if payload.get("overall_decision") not in {
            "ACCEPTED",
            "REJECTED",
            "ON_HOLD",
        }:
            raise CanonicalizationError(
                "approval snapshot overall_decision must be a candidate state"
            )
        return cls.freeze(payload)

    def verify(self) -> None:
        payload = self.payload
        expected = canonical_hash(payload)
        if self.content_hash != expected:
            raise CanonicalizationError("snapshot content hash does not match canonical payload")
        verified = self.freeze_for_approval(payload)
        if verified.content_hash != self.content_hash:
            raise CanonicalizationError("snapshot is not canonical")
