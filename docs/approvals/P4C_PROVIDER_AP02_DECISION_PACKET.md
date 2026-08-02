# P4-C Provider-specific AP-02 decision/evidence packet

**Status:** `PENDING / NOT APPROVED`

Use one separately completed packet for exactly one proposed Provider/model/endpoint combination. This template neither suggests nor selects a Provider and contains no credential value, person name, endpoint, or approval.

## 0. Research prefill — non-approval only

The [2026-08-02 public-source due-diligence note](../research/2026-08-02-p4c-ocr-provider-due-diligence.md) recommends the following **first research candidate**, not a selected or approved Provider:

|Research-only field|Non-approval prefill|
|---|---|
|Candidate Provider|Azure AI Document Intelligence|
|Candidate model|`prebuilt-layout`|
|Candidate API semantics|REST API `2024-11-30` / Document Intelligence 4.0 GA|
|Candidate region|Korea Central|
|Proposed call shape if later approved|Synchronous/online bounded calls only|
|Research status|`CANDIDATE ONLY / NOT SELECTED / NOT APPROVED`|

This prefill does not assert that an account, tenant, subscription, resource, endpoint, or credential exists. Every formal decision field below remains `PENDING`, including all account, contract, payload, retention, credential, pricing/budget, P4-B intersection, and approver fields. Public research cannot satisfy Provider-specific AP-02.

## 1. Provider decision identity

|Field|Required value|
|---|---|
|Packet/evidence ID|`PENDING`|
|Provider|`PENDING`|
|Model|`PENDING`|
|Model version|`PENDING`|
|Endpoint|`PENDING`|
|Processing region|`PENDING`|
|Decision status|`PENDING / NOT APPROVED`|

## 2. Payload boundary

|Field|Required value|
|---|---|
|Allowed payload/document categories|`PENDING`|
|Redacted field allow-list|`PENDING`|
|Forbidden fields and content|`PENDING`|
|Redaction method/version and validation evidence|`PENDING`|
|Request-size and batching limits|`PENDING`|

Anything not explicitly allow-listed is forbidden and must fail closed before transmission.

## 3. Retention, deletion, and training use

|Field|Required value|
|---|---|
|Provider retention period and start event|`PENDING`|
|Provider deletion method/SLA/evidence|`PENDING`|
|Training or service-improvement use|`PENDING`|
|Training-use opt-out setting and evidence|`PENDING`|
|Abuse monitoring or exceptional retention|`PENDING`|

## 4. Contract, subprocessors, and security review

|Field|Required value|
|---|---|
|Subprocessor list/version/date|`PENDING`|
|DPA/contract reference and review result|`PENDING`|
|Security/privacy review evidence ID|`PENDING`|
|Data residency and cross-border transfer assessment|`PENDING`|
|Material contractual exceptions and accepted risk|`PENDING`|

## 5. Credential and log controls

Do not record secret values in this packet.

|Field|Required value|
|---|---|
|Approved credential source/reference|`PENDING`|
|Credential owner|`PENDING`|
|Rotation period/process|`PENDING`|
|Least-privilege scopes and rationale|`PENDING`|
|Revocation procedure|`PENDING`|
|Request/response/error log-redaction controls and evidence|`PENDING`|

## 6. Pricing and budget

|Field|Required value|
|---|---|
|Pricing version/effective date|`PENDING`|
|Currency|`PENDING`|
|Unit pricing model|`PENDING`|
|Bounded benchmark budget|`PENDING`|
|Hard cost cap and enforcement method|`PENDING`|
|Budget/cost owner|`PENDING`|

## 7. Audit and response custody

|Field|Required value|
|---|---|
|Audit event fields|`PENDING`|
|Correlation identifier policy|`PENDING`|
|Raw-response retention period/location reference|`PENDING`|
|Raw-response access and least privilege|`PENDING`|
|Raw-response deletion evidence|`PENDING`|
|Prohibited log/audit content|`PENDING`|

## 8. Disable, rollback, fallback, and incident ownership

|Field|Required value|
|---|---|
|Disable switch and verification evidence|`PENDING`|
|Rollback criteria and procedure|`PENDING`|
|Manual fallback workflow|`PENDING`|
|Incident owner|`PENDING`|
|Incident escalation/contact evidence reference|`PENDING`|
|Credential revocation and containment procedure|`PENDING`|

## 9. Destination and corpus intersection

|Field|Required value|
|---|---|
|Approved Provider destination|`PENDING`|
|Approved P4-B packet/evidence reference|`PENDING`|
|Approved P4-B manifest ID/version|`PENDING`|
|Intersection of P4-B corpus scope and this P4-C payload/destination scope|`PENDING`|
|Explicit exclusions outside the intersection|`PENDING`|

## 10. Provider-specific AP-02 decision

|Field|Required value|
|---|---|
|Provider-specific approver|`PENDING`|
|Approval/decision date|`PENDING`|
|Approval evidence ID|`PENDING`|
|Approved Provider/model/version/endpoint/region|`PENDING`|
|Approved bounded call/benchmark scope|`PENDING`|
|Final decision|`PENDING / NOT APPROVED`|

## Fail-closed completion rules

1. One packet applies to one Provider/model/version/endpoint scope only. Generic, cross-provider, inherited, or implied approval is invalid.
2. Any `PENDING`, blank, missing, ambiguous, or unverified required field keeps P4-C at `BLOCKED_AP02_PROVIDER_OPT_IN`.
3. All fields must be complete and approved before adapter implementation, credential use, network access, or any Provider call.
4. An external benchmark is allowed only within the exact intersection of an approved P4-B corpus packet and this approved P4-C Provider packet.
5. P4-B approval alone never permits transmission, and P4-C approval alone never establishes corpus representativeness or permits an unreferenced corpus.
6. Provider, model, version, endpoint, region, payload, contract, subprocessor, retention, credential, pricing, destination, or incident-control changes require a new or explicitly versioned Provider-specific decision.
