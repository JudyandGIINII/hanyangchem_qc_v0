# 요구사항 추적 매트릭스 — 한양화학 수입검사 디지털화 및 LOT 추적

**상태:** P0A/P0B/P1/P2/P3 source complete and accepted; P2/P3 are delivered to `origin/main`. P4-A Offline/Synthetic is complete/accepted/delivered at original source/integration baseline `aeedceb2c3b7008439a9c72e3984be77f6135e51`; maintenance `cad1ab48b7ab1923638fe8600f23ef640efdab73` and fail-closed preflight `fce19681f75cac8f95bb6cde95ad50351cf9e309` are also accepted/delivered. The authorized local-only OCR engineering lane is complete/accepted/delivered at source/integration baseline `91fd4a8229b12d2b229f2ef9abb9dceef93591b5`; pre-closure main `96413d20230b62033ecb754a12e5a1a621a7b95c` is its later descendant, and the closure commit will be newer. Git history is authoritative for exact SHA/remote-tip state. P4-B remains `BLOCKED_QUALITY_CORPUS_APPROVAL` as a future representative-corpus validation gate, not code debt; P4-C remains deferred `BLOCKED_AP02_PROVIDER_OPT_IN` and is not required for local-only scope. No representative-corpus/production OCR quality, full P4/P5, release, production readiness, real-data apply/import, external Provider/network/credential, production migration, or production DB-role claim is authorized.
**정본:** `Prd.md`  
**계획:** `docs/plans/2026-07-30-integrated-implementation-plan.md`  
**규칙:** 아래 경로는 모두 구현 시 `Create` 대상이다. `Planned`는 통과를 의미하지 않는다. 각 행은 해당 Phase의 테스트가 실제 exit 0이고 Hermes 독립 QA가 증빙을 확인해야 `Verified`로 바뀐다.

## 소유자

- **DOMAIN:** 순수 판정·정책·상태 도메인
- **DATA:** PostgreSQL/Alembic/repository/invariant
- **API:** FastAPI application/RBAC/idempotency/OpenAPI
- **WORKER:** ingestion/OCR/parser/report/outbox
- **WEB:** Next.js UI/접근성/E2E
- **OPS:** 보안/관측/백업/복구/배포
- **QUALITY:** 품질팀 정책·golden/UAT 승인
- **HERMES-QA:** 독립 검증·gate 판정

## 2026-08-03 local-only OCR accepted-delivery trace

This table describes the accepted/delivered local-only OCR source at baseline `91fd4a8…`. Final independent review was `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 4, NOTE 8); B1/M1-M9 and MA-1 are closed. Evidence is generated-synthetic/local only and grants no representative-corpus or production claim.

|Requirement/control|Owner|Implementation and test evidence|Current gate|
|---|---|---|---|
|FR-OCR-001 page parsing|WORKER/QUALITY|Native text is used per page when sufficient; only insufficient pages render at bounded 300/400 DPI. Generated mixed native/scanned, rotation, signed skew, positive perspective transform, illumination, contrast, noise, blur/JPEG, scaling, native/scanned table, blank/corrupt/oversized cases are covered by `backend/tests/local_ocr/` and recorded real `make p4-local-ocr-smoke` evidence.|Accepted/delivered generated-synthetic/local scope|
|FR-OCR-002 provider abstraction|WORKER/API|`LocalOcrExtractionProvider` implements the existing extraction port; rooted opaque document resolution is bounded/immutable; no DB migration was needed; no fallback exists.|Accepted local-only source; not wired as an external/service route|
|FR-OCR-003 provenance|WORKER/API|Candidates preserve page, normalized source-frame rectangular bbox, spatial reading order, confidence, selected variant/recipe, rotation/deskew/perspective provenance, and stable reason ordering. Polygons are not implemented or claimed by this local OCR candidate.|Contract drift passed|
|FR-OCR-005 Human Review|WORKER/QUALITY|All local OCR candidates set `review_required=true`; native and local-OCR routes share one stable reason evaluator covering low/missing/native disagreement/variant disagreement/numeric/unit/LOT/table conditions. Native table suspicion uses a broad, over-inclusive bounded alignment signal without rendering/OCR. Missing and table regressions exercise real native layout; low-confidence proves evaluator wiring through a fake backend because production native lines use confidence 1.00. No auto-finalize/approve/decide path exists.|Fail closed; MA-1 independently closed; residual minors retained|
|Runtime/model supply chain|WORKER/OPS|Exact locked packages and versioned model manifest validate URL, archive size/hash, tree hash, engine/language/license/local path. Setup-only bootstrap is separate; runtime rejects path escape, endpoint/credential/source overrides, missing/mismatched models, auto-download, and network.|Local preflight passed; model binaries ignored/untracked|
|Resource and confidentiality limits|WORKER/OPS|PDF-only, 25 MiB, 10 pages, 120M pixels, 12 variants, 120 seconds, concurrency 1; source immutable; logs/reports omit path and text/full payload; socket/DNS guards surround engine initialization and prediction.|Focused/adversarial tests passed|
|Synthetic engineering KPI|WORKER/QUALITY|At independent-review time the expensive smoke had not been rerun after final native remediation; later Hermes ran the final source and recorded physical-line field/value header `1.0000`, numeric `1.0000`, public-provider candidate review exposure `1.0000`, network `0/0`, output `581ed7da…437c1`, aggregate `6545119c…6a9c`.|Generated-synthetic gate only; review-time caveat and later controller evidence both preserved|
|Repository regression|HERMES-QA|Backend 641 passed/92 deselected, Ruff, strict mypy 67, compileall; frontend Vitest 32/build; golden 198; preflight 97; local focused/runtime 43; contracts, migration 4, scans, Compose passed.|Controller final-source verification passed|
|Independent review and residuals|WORKER/API/OPS/HERMES-QA|Final `ACCEPT_WITH_MINOR` 0/0/4, NOTE 8; B1/M1-M9 and MA-1 closed. Residual minors are broad table signal, fake-backend-only native low-confidence evaluator wiring, independent-review-time smoke non-rerun before the later controller run, and duplicate native word extraction. Eight operational/contract/scope notes remain disclosed in the implementation note.|Accepted with bounded residual limitations|
|Git/delivery boundary|HERMES-QA|Source/integration baseline `91fd4a8…` was committed, fresh-main fast-forward integrated, and delivered; pre-closure `96413d2…` is a later descendant. Closure SHA/live tip comes from Git history.|Complete/accepted/delivered|
|Public synthetic demo boundary|WEB/OPS|Verified 2026-08-03 KST production deployment `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y` for Vercel `hanyangchem_qc` is `READY`; its URL `https://hanyangchem-739r15g9t-judy-ng-ii-nii-s-projects.vercel.app` has alias `https://hanyangchemqc.vercel.app` and meta `sourceCommit=cf6d6327172fb09da0fe0e3b12159f6596553c41`. Next.js 15.5.22 completed compile/lint/type, five static routes and `/api/health` in 57s; root 200 and health ready. Alias browser QA proved title/public no-backend/no-server-persistence boundary, no failed fetch/local resources, alias-only host, console 0, and local-only team-lead approval. Production/Preview flags are saved. `96413d2…` review remains `ACCEPT_WITH_MINOR` 0/0/6 with all six residuals unfixed; future missing/incorrect config can fall back to localhost and must repeat deployment API/browser proof. Later docs-only descendant leaves `frontend/` unchanged from `cf6d632…`.|Exact production frontend boundary verified; no backend/DB/worker/OCR/model/document exposure; no representative OCR/full-P4/P5/production-readiness claim|
|Deferred gates|QUALITY/OPS|P4-B remains required only if future representative real-corpus validation is desired; inventory is 4 candidate documents/0 eligible. P4-C remains required only for a future external Provider and is not required for local-only scope. Both packets remain pending and grant no approval.|P4-B future validation boundary; P4-C deferred; no active provider request|

