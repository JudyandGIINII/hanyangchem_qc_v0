# ADR 0004: Local Auth/RBAC and real-source evidence prohibition

**Status:** Accepted (AP-04 and AP-05, 2026-07-30)

## Decision

The pilot default is Local Auth with Argon2id and roles `INSPECTOR`, `LEAD`, `ADMIN`, `VIEWER`, and `SERVICE`; `ADMIN` cannot approve quality decisions. Real PDF/XLSX source files are prohibited from Git, mirrors, uploads, and external transmission; only approved hashes and masked/derived fixtures may be versioned.

## Consequences

P0B has no authentication service implementation and stores no source body. Future approval paths must enforce role separation and audit evidence at API and database boundaries, while all source handling remains subject to the evidence prohibition.

## Rollback and exceptions

Rollback disables Local Auth access and revokes any pilot credentials; it does not relax audit or source-evidence controls. Any auth-provider change or source-handling exception requires later AP-06/AP-08 gates plus explicit authorized security, quality, and operations approval; no implementation flag can override this decision.
