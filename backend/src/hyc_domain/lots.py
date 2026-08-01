from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class LotIdentityStatus(StrEnum):
    CANONICAL = "CANONICAL"
    PROVISIONAL = "PROVISIONAL"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    MERGED = "MERGED"


def normalize_identity_component(raw: str | None) -> str | None:
    if raw is None:
        return None
    normalized = unicodedata.normalize("NFKC", raw).strip()
    return normalized or None


@dataclass(frozen=True, slots=True)
class LotIdentity:
    policy_version: str
    supplier_lot_no: str | None
    production_date: str | None
    package_mark: str | None

    def key_and_status(self) -> tuple[str | None, LotIdentityStatus]:
        if self.policy_version != "v1":
            return None, LotIdentityStatus.CONFLICT_REVIEW
        lot_number = normalize_identity_component(self.supplier_lot_no)
        if lot_number is None:
            return None, LotIdentityStatus.PROVISIONAL
        return lot_number, LotIdentityStatus.CANONICAL


def can_merge(
    *,
    status: LotIdentityStatus,
    expected_version: int,
    current_version: int,
    lead_actor_id: object,
    admin_actor_id: object,
    reason: str,
) -> bool:
    return (
        status is LotIdentityStatus.CONFLICT_REVIEW
        and expected_version == current_version
        and lead_actor_id != admin_actor_id
        and bool(reason.strip())
    )
