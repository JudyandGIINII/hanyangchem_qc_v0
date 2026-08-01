# ADR 0003: Canonical LOT and receipt allocation identity

**Status:** Accepted (AP-03, 2026-07-30)

## Decision

Canonical material LOT identity is separate from inbound receipt allocation identity: `material_lots` and `receipt_lot_allocations` are distinct records. The exact v1 identity key is supplier + material + NFKC/trimmed LOT number. Production date and package mark are conflict evidence, never v1 key components. Missing LOT number is provisional, and re-entry of the same normalized key resolves through a bounded `merged_into_id` chain to the surviving canonical LOT.

## Consequences

No hidden one-to-one LOT/receipt assumption is allowed. Missing LOT number fails closed as provisional; conflicting production/package evidence enters conflict review without silently changing v1 identity. Promotion and merge remain explicit audited actions, allocations to merged LOTs are denied, and a supplier reuse rule can only be introduced as a versioned policy with evidence.

## Rollback and exceptions

Rollback retains canonical records and disables the proposed policy version rather than merging or rewriting history. A LOT merge is a master-data identity action, not a quality-decision approval: it requires two different actors, one `LEAD` quality approver and one `ADMIN` master-data approver, plus reason, expected version, lock, and append-only audit evidence.