## P0B delivery trace

|P0B task|Delivered candidate|Verification / ADR binding|Current gate|
|---|---|---|---|
|P0B.1|`backend/scripts/import_spec_workbook.py`|`backend/tests/integration/importers/test_spec_workbook_dry_run.py`: synthetic-only dry run; bounded all-member CRC/decompression reads; canonical OPC Content-Type resolution and media-type-driven XML parsing; exact workbook/worksheet/shared-strings/`.rels` types; complete ASCII RFC 3986 Relationship-Type and conservative canonical OPC member/Override/Target lexical validation (including safe in-root `..` only), attribute-free `Relationships` roots, unique IDs while same-target distinct typed relationships remain permitted; all fail closed|accepted|
|P0B.2|`fixtures/spec-import/qm301-7-expected.json`|Typed approved baseline binds 38 templates / 119 item rows to the approved source SHA-256; deterministic ordered `QUALITY_REVIEW_REQUIRED` digest/count discrepancy evidence, no auto-correction/apply|accepted|
|P0B.3|`fixtures/manifests/source-documents.yaml`|Metadata-only alias/hash manifest retains the v1 P0A observation path while linking the controller reverification; sensitive-document prevention covers extension patterns and importer tests generate temporary synthetic workbooks only|accepted|
|P0B.4|`docs/adr/0001-deployment-and-data-boundary.md` through `docs/adr/0004-local-auth-rbac-and-real-source-prohibition.md`|Read-only, external-OCR-off, LOT/allocation, and source-prohibition decisions remain binding|accepted|

P0B final independent review: `APPROVE` after 67 in-memory probes (HIGH 0, MEDIUM 0). The accepted LOW note—generic scheme-specific URI semantics—remains defense-in-depth because the relationship roles consumed by the importer use exact allowlists. Controller evidence records `127 passed`; the approved real QM301 dry-run returned 38 templates/119 rows with discrepancy 0, DB write/apply 0, unchanged source hash/size/mtime, and tracked sensitive documents 0.

## P1 remediation verification trace

|P1 control|Actual 2026-07-31 evidence|Current gate|
|---|---|---|
|Backend reproducibility and source layout|P0A’s 4 historical filename-hash bindings remain valid; explicit before/after two-pass check was 4/4 equal, `source_immutable_before_after: true`, and normalized current-tree basename hits 0. Root `pytest.ini` is canonical with no nested backend pytest config; `--collect-only -vv` reported repository rootdir/configfile, a targeted direct file passed 12 tests, and the full suite passed 172 (one non-blocking upstream Starlette/httpx deprecation warning). Accepted P0B importer and integration test remain byte-identical to `origin/main`; their accepted review was `APPROVE` (0H/0M), and controller dry-run evidence remains 38 templates/119 rows, discrepancy 0, DB write/apply 0, source unchanged.|accepted and verified by Hermes direct QA|
|Contract/API readiness|Committed JSON Schema/OpenAPI and generated-client drift checks passed; strict extra/required UUID/time/Decimal-string boundaries and typed API/worker readiness 503 exception tests passed. Final `make check` exited 0.|accepted and verified by Hermes direct QA|
|Static/security/migration|Final `make check` passed Ruff, strict mypy across 15 files, compileall, migration check, secret scan, sensitive-document scan, and Compose config. Ruff/mypy retain only the stated byte-identity preservation exclusions for accepted P0B content.|accepted and verified by Hermes direct QA|
|Frontend and disposable runtime|Corepack `pnpm` runs from frontend cwd and selects pinned pnpm `10.13.1`; frozen install, lint, `next typegen`, `tsc --noEmit --incremental false`, Vitest (1), production build, and client drift all passed with unchanged lockfile and no `tsconfig.tsbuildinfo`. Final disposable Compose exact-candidate process `proc_7e03db110d2f` exited 0: PostgreSQL/Redis/API/worker/web healthy, API live/ready and web HTTP 200 expected JSON, PostgreSQL migration roundtrip, and cleanup passed. PostgreSQL remains `tmpfs`, PostgreSQL/Redis remain unpublished, and API/web remain loopback-only.|accepted and verified by Hermes direct QA|

## FE8 frontend fixture workflow verification trace

|Fixture control|Actual 2026-07-31 evidence|Scope / gate|
|---|---|---|
|Eight deterministic flows|Queue; receipt/canonical LOT; document-candidate explicit finalization; section-allocation matching; internal testing; submit preflight; LEAD review; and LOT/audit timeline are implemented. UI review completed a fresh document/matching/internal/preflight/submit/LEAD flow on standalone BUILD_ID `yxIU8dalJEwMZG9Hg5YIz` and reported `APPROVE` (HIGH/MEDIUM/LOW 0).|Fixture UI verified only; not P2/P3 backend/domain completion|
|Numeric, confirmation, and fail-closed behavior|Business values use Decimal strings and `BigInt`, never binary floating point; document candidates require explicit manual confirmation. Guards deny missing/blank evidence and reasons, wrong source status/role, receipt/allocation LOT/quantity/unit or spec-profile/version inconsistencies, invalid or missing thresholds, unconfirmed internal results, relationship/trace drift, and submitted mutations. Qualitative values allow only `적합`/`부적합`; blank rows remain held.|Fixture reducer contract, not a production decision engine|
|Reducer-only approval state|The snapshot builder is private/non-exported. Its exact entire `internalTests` contract requires cardinality, IDs, item/unit, spec ID, required flag, and all HYC/supplier bounds to match; it serializes explicit `null` thresholds and recursively freezes the value-complete local snapshot. Source review was `APPROVE` (BLOCKER/MAJOR/MINOR 0), with 31 focused tests and a 14-attack external probe passing.|Local reducer demo only; no DB snapshot/audit/RBAC/idempotency claim|
|UI lock and responsive evidence|At `SUBMITTED`, receipt 8/8, document 12/12, matching 1/1, internal 8/8, and submission 2/2 controls were disabled; after `APPROVED`, team review 6/6 was also disabled, with canonical LOT/spec and exact reasons read from the frozen summary. A true 390×844 viewport had inner/document/body width 390 and no page-level overflow.|Fixture UI verified only; role switching is simulation, not real authentication/authorization|
|Controller, fresh-main integration, and delivery gates|Before and after documentation sync, and again in a fresh isolated Orca integration worktree, `make bootstrap && make check` exited 0: backend pytest 172 passed (one upstream Starlette/httpx deprecation warning), Ruff, strict mypy 15 files, compileall, generated-client drift, migrations, secret/sensitive scans, Compose config, frozen pnpm install, ESLint, next typegen, artifact-free tsc, frontend Vitest 3 files/32 tests, production build, and protected P0B byte identity. Feature commit `e79f00ca367bb43d3c0d370d228b9dad0e57e99c` fast-forwarded from fresh base `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5`; integration standalone BUILD_ID `U9jrUNlnVYwIknPKm1GwF` returned root/health HTTP 200, desktop and true 390×844 QA passed without page overflow, and the integration active probe passed 32 asserted results. Push-time remote-base/merge-base checks and post-push remote equality/ancestry verification passed.|Delivered to `origin/main`; fixture-only/product boundaries unchanged|

