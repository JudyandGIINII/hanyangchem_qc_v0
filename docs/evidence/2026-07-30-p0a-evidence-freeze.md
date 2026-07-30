# P0A Read-only Evidence Freeze

**Observed at (UTC):** `2026-07-30T14:53:19.285115Z`  
**Status:** `P0A_COMPLETE`  
**Authority:** AP-01~05 and P0A/P0B/P1 approved by the user on 2026-07-30.

## Safety result

- Source evidence was read locally only; no source body or worksheet cell value is copied into this evidence packet.
- Real PDF/XLSX files remain prohibited from Git and external transmission under AP-05.
- SHA-256, byte size, format, and filesystem metadata were captured before and after observation.
- Before/after metadata and digest comparison: **PASS — source immutable**.

## Source manifest

|Filename|Format|Bytes|SHA-256|
|---|---:|---:|---|
|`QM301-7_RB 수입검사성적서.xlsx`|xlsx|338134|`b8ebb179b0dece9a6aa06229fe28feb1890082bd32a46e3ccc314febec138c9f`|
|`물먹는하마 내수8P 패키지_250213.pdf`|pdf|370049|`6ae50fdd4c9e01be39ebf113bf3198d0407ab427c3de782799e9014c8a88d53f`|
|`수입검사성적서_Raw_Data.xlsx`|xlsx|11836|`4de7b781c80a8bf663a8983af03e9ae912919c8ac70bf3d1f5dda1e07f281ff1`|
|`업체COA_염화칼슘_세계로비드_2025.04.23.pdf`|pdf|904378|`da50e56873e37cd07401050bec2976697adabb47927268a8cbbd2674eec0ca48`|

Machine-readable canonical evidence: [`2026-07-30-p0a-source-manifest.json`](./2026-07-30-p0a-source-manifest.json).

## Workbook metadata-only observation

|Filename|Worksheets|Aggregate used rows metadata|Max used columns metadata|
|---|---:|---:|---:|
|`QM301-7_RB 수입검사성적서.xlsx`|38|1438|71|
|`수입검사성적서_Raw_Data.xlsx`|3|13|56|

The previously observed **38 templates / 119 item rows** is retained as `UNVERIFIED_UNTIL_P0B_PARSER`. Workbook worksheet counts and generic worksheet-dimension metadata do not prove business-item cardinality. P0A does not infer or auto-correct row meaning; P0B must reproduce the count through a tests-first dry-run parser and report discrepancies for QUALITY review.

## Decision and traceability references

- AP-01~08 and approved AP-01~05 values: [`../plans/2026-07-30-integrated-implementation-plan.md`](../plans/2026-07-30-integrated-implementation-plan.md)
- PRD contradictions and integrated resolution: integrated plan sections 2–3
- FR/policy/NFR/AT/DoD trace authority: [`../TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md)

## P0A gate

- [x] Source mtime/size/hash before and after match
- [x] No source body, worksheet cell value, or secrets copied
- [x] 38/119 claim remains explicitly unverified
- [x] AP decisions and contradiction references recorded
- [x] Requirement trace matrix exists
- [x] No parser, database, fixture, external call, or migration executed in P0A
