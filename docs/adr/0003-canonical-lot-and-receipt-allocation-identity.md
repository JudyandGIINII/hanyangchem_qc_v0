# ADR 0003: Canonical LOT and receipt allocation identity

**Status:** Accepted (AP-03, 2026-07-30)

## Decision

Canonical material LOT identity is separate from inbound receipt allocation identity: `material_lots` and `receipt_lot_allocations` are distinct records. The pilot identity key is supplier + material + NFKC/trimmed LOT number; production date is not part of the default key.

## Consequences

No hidden one-to-one LOT/receipt assumption is allowed. Missing identity components must fail closed as provisional or conflict-review cases, and a supplier reuse rule can only be introduced as a versioned policy with evidence.

## Rollback and exceptions

Rollback retains canonical records and disables the proposed policy version rather than merging or rewriting history. P2 is conditionally authorized only after P0B QC/controller acceptance; any identity-policy exception, merge, or activation still requires the P2 data-model gate and explicit authorized quality/master-data approval with audit evidence.