The reviewed source-only 10-file manifest before these documentation edits was `5b7f222fa5bba991499c3be4e8b49231fba59bb66b1b50dcc1e43ed29ddb6335`, at `HEAD`/base/`origin/main` `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5` and status digest `754834d90ae0c30075a0e611383abc9f99e6c157d335c7e6ddcd6ff8cb569692`; grammar is sorted path + NUL + hex SHA-256(file) + newline. Earlier candidate manifests `6b79...`, `4447...`, `0797...`, `987956...`, `b96da...`, and `97c508...` are superseded and are not final evidence. This record deliberately does not identify the pre-doc manifest as a docs-inclusive final manifest.

## P2 accepted source-gate verification trace

|P2 control|Accepted implementation / actual evidence|Current gate|
|---|---|---|
|P2.1–P2.2 Decimal, unit, master/spec|Fixed-point boundaries reject float, negative zero, non-finite, and ambiguous forms. Versioned 96-digit local Decimal context pins precision/rounding/traps; conversion and averaged-sample pre-round/result/version evidence is global-context independent. Receipt-lot allocation carries nullable model scope; repository and PostgreSQL choose the unique most-specific material/supplier/model ACTIVE/effective spec, preserve nullable fallback, exclude cross-model scope, and fail closed on equal-specificity ambiguity or overlap. DRAFT finalization denial and empty-autogenerate-diff migration gating remain enforced.|Accepted at P2 source gate|
|P2.3–P2.5 LOT, receipt/allocation, documents, results|AP-03 v1 identity is exactly supplier+material+NFKC/trim LOT No.; production/package data is conflict evidence. Provisional promotion, bounded merged-survivor re-entry, distinct LEAD+ADMIN audited master-data merge, merged-allocation denial, strict Decimal persistence, lowercase-hex hashes, positive quantity/page ranges, policy/status/data-type allowlists, supplier/HYC/internal separation, and sample XOR are covered.|Accepted at P2 source gate|
|P2.6–P2.8 judgment, workflow, approval/idempotency|The ordered engine explicitly retains `ON_HOLD > REJECTED > ACCEPTED`; `BOTH_ALL_MUST_PASS` never degrades on missing supplier evidence. All 15 case states are reachable without DRAFT bypass and INTERNAL_TEST_PENDING blocks review. Document transitions use a stable tuple and unique full current+target+role keys. Finalization accepts no caller candidate/snapshot/re-evaluation flag, and Alembic `20260801_0003` adds a DB backstop requiring every new case to have null `final_decision`; frozen `20260731_0002` is unchanged. The repository reloads persisted inputs, derives the engine candidate, permits plain `ACCEPTED` only for an `ACCEPTED` candidate, requires reasoned `SPECIAL_ACCEPTED` for a `REJECTED` or `ON_HOLD` accepting override, enforces LEAD-only separated approval, constructs/verifies the value-complete hashed snapshot, then atomically writes approval/audit/outbox with expected-version protection. ADMIN remains master-data-only for LOT merge. N-M3 remains accepted follow-up, not fixed: a broadly privileged DB-direct app-role writer can create an unfinalized row already at `LEAD_REVIEW` and finalize it with complete valid evidence, bypassing intermediate status history; decision integrity, mandatory evidence, and finalized-row immutability still hold. Revisit before production DB-role activation.|Accepted at P2 source gate; N-M3 pre-production follow-up|
|Portable/full regression|After N-M1/N-M2 hardening, `make check` exited 0: Ruff with E501 enabled, strict mypy 29 files, backend `346 passed, 10 PostgreSQL deselected`, compileall, migration contract `4 passed`, secret/sensitive scans, Compose rendering, and unchanged FE8 frontend lint/type/build/Vitest `32 passed`. Earlier 344/9/28 values remain historical and are superseded.|Accepted source-gate evidence|
|PostgreSQL runtime|The final-minor-hardened `run_p2_postgres_tests.sh` exited 0 with 10 owner/app-role/concurrency/trigger tests, including direct finalized-INSERT denial/rollback, normal unfinalized-INSERT success, atomic denial of reasoned `ON_HOLD → ACCEPTED`, realistic privilege/denial probes, upgrade→downgrade→upgrade, empty autogenerate drift, and empty unique Compose resource inventory after teardown.|Accepted source-gate evidence|
|Post-integration closure|Under separate explicit user authorization, P2 is complete, accepted, committed, fresh-main integrated, and delivered to `origin/main`: source commit `996056b` and first integration-documentation commit `58e963c` were delivered from baseline `1e96836`. `58e963c` is verified first-push/integration evidence and a durable ancestor; this post-push docs reconciliation is a later descendant, and Git history is authoritative for the live tip. Fresh `make bootstrap` and `make check` exited 0: backend `346 passed, 10 PostgreSQL deselected`, strict mypy 29, migration contract 4, FE8 frontend 32 plus lint/typecheck/build, scans/Compose; disposable PostgreSQL 10 passed and cleanup was verified.|Delivered to `origin/main`; Git history authoritative for live tip|
|Protected P0B boundary|Importer SHA-256 `61caebd0...e23` and dry-run test SHA-256 `c0799b04...801` remain byte-identical to `origin/main`; no real source content or external OCR/AI was used.|Preserved|

## P3 accepted source and delivery verification trace

