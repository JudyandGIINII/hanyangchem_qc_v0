# P0A Read-only Evidence Freeze

**Original observation (UTC):** `2026-07-30T14:53:19.285115Z`
**Status:** `P0A_COMPLETE`  
**Authority:** AP-01~05 and P0A/P0B/P1 approved by the user on 2026-07-30.

## Safety result

- Source evidence was read locally only; no source body or worksheet cell value is copied into this evidence packet.
- Real PDF/XLSX files remain prohibited from Git and external transmission under AP-05.
- The original 2026-07-30 observation captured SHA-256, byte size, format, and filesystem metadata before and after; the v1 artifact retains one canonical snapshot plus `source_immutable_before_after: true`, not explicit per-source before/after records.
- The controller's 2026-07-31 reverification sidecar is the first tracked artifact with explicit per-source before and after observations. It is distinct from the original observation; neither record performs import, apply, database write, or external transmission.
- Current-tree masking replaces historical exact filename fields with stable aliases and `filename_sha256` values calculated from the historical tracked filename strings. Historical Git already contained filename metadata; no history rewrite was authorized. This is forward remediation and does not claim history was purged.

## Source manifest

|Source alias|Format|Bytes|SHA-256|
|---|---:|---:|---|
|`qm301-7-rb-import-inspection`|xlsx|338134|`b8ebb179b0dece9a6aa06229fe28feb1890082bd32a46e3ccc314febec138c9f`|
|`domestic-8p-package`|pdf|370049|`6ae50fdd4c9e01be39ebf113bf3198d0407ab427c3de782799e9014c8a88d53f`|
|`inbound-inspection-raw-data`|xlsx|11836|`4de7b781c80a8bf663a8983af03e9ae912919c8ac70bf3d1f5dda1e07f281ff1`|
|`calcium-chloride-coa-2025-04-23`|pdf|904378|`da50e56873e37cd07401050bec2976697adabb47927268a8cbbd2674eec0ca48`|

Machine-readable canonical v1 evidence: [`2026-07-30-p0a-source-manifest.json`](./2026-07-30-p0a-source-manifest.json). The v1 `read_only_observation.workbook_metadata[0]` path remains available for the accepted P0B expectation fixture. Controller-only two-pass reverification: [`2026-07-31-p0a-controller-reverification.json`](./2026-07-31-p0a-controller-reverification.json).

## Workbook metadata-only observation

|Source alias|Worksheets|Aggregate used rows metadata|Max used columns metadata|
|---|---:|---:|---:|
|`qm301-7-rb-import-inspection`|38|1438|71|
|`inbound-inspection-raw-data`|3|13|56|

The original **38 templates / 119 item rows** claim remained `UNVERIFIED_UNTIL_P0B_PARSER`; worksheet counts and generic dimension metadata do not prove business-item cardinality. P0A did not infer or auto-correct row meaning. P0B later reproduced the count through its accepted read-only dry-run contract.

## Decision and traceability references

- AP-01~08 and approved AP-01~05 values: [`../plans/2026-07-30-integrated-implementation-plan.md`](../plans/2026-07-30-integrated-implementation-plan.md)
- PRD contradictions and integrated resolution: integrated plan sections 2–3
- FR/policy/NFR/AT/DoD trace authority: [`../TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md)

## P0A gate

- [x] Original before/after observation is asserted by `source_immutable_before_after: true`; v1 retains a single canonical snapshot rather than explicit per-source records
- [x] Controller 2026-07-31 two-pass reverification, the first tracked explicit per-source before/after record, is linked separately
- [x] No source body, worksheet cell value, or secrets copied
- [x] AP decisions and contradiction references recorded
- [x] Requirement trace matrix exists
- [x] No parser, database, fixture, external call, or migration executed in P0A
