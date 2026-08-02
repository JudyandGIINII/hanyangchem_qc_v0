# P4-B QUALITY corpus decision/evidence packet

**Status:** `PENDING / NOT APPROVED`

This template records a bounded QUALITY decision for one proposed local P4-B corpus. It contains no corpus body, actual storage path, source hash, person name, or approval. Complete it only with evidence handled under the approved data-classification and access process.

## 1. Decision identity

|Field|Required value|
|---|---|
|Packet/evidence ID|`PENDING`|
|Manifest ID|`PENDING`|
|Manifest version|`PENDING`|
|Decision scope and bounded benchmark purpose|`PENDING`|
|Decision status|`PENDING / NOT APPROVED`|

## 2. Source manifest and classification

Add one row per proposed source without embedding the document body.

|Source reference|SHA-256|Data classification|Document type|Supplier category|Difficulty category|Included/excluded rationale|
|---|---|---|---|---|---|---|
|`PENDING`|`PENDING`|`PENDING`|`PENDING`|`PENDING`|`PENDING`|`PENDING`|

## 3. Representativeness decision

|Document type|Supplier segment|Difficulty stratum|Proposed count/coverage|Known gaps or skew|Rationale|
|---|---|---|---|---|---|
|`PENDING`|`PENDING`|`PENDING`|`PENDING`|`PENDING`|`PENDING`|

- Population or operating context represented: `PENDING`
- Sampling/selection method: `PENDING`
- Why the matrix is sufficient for this bounded run: `PENDING`
- Explicit non-representative uses: `PENDING`

## 4. De-identification and residual risk

|Field|Required value|
|---|---|
|De-identification method and version|`PENDING`|
|Fields/content removed, transformed, or retained|`PENDING`|
|De-identification reviewer|`PENDING`|
|Review date|`PENDING`|
|Residual re-identification risk assessment|`PENDING`|
|Residual-risk mitigation and acceptance evidence|`PENDING`|

## 5. Approved local custody

|Field|Required value|
|---|---|
|Approved local storage reference|`PENDING`|
|Storage owner|`PENDING`|
|Authorized roles/users and least-privilege rationale|`PENDING`|
|Access grant/review evidence|`PENDING`|
|Encryption at rest|`PENDING`|
|Encryption in transit within the approved local boundary, if applicable|`PENDING`|

Do not place actual sensitive paths in this packet; record an approved evidence reference instead.

## 6. Absence from prohibited surfaces

Attach or reference evidence proving that real source bodies are absent from every surface below.

|Surface|Required proof/evidence ID|Result|
|---|---|---|
|Git history and working trees|`PENDING`|`PENDING`|
|Repository mirrors or artifact mirrors|`PENDING`|`PENDING`|
|AI prompts|`PENDING`|`PENDING`|
|AI/chat transcripts|`PENDING`|`PENDING`|
|CI inputs, logs, caches, and artifacts|`PENDING`|`PENDING`|

## 7. Retention and deletion

|Field|Required value|
|---|---|
|Retention owner|`PENDING`|
|Retention period and start event|`PENDING`|
|Deletion trigger and method|`PENDING`|
|Deletion verifier|`PENDING`|
|Required deletion evidence and evidence location/ID|`PENDING`|
|Exceptions/holds and approval process|`PENDING`|

## 8. Benchmark destinations

|Destination category|Decision|Exact bounded scope and rationale|
|---|---|---|
|Allowed local benchmark destinations|`PENDING`|`PENDING`|
|Forbidden local destinations|`PENDING`|`PENDING`|
|External destinations|`FORBIDDEN unless separately approved by the intersecting P4-C packet`|`PENDING`|

## 9. Exclusions and limitations

- Excluded document types, suppliers, difficulty strata, fields, or uses: `PENDING`
- Known quality, coverage, de-identification, or measurement limitations: `PENDING`
- Claims this decision does not support: `PENDING`
- Conditions requiring reapproval or a new manifest version: `PENDING`

## 10. QUALITY decision

|Field|Required value|
|---|---|
|Named QUALITY approver|`PENDING`|
|Approval/decision date|`PENDING`|
|Approval evidence ID|`PENDING`|
|Approved manifest ID/version|`PENDING`|
|Approved bounded local run scope|`PENDING`|
|Final decision|`PENDING / NOT APPROVED`|

## Fail-closed completion rules

1. Any `PENDING`, blank, missing, ambiguous, or unverified required field keeps P4-B at `BLOCKED_QUALITY_CORPUS_APPROVAL`.
2. Generic permission to continue, prepare, test, or benchmark is not QUALITY corpus approval.
3. Approval opens only the explicitly bounded local P4-B run recorded in this packet.
4. P4-B approval never authorizes external transmission, Provider access, P4-C implementation, or a Provider call.
5. Scope, manifest, custody, retention, destination, or risk changes require a new or explicitly versioned decision before use.