|P3 control|Actual 2026-08-01 accepted evidence|Current gate|
|---|---|---|
|Synthetic vertical slice|Calcium-chloride-bead fixture intake, canonical LOT/allocation, checksum-deduplicated document, persisted extraction review with NUMERIC confidence, specification snapshot, fail-closed internal-test hold, inspector submission, separated LEAD approval, revision/retest lineage, immutable finalized evidence, and split-LOT trace are implemented through PostgreSQL-backed FastAPI routes and the API-backed Next.js workspace.|Source accepted|
|Approval and API defenses|Separate actors and RBAC deny inspector/ADMIN approval; `If-Match` stale versions return 409; approval re-evaluation, approval, decision snapshot, audit, outbox, and completed idempotency response commit atomically. Every supplier/internal/sample I/U/D trigger locks deterministic old/new parent cases before testing `final_decision`, serializing with approval's case lock. Extraction-run, field-review, document-section, and allocation-link I/U/D/reparent guards lock deterministic old/new authoritative runs before testing `CONFIRMED`; one confirmed run per document and one confirmed allocation per section are DB-enforced, while the legitimate transactional `REVIEW_REQUIRED → CONFIRMED` path remains. Missing-row idempotency exact-constraint savepoints, typed upload 422/413 cleanup, internal-results replace/clear, eligibility rollback, mutation-free GET, and unknown-integrity re-raise remain. Focused direct app-role tests prove failed confirmation rollback and deny confirmed review rewrites and cross-LOT link rebinds.|Source accepted; N-1/N-2/N-5 retained as fixture-only debt|
|Authoritative workflow status UI|Once an inspection exists, both the prominent badge and polite live region derive from the server inspection status and retain an unambiguous localized label plus code (`승인 완료 · ACCEPTED`) after approval and LOT trace. Before inspection creation the badge explicitly says it is pre-creation guidance. Real Playwright and separate live-stack smoke verify no stale `검토 필요`, visible controls, and no page overflow on desktop or 375×812.|Source accepted|
|Final independent backend review|`PASS`, blocker/major/medium 0: P3 PostgreSQL 67; mutation-first reverse-order probe 6 cycles; terminal-first focused 27; P2 regression 10; substantive gates backend 346 passed/77 PostgreSQL deselected, strict mypy 39, frontend 32, migration 4.|Independent source review passed|
|Final independent UI/API review|`PASS`: real `make p3-e2e` Playwright 3/3; separate real live-stack HTTP/browser smoke on desktop and 375×812; expected concurrent status pairs 201+409 intake, 201+409 inspection, and 200+409 approval; byte-identical sequential replay; invalid upload 422/413 with no residue; P3 API 67; unchanged repository fingerprint and cleanup 0/0/0/0.|Independent source review passed|
|Hermes controller QA|`make bootstrap && make check` passed Ruff, strict mypy 39, backend 346/77 deselected, frontend Vitest 32 plus Next build, migration 4, scans, and Compose. P2 PostgreSQL 10, P3 PostgreSQL 67, real Playwright 3, and targeted `test_db_serialization.py` 27 tests across three fresh cycles (81 total) passed. The frozen pre-doc candidate hash remained unchanged; Docker HYC containers/networks/volumes were 0/0/0 and only user-owned n8n remained running and untouched.|Accepted at P3 source gate|
|Candidate/Git evidence|Historical pre-integration freeze: base HEAD `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`; 50 changed/untracked files; source hash `51f3bbb1d23970484813e893e51fd781f89fb781d02fac2db5cb475b00cac7f2`, which was not a post-doc hash. Final source commit `91465f0413d0c0ca2633577078ec1300a6096442` (`feat: complete P3 vertical slice`) contains exactly 52 files, 8911 insertions, and 119 deletions. Clean local main and `origin/main` both began at the baseline; `git merge --ff-only 91465f0...` advanced main without merge commit/rebase. Fresh integrated bootstrap/check, Ruff, mypy 39, backend 346/77, frontend 32/build, migration 4, scans/Compose, P2/P3 PostgreSQL 10/67, and Playwright 3/3 passed; HYC cleanup was 0/0/0 and n8n untouched. Push `b7bc4a8..91465f0 main -> main` succeeded. Post-fetch local main, `origin/main`, and remote main all equal the full source commit; base/source are ancestors of `origin/main`; main/candidate worktrees were clean immediately before this docs-only reconciliation.|Committed, fresh-main fast-forward integrated, delivered to `origin/main`; Git history authoritative|
|Boundary|Only synthetic fixtures were used. No real PDF/XLS/XLSX, external OCR/AI/NAS/Drive/ERP, production DB-role activation, non-disposable DB, public exposure, deployment, release, or prohibited Git operation occurred. This row is P3 historical closure evidence; the later P4-A synthetic-only source acceptance below does not alter its P3 facts. P2 N-M3 remains accepted and unfixed.|Preserved; not production-ready|

## P4-A Offline/Synthetic remediation verification trace

Authoritative plan/evidence: [`docs/plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md`](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md). 아래 `Verified`는 generated non-sensitive offline/synthetic evaluator 범위에만 적용된다. 실제 대표 코퍼스/OCR/Provider 품질, P4-B, P4-C, full P4 또는 P5를 검증했다는 뜻이 아니다.

