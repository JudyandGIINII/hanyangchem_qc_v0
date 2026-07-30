# ADR 0001: Deployment and data boundary

**Status:** Accepted (AP-01, 2026-07-30)

## Decision

The pilot default is an internal-network Mac/Linux Docker Compose deployment. Database data and source documents remain in internal storage; public deployment and service exposure are not authorized.

## Consequences

P0B may create only read-only, local evidence tooling and masked fixtures. Any production-like deployment, storage relocation, network exposure, or retention change requires the later AP-06/AP-08 operating and production-transition gates.

## Rollback and exceptions

Rollback is disabling the pilot environment and retaining no newly imported real data. An exception requires explicit product and operations approval from the authorized decision owner; a test pass or feature flag is not authority.