|Requirement/control|P4 lane / owner|Actual P4-A evidence|Current gate|
|---|---|---|---|
|AT-001 COA parsing|P4-A WORKER/QUALITY; P4-B QUALITY|Synthetic golden preserves supplier/product/LOT/row/spec/result/page/polygon and low-confidence/reference-only semantics. Accepted report includes exact field 35/44, page mismatch 1, non-unit IoU 1. Real representative corpus remains absent.|P4-A synthetic verified; P4-B blocked|
|AT-004 variable samples|P4-A WORKER/QUALITY|Strict sample identity/value/raw/source order and cardinality binding; duplicate/unmapped/value-mismatch and fixed-shape loss paths fail closed.|P4-A synthetic verified|
|FR-OCR-001 accuracy-first pipeline|P4-A WORKER|Deterministic 8-stage synthetic runner, exact stage/error compatibility, fail-closed upstream `SKIPPED`, candidate-observed warnings, canonical warning/error order, exhaustive rejection of non-empty warnings when extraction is non-successful, and no warnings on failed/skipped stages.|P4-A accepted/delivered synthetic scope; no real OCR claim|
|FR-OCR-002 Provider abstraction|P4-A WORKER/API; P4-C|Existing synthetic-only `ExtractionProvider` seam preserved; independent candidate payloads are stored and runtime does not copy golden answer keys. Contract/client drift passed.|P4-A seam verified; external Provider blocked|
|FR-OCR-003 structured output/provenance|P4-A WORKER/API|Strict/versioned golden, fixture, stage, candidate, report, output schemas; canonical JSON and Decimal/SHA-256 dataset→stage→candidate→report→output exact binding, cardinality, and order.|P4-A synthetic verified|
|FR-OCR-004 handwriting|P4-A WORKER/QUALITY|20-edge matrix binds handwriting to candidate/reference-only behavior and prevents business-field promotion.|P4-A synthetic verified|
|FR-OCR-005 confidence/Human Review|P4-A WORKER/QUALITY|Disjoint executable `CANDIDATE_ONLY`/`REVIEW_REQUIRED`/`MANUAL_FALLBACK`/`STABLE_FAILURE` dispositions with exact reason codes; low-confidence/missing/unsupported paths do not auto-finalize.|P4-A synthetic verified; QUALITY KPI threshold unapproved|
|FR-OCR-006 logic validation|P4-A DOMAIN/WORKER|Duplicate, unmapped, unapproved normalization, value mismatch, warning ordering, and all 20 edge dispositions are executable and fail closed; no automatic correction.|P4-A synthetic verified|
|Metrics and geometry|P4-A WORKER/QUALITY|Exact/normalized, row precision/recall, missing confusion, by-kind, page and polygon Decimal IoU metrics use precision 28 / `ROUND_HALF_EVEN` in schema validation and scoring. Public missing/invalid polygon counts remain Literal-zero compatible under strict required geometry; dead internal counters are removed. `PAGE_MISMATCH` has no IoU, no invented threshold; invalid geometry fails closed.|P4-A accepted/delivered synthetic scope; former source-quality notes closed; acceptance threshold remains QUALITY decision|
|Commands and reproducibility|P4-A WORKER/HERMES-QA|Maintenance focused 9; golden 192; Ruff; backend 510/77, strict mypy 49/0, compileall; full check exit 0 with frontend Vitest 32/build, migration 4, scans/Compose. Benchmark repeated twice with output/report/fixture `354d7c10…bfd23` / `7b0601d2…8933` / `05f77739…18d0` unchanged.|Final maintenance controller QA passed; independent `ACCEPT` 0/0/0|
|Candidate/Git boundary|P4-A HERMES-QA|Original source/integration baseline `aeedceb…`; documentation ancestors `1d98e4c…`/`afe58a0…`; exact four-path maintenance digest `7ed91a67…a85ce` unchanged before/after; `cad1ab4…` directly descends from `afe58a0…`. Fresh `origin/main` fast-forward/non-force delivery succeeded; capture-time local integration HEAD/`origin/main`/remote equality, ancestry, and clean status passed. Later docs-only tip comes from Git history.|Complete/accepted/delivered; original baseline and maintenance delivery distinguished|
|P4 preflight contracts|P4-A/P4-B/P4-C WORKER/QUALITY/HERMES-QA|Fail-closed offline/local preflight source/delivery `fce19681…`; Agy/Gemini `ACCEPT` 0/0/0; preflight 97, golden 192, Ruff, strict mypy 52/0, backend 607/77, frontend 32/build, migration 4, scans/Compose. Fresh ff-only/non-force delivery and capture-time remote equality passed.|Accepted/delivered contract evidence; grants no P4-B/P4-C approval|
|Local corpus eligibility preflight|P4-B QUALITY|Private inventory aggregate is 4 candidate documents and 0 eligible because human-label and independent-review evidence are absent. No filename/path/hash/body recorded.|Non-representative; not a QUALITY corpus; `BLOCKED_QUALITY_CORPUS_APPROVAL`|
|Provider due diligence|P4-C OPS/QUALITY/HERMES-QA|[2026-08-02 official-source research](research/2026-08-02-p4c-ocr-provider-due-diligence.md) compares Azure, NAVER, and Google; Azure `prebuilt-layout` / REST `2024-11-30` / Korea Central is first research candidate only. Account/contract/payload/credential/budget/P4-B intersection/approver remain `PENDING`.|Research only; not selected/approved; no external call|
|P4-B / P4-C gates|QUALITY / AP-02 approvers|No real corpus representativeness/de-identification evidence and no Provider-specific opt-in. No real corpus, Provider, credential, network, DB/migration/API/frontend/service change, or deployment occurred.|P4-B and P4-C independently blocked|
|AP-02 external-provider gate|P4-C OPS/QUALITY/HERMES-QA|One complete [`P4-C Provider-specific AP-02 packet`](approvals/P4C_PROVIDER_AP02_DECISION_PACKET.md) per Provider; public research prefill is non-approval and generic/cross-provider approval is forbidden|`BLOCKED_AP02_PROVIDER_OPT_IN`; `PENDING / NOT APPROVED`|
|QUALITY corpus representativeness|P4-B QUALITY|Complete [`P4-B QUALITY corpus packet`](approvals/P4B_QUALITY_CORPUS_DECISION_PACKET.md), including manifest/classification/de-identification/representativeness/custody/absence/retention/destination/exclusions/named approval|`BLOCKED_QUALITY_CORPUS_APPROVAL`; `PENDING / NOT APPROVED`|
|Metric contract|P4-A WORKER/QUALITY|Separate exact/normalized, row precision/recall, missing confusion, by-kind, page/polygon Decimal IoU; denominator/ignored/duplicate/normalization rules; canonical report digest|P4-A synthetic Verified; no acceptance threshold approved|
|P4-A historical minor closure|P4-A WORKER/QUALITY|Original review's schema Decimal-context and dead internal counter notes were closed by `cad1ab4…`; maintenance review returned `ACCEPT` 0/0/0. Strict required geometry and fail-closed semantics remain.|Closed P4-A maintenance hygiene; not P4-B/P4-C/full-P4 completion|
|P4-A commands|P4-A WORKER/HERMES-QA|Maintenance focused 9; `make p4-golden-check` 192; Ruff/mypy 49/backend 510/77/compileall; full check, frontend 32/build, migration 4, scans/Compose; two unchanged benchmark runs.|Final maintenance controller QA and independent acceptance passed; delivered|

P4-A CI는 generated non-sensitive synthetic fixture, fixture provider, stable clock/ordering만 사용하며 network/external credential이 없다. P4-B/P4-C의 `PENDING` packet field는 approval로 계산하지 않는다. QUALITY가 geometry/KPI threshold를 승인하기 전에는 임의 acceptance threshold를 만들지 않는다. KPI 미달/부재는 Human Review와 manual fallback을 늘리며 auto-finalization을 허용하지 않는다.

## 1. 기능 요구사항 전수 추적

|Requirement|요약|Phase|Owner|대표 Planned 검증|승인/Gate|
|---|---|---:|---|---|---|
|FR-MST-001|품목 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_material_master.py`; `frontend/tests/e2e/master-data.spec.ts`|AP-04, P5|
|FR-MST-002|공급업체 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_supplier_master.py`|AP-04, P5|
|FR-MST-003|모델 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_model_master.py`|P5|
|FR-MST-004|품목-공급사-모델 매핑|P2/P5|DATA/API|`backend/tests/integration/db/test_supplier_material_model_scope.py`|P2|
|FR-MST-005|nullable 코드/후속 업데이트|P2/P5|DATA/API|`backend/tests/integration/db/test_nullable_code_uniqueness.py`; import dry-run|P5|
|FR-MST-006|BOM 확장 준비|P2|DATA/API|`backend/tests/contract/test_erp_bom_seam.py`(feature OFF)|AP-08; 자동연계 비범위|
|FR-SPEC-001|공통/공급사/모델 기준 프로파일|P2|DOMAIN/DATA|`backend/tests/unit/specifications/test_spec_selection.py`; overlap DB test|AP-03, P2|
|FR-SPEC-002|Draft/Active 기준 버전·적용일|P2/P5|DOMAIN/DATA/API|`backend/tests/integration/db/test_spec_version_lifecycle.py`|P2/P5|
|FR-SPEC-003|표준 검사항목|P2/P5|DATA/API/QUALITY|seed replay + `test_standard_test_items.py`|QUALITY review|
|FR-SPEC-004|규격 operator/정성/사용자 정의|P2|DOMAIN/DATA|`backend/tests/unit/specifications/test_spec_expression.py`; operator CHECK|P2; custom은 MANUAL|
|FR-SPEC-005|결과 출처 정책|P2|DOMAIN|`backend/tests/unit/judgment/test_source_policy.py`|P2|
|FR-SPEC-006|COA 누락 정책|P2/P3|DOMAIN/API|`backend/tests/unit/judgment/test_missing_policy.py`; hold integration|P3|
|FR-SPEC-007|샘플 계산/판정 정책|P2/P5|DOMAIN/QUALITY|`backend/tests/unit/judgment/test_sample_policy.py`|항목 정책 QUALITY 승인|
|FR-INB-001|입고 생성·필드|P2/P3|DATA/API/WEB|`backend/tests/integration/api/test_inbound_receipt.py`; vertical slice|P3|
|FR-INB-002|임시저장·OCR/수기 교차검증|P3|API/WEB|`frontend/tests/e2e/cross-validation.spec.ts`|P3|
|FR-INB-003|LOT 관계 유연성|P2/P3|DOMAIN/DATA/API|`backend/tests/integration/db/test_material_lot_identity.py`; `test_split_lot_trace.py`|AP-03, P2|
|FR-DOC-001|NAS/Drive/수동 수집|P3/P6|WORKER/API|manual upload P3; source adapter contract P6|AP-01/02/06|
|FR-DOC-002|파일 안정화|P6|WORKER|`backend/tests/integration/workers/test_stabilizing_watcher.py`|P6|
|FR-DOC-003|원본 hash/불변/metadata|P2/P3|DATA/API/OPS|`backend/tests/integration/api/test_document_immutability.py`|AP-05, P3|
|FR-DOC-004|SHA-256 중복 탐지/재사용|P3|API/DATA|`backend/tests/integration/api/test_document_dedup.py`|P3|
|FR-DOC-005|Storage Adapter/Primary/Mirror|P1/P6|WORKER/OPS|P1 accepted port boundary; mirror failure test remains P6|AP-06, P6|
|FR-OCR-001|정확도 우선 파이프라인|P4/P5|WORKER/QUALITY|`backend/tests/golden/test_pipeline_regression.py`|AP-02, QUALITY benchmark|
|FR-OCR-002|Provider 추상화|P1/P4|WORKER|P1 accepted `backend/tests/contract/test_extraction_port.py`; provider use remains P4|P1 accepted/P4|
|FR-OCR-003|구조화 출력 schema/원문 위치|P1/P4|WORKER/API|P1 accepted JSON Schema/Pydantic contract + bbox validation; golden remains P4|P1 accepted/P4|
|FR-OCR-004|손글씨는 참고 메모|P4|WORKER/QUALITY|`test_handwriting_never_business_field.py`|P4|
|FR-OCR-005|confidence/Human Review|P3/P4|API/WEB/QUALITY|low-confidence hold + review E2E|P3/P4|
|FR-OCR-006|합계/범위/날짜/누락 논리 검증|P2/P4|DOMAIN/WORKER|`backend/tests/unit/judgment/test_logical_validation.py`; golden|P4|
|FR-MAP-001|표준 항목 별칭|P2/P5|DATA/API|`backend/tests/integration/api/test_alias_mapping.py`|P5|
|FR-MAP-002|mapping 상태|P2/P3|DOMAIN/API|unmapped excluded/hold tests|P3|
|FR-MAP-003|학습형 운영(승인 전 전역 금지)|P5|API/QUALITY|`test_alias_approval_scope.py`|QUALITY approval|
|FR-UNIT-001|단위 마스터/차원/공식 버전|P2|DOMAIN/DATA|`backend/tests/unit/judgment/test_unit_registry.py`|P2|
|FR-UNIT-002|자동 환산/차원 일치|P2/P3|DOMAIN|`backend/tests/unit/judgment/test_unit_conversion.py`|P2|
|FR-UNIT-003|원값/환산값/공식/반올림 기록|P2|DOMAIN/DATA|snapshot serialization test|P2|
|FR-JDG-001|판정 단계와 hold 우선순위|P2|DOMAIN|`backend/tests/unit/judgment/test_engine_pipeline.py`|P2|
|FR-JDG-002|공급사/HYC 기준 분리|P2/P3|DOMAIN/API/WEB|`test_supplier_vs_hyc_spec.py`; panel E2E|P3|
|FR-JDG-003|자체 검사 우선|P2/P3|DOMAIN|`backend/tests/unit/judgment/test_source_policy.py`|P2|
|FR-JDG-004|전체 후보/업무 최종상태|P2/P3/P5|DOMAIN/API|engine 3-state + workflow 5-state transition tests|P3/P5|
|FR-JDG-005|기준·근거 Snapshot 재현성|P2/P3|DOMAIN/DATA/API|`test_spec_snapshot_immutability.py`; canonical hash|P3|
|FR-INT-001|자체검사 대상 표시|P3/P5|DOMAIN/WEB|hold integration + panel E2E|P3|
|FR-INT-002|자체검사 입력 필드|P3/P5|API/WEB|`test_internal_results_api.py`|P3/P5|
|FR-INT-003|가변 샘플|P2/P4/P5|DOMAIN/DATA/WEB|sample property + package golden + E2E|P5|
|FR-INT-004|임시저장|P3|API/WEB|versioned autosave/conflict E2E|P3|
|FR-INT-005|계산값|P2/P3|DOMAIN|sample aggregate tests|P2|
|FR-INT-006|사진/시험기록 증빙|P5|API/WEB/OPS|attachment validation/audit E2E|P5|
|FR-APR-001|검사자 제출 검증|P2/P3|DOMAIN/API|`test_submit_guards.py`|P3|
|FR-APR-002|팀장 검토/승인·역할분리|P2/P3|API/WEB|`test_rbac_approval.py`; E2E|AP-04, P3|
|FR-APR-003|반려/사유/재제출|P2/P5|DOMAIN/API/WEB|transition + return/resubmit E2E|P5|
|FR-APR-004|확정 불변/Snapshot/정정 revision|P2/P3|DATA/API|`test_approval_atomicity.py`; DB mutation denial|P3|
|FR-NCR-001|처리방안|P5|DOMAIN/API/WEB|`test_nonconformance_disposition.py`|P5|
|FR-NCR-002|부적합 기록/승인/기한/증빙|P5|DATA/API/WEB|`frontend/tests/e2e/nonconformance.spec.ts`|P5|
|FR-NCR-003|재검사 연결|P2/P5|DOMAIN/DATA/API|`test_retest_vs_revision.py`|P5|
|FR-NCR-004|모듈 Feature Flag|P1/P5|API/WEB|`test_feature_flags.py`|P5; invariant guard는 비활성 불가|

## 2. 화면·매칭·데이터·API·보고서 정책 추적

|Policy ID|PRD 범위|Phase|Owner|대표 Planned 검증|Gate|
|---|---|---:|---|---|---|
|UI-001|§12.1 목록 컬럼·필터·통합검색|P5|API/WEB|`frontend/tests/e2e/inspection-list-filter.spec.ts`; API query tests|NFR-PERF|
|UI-002|§12.2 좌우 상세·원문/bbox·자체검사·경고|P3/P5|WEB/API|vertical slice + `inspection-detail.spec.ts`|P3/P5|
|UI-003|§12.3 OCR 검토 단축키/저신뢰/체크리스트|P3/P5|WEB|`ocr-review-accessibility.spec.ts`|P5|
|UI-004|§12.4 기준 비교/편집/Draft→활성/Import|P5|WEB/API/QUALITY|`spec-version-management.spec.ts`|QUALITY 승인|
|UI-005|§12.5 승인건 통계·테스트/취소 제외|P5|API/WEB|`test_quality_stats_snapshot_only.py`|P5|
|MATCH-001|§13.1 우선순위|P2/P3|DOMAIN|`backend/tests/unit/documents/test_match_ranking.py`|AP-03|
|MATCH-002|§13.2 후보도 잠정, 핵심 충돌 자동금지, section 분리|P3/P4|DOMAIN/API/WEB|ambiguous/no-match/manual confirmation tests|P3/P4|
|MATCH-003|§13.3 상태·재연결 감사|P2/P3|DATA/API|`test_document_relink_audit.py`|P3|
|DATA-001|§14.1/14.2 관계·테이블|P2|DATA|migration schema snapshot/constraints|AP-03|
|DATA-002|§14.3 승인/기준/checksum/Decimal/FK/soft-delete/UTC|P2|DATA/DOMAIN|DB invariant suite|P2|
|DATA-003|canonical LOT 보정|P2|DATA/DOMAIN|identity conflict/merge/concurrency/re-entry tests|AP-03|
|API-001|§15.1 endpoint surface/OpenAPI|P1~P5|API|P1 accepted `backend/tests/contract/test_openapi_contract.py`, generated OpenAPI/client drift check|P1 accepted/P5|
|API-002|§15.2 upload/approve/report Idempotency-Key|P2/P3/P5|API/DATA|P3 `test_idempotency_races.py`: intake/inspection/approval missing-row same/different-payload concurrency, byte-stable replay, exact completed row and loser rollback; P5 report coverage remains|P3 accepted/P5|
|API-003|§15.2 RBAC/correlation/error/page/filter/sort/version/reason/size/Job ID|P1~P5|API|P1 accepted correlation/error envelope contract; remaining surface P2~P5|P1 accepted/P5|
|REP-001|§16.1 Raw 호환+Long+Documents+optional Audit, 무절단|P5|WORKER/QUALITY|`test_raw_excel_lossless.py`|QUALITY sample approval|
|REP-002|§16.2 승인 Snapshot 통합보고서·정정 버전|P5|WORKER/DATA|`test_integrated_report_from_snapshot.py`|P5|
|REP-003|§16.3 LOT trace·분할 입고·production link seam|P3/P5|API/WORKER|`test_split_lot_trace.py`; `test_production_lot_link_seam.py`|AP-08; 자동 ERP 비범위|
|REP-004|§16.4 월별/공급사 품질 통계|P5|API/WORKER|`test_supplier_quality_report.py`|P5|
|ARCH-001|§17.1 stack와 OCR/판정 분리|P1/P2|HERMES-QA|P1 accepted process/component health smoke; import-linter remains P2|P1 accepted/P2|
|ARCH-002|§17.2 API/DB/storage/queue/worker/ERP adapter|P1~P6|API/WORKER/OPS|contract/smoke/feature-off tests|P6|
|ARCH-003|§17.3 metadata vs immutable source/derived artifacts/mirror|P2/P6|DATA/WORKER/OPS|storage/mirror/lineage tests|AP-06, P6|

## 3. 보안·감사·보존/NFR 전수 추적

|Policy ID|PRD 요구|Phase|Owner|대표 Planned 검증|Gate|
|---|---|---:|---|---|---|
|SEC-001|§18.1 TLS, 안전 hash, 최소권한, secret, MIME/scan, 실행금지, AI 정책, download audit, session 제한|P1/P5/P6|API/OPS/HERMES-QA|threat-model checklist, upload attack fixtures, RBAC, secret scan, TLS config inspection|AP-01/02/04, production|
|AUD-001|§18.2 11개 감사 이벤트 군 전부|P2/P3/P5|DATA/API/HERMES-QA|`backend/tests/integration/db/test_audit_event_matrix.py`가 요구 event matrix 순회|P5|
|RET-001|§18.3 설정형 보존, 승인>=원본, audit 삭제 제한|P2/P6|DATA/OPS|retention policy/permission/expiry dry-run tests|AP-08|
|BACKUP-001|§18.3 DB 일일 백업, 파일 백업/이중화, 복원 문서, RPO/RTO 승인|P6|OPS/HERMES-QA|`scripts/backup.sh` + disposable `restore-verify.sh` row/hash manifest|AP-08, production|
|NFR-ACC|§19.1 deterministic, no LLM final, bbox, raw/normalized/final, parse fail review|P2~P5|DOMAIN/WORKER/WEB|domain/golden/E2E fail-closed suites|P3/P5|
|NFR-PERF|§19.2 list/detail 2s, 100k search 3s, upload receipt 3s, report async|P5/P6|API/DATA/OPS|`backend/tests/performance/test_query_targets.py`; dataset/load profile and environment recorded|Pilot; 실제 규모 후 조정|
|NFR-AVAIL|§19.3 OCR 장애 시 수기 흐름, retry/manual, DLQ, status|P3/P6|API/WORKER/OPS|OCR-off vertical slice; worker kill/retry/DLQ/status tests|P3/P6|
|NFR-EXT|§19.4 no-code config, provider/ERP adapters, unlimited item/sample, site/warehouse IDs|P1/P2/P5|DOMAIN/API/WORKER|config-driven alias/schema tests, large variable-sample property tests, feature-off ERP contract|P5|
|NFR-UX|§19.5 한국어, 색+텍스트, 숫자 즉시 오류, 상태 구분, 유실 방지|P3/P5|WEB|Playwright accessibility/keyboard/autosave/conflict tests|P5|
|OCR-BENCH-001|§20.1 provider 고정 전 representative golden와 10개 지표|P4|WORKER/QUALITY|P4-A versioned synthetic runner/metrics/report verified; P4-B 표본 대표성 QUALITY 승인 및 P4-C Provider별 AP-02는 별도|P4-A synthetic verified; P4-B/P4-C blocked|
|OCR-EDGE-001|§20.2 20개 edge case|P2~P5|DOMAIN/WORKER/API|P4-A executable 20-edge matrix with disjoint exact disposition/reason binding; real-corpus/provider behavior remains later gated|P4-A synthetic matrix verified; later scope blocked/planned|

## 4. API Idempotency 계약 정본

|Endpoint family|Scope/Request hash|Same key + same hash|Same key + different hash|보존|Planned test|
|---|---|---|---|---|---|
|`POST /documents/upload`|`principal_id + route + key`; streaming file SHA-256 + canonical metadata|기존 canonical document/job의 최초 status/body를 반환; 새 원본/작업 없음|`409 IDEMPOTENCY_KEY_REUSED`|업로드 업무/보존 정책 이상; 만료 후에도 checksum dedupe는 독립 유지|`backend/tests/integration/api/test_upload_idempotency.py`|
|`POST /inspection-cases/{id}/approve`|actor+case+key; case id, expected version, action, canonical reason/comment|기존 approval/snapshot 응답 반환; audit/approval 1건|409; final-state guard도 거부|approval/audit와 동일 기간, 임의 만료 금지|`backend/tests/integration/api/test_approval_idempotency.py`|
|`POST /reports/*`|actor+route+key; report kind, approved snapshot IDs, canonical filters, template version|동일 report job/resource 반환; worker 중복 없음|409|job/resource 보존기간 이상|`backend/tests/integration/api/test_report_idempotency.py`|

공통 `idempotency_records`에는 key, principal/scope, request hash, state(`PENDING/COMPLETED/FAILED_RETRYABLE`), status/body/resource, created/completed/expires를 저장한다. PENDING lease 회수와 crash recovery를 테스트한다. Generic TTL은 설정형이지만 승인 key는 approval/audit 보존보다 짧아질 수 없다.

## 5. Canonical LOT identity 계약 정본

- Pilot 기본 identity policy: `(supplier_id, material_id, normalized_supplier_lot_no)`. 생산일·입고일·수량·모델은 일치/충돌 증거이지 기본 key가 아니다. 이는 동일 공급사 LOT의 분할 입고를 하나로 조회하는 AT-013에 맞춘다.
- 원문 `supplier_lot_no_raw`는 불변 보존한다. 기본 normalization은 Unicode NFKC와 양끝 공백 제거만 적용하며 case·내부 구분자는 자동 변경하지 않는다. 공급사별 추가 normalization은 versioned policy와 QUALITY 승인 후에만 허용한다.
- 공급사가 LOT 번호를 재사용해 생산일 등 추가 구분자가 필요하다는 현업 근거가 있으면 AP-03에서 `lot_identity_policy`의 components를 버전 지정한다. 기존 identity를 조용히 재계산하지 않는다.
- `material_lots(supplier_id, material_id, identity_policy_version, identity_key)`에 `UNIQUE`; concurrent create는 transaction + unique conflict/upsert로 기존 canonical id를 반환한다.
- 필수 component가 누락되면 `PROVISIONAL`; 자동 병합·최종 판정에 사용하지 않고 `CONFLICT_REVIEW`로 보낸다.
- promotion/merge는 QUALITY Lead와 master-data ADMIN의 분리된 권한, expected version, 사유, advisory/row lock, 링크 이관 transaction, `merged_into_id`, append-only audit로 수행한다. 원 canonical row는 삭제하지 않는다.

Planned tests:

- `backend/tests/integration/db/test_material_lot_identity.py`
- `backend/tests/integration/db/test_concurrent_lot_creation.py`
- `backend/tests/integration/api/test_same_lot_reentry.py`
- `backend/tests/integration/api/test_provisional_lot_conflict.py`
- `backend/tests/integration/api/test_lot_merge_audit.py`
- `backend/tests/integration/api/test_split_lot_trace.py`

## 6. AT-001~AT-013 추적

|AT|Phase|대표 Planned 검증|Gate/보정|
|---|---:|---|---|
|AT-001 COA 파싱|P4/P5|`backend/tests/golden/{test_schema.py,test_artifacts_and_scoring.py,test_runner_stages_metrics_edges.py}`|P4-A synthetic schema/scoring/runner scope verified; real representative documents remain P4-B/P5|
|AT-002 공급사/HYC 규격 분리|P2/P3|`backend/tests/unit/judgment/test_supplier_vs_hyc_spec.py`|컬럼·판정 독립|
|AT-003 필수 누락 대체|P2/P3|`backend/tests/integration/api/test_internal_substitute_hold.py`|자체검사 전 hold/승인 차단|
|AT-004 가변 샘플|P4/P5|`backend/tests/golden/{test_schema.py,test_runner_stages_metrics_edges.py}`|P4-A synthetic identity/value/raw/order/cardinality binding verified; real corpus remains P4-B/P5|
|AT-005 입고 교차검증|P3|`frontend/tests/e2e/cross-validation.spec.ts`|원문/OCR/수기/final/사유|
|AT-006 단위 자동 변환|P2|`backend/tests/unit/judgment/test_unit_conversion.py`|dimension/formula version/Decimal/pre-round|
|AT-007 자체 결과 우선|P2/P3|`backend/tests/unit/judgment/test_source_policy.py`|internal effective, supplier 보존|
|AT-008 중복 문서|P3|`backend/tests/integration/api/{test_document_dedup.py,test_idempotency_races.py}`|checksum dedupe, empty 422/over-limit 413 cleanup, intake/inspection idempotency race/replay|
|AT-009 기준 버전 고정|P2/P3|`backend/tests/integration/db/test_spec_snapshot_immutability.py`|v2 활성 뒤 과거 v1 불변|
|AT-010 승인|P3|`backend/tests/integration/api/{test_approval_atomicity.py,test_idempotency_races.py}`|snapshot/approval/audit/outbox 원자성, first-reservation race 200+409, 중복 0, byte-stable replay|
|AT-011 부적합 처리|P5|`frontend/tests/e2e/nonconformance.spec.ts`|처리/승인/목표일/증빙/재검사|
|AT-012 Raw Data 출력|P5|`backend/tests/integration/{reports/test_raw_excel_lossless.py,api/test_report_idempotency.py}`|호환+Long·무손실·동일 job replay|
|AT-013 LOT 조회|P3/P5|`backend/tests/integration/api/{test_split_lot_trace.py,test_production_lot_link_seam.py}`|분할 입고/문서/검사/NCR + feature OFF production link 저장·조회·보고서 seam; ERP 자동 수집은 비범위|

## 7. Definition of Done 세부 추적

|DoD group|Phase|Verification owner/evidence|
|---|---:|---|
|Migration/Seed 재실행, 38 template Draft import|P1/P2/P5|DATA + HERMES-QA; disposable migration replay, importer dry-run/apply snapshot|
|입고/LOT·OCR/수기 교차검증·문서 M:N|P2/P3|API/WEB; vertical Slice + true LOT identity contracts|
|두 PDF 유형·저신뢰 Human Review·OCR golden|P4/P5|WORKER/QUALITY; approved corpus golden report|
|HYC 판정·자체검사·가변 sample|P2~P5|DOMAIN/API/WEB; property/integration/E2E|
|검사자→팀장·5 workflow 결과·NCR|P3/P5|API/WEB/QUALITY; role/state/NCR E2E|
|원본 불변/hash·감사·승인 직접수정 차단|P2/P3|DATA/API/HERMES-QA; app+DB denial tests|
|Raw/통합/LOT/통계 4종 출력|P5|WORKER/QUALITY; snapshot fixture, no-truncation, production-link seam|
|Unit/Integration/E2E/OpenAPI/Golden|P1부터 누적|HERMES-QA가 실제 명령과 exit code 재검증|
|설치/운영/백업/복구·관리자/품질팀 가이드|P6|OPS/QUALITY; clean install + restore rehearsal + tabletop|
|외부 Secret 0|모든 Phase|secret scan + config review|

## 8. 승인 상태

현재 매트릭스는 P0A/P0B/P1/P2/P3, P4-A/preflight, 그리고 source baseline `91fd4a8…`의 local-only OCR accepted/delivered evidence를 보존한다. Pre-closure `96413d2…`와 이후 closure/live tip은 Git history로 확인한다. Active local-only P4 engineering은 complete다. P4-B는 4 candidate/0 eligible인 현재 inventory로는 `BLOCKED_QUALITY_CORPUS_APPROVAL`이며 real-corpus validation을 원할 때만 해제할 future QUALITY gate이지 code debt가 아니다. P4-C는 deferred Provider-specific opt-in이고 local-only scope에 필요하지 않으며 active account request가 없다. P5 is unstarted and not authorized. Linked packet templates remain `PENDING / NOT APPROVED`. Representative-corpus quality/accuracy, full P4/P5, 실데이터 apply/import, external Provider/OCR/AI/NAS/Drive/ERP, 비일회성/production DB, production DB-role activation, release/production readiness는 계속 미승인이다. Public Vercel demo는 synthetic frontend-only이며 live deployment identity/behavior는 deployment API/browser evidence가 정본이다.
