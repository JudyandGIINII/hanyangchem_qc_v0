# P4 local-only OCR accepted delivery handoff

## 2026-08-03 active handoff

- The authorized local-only low-quality PDF OCR engineering lane is complete, independently accepted, committed, fresh-`origin/main` fast-forward integrated, and delivered. Source/integration baseline is `91fd4a8229b12d2b229f2ef9abb9dceef93591b5` (`feat: add local-only low-quality PDF OCR`). Pre-closure main baseline `96413d20230b62033ecb754a12e5a1a621a7b95c` is its later descendant; the commit containing this documentation closure will be newer, and Git history is authoritative for its exact SHA/remote-tip state.
- All OCR output is a candidate with `review_required=true`; missing/low-confidence/conflicting/table-layout results fail closed. Runtime network, credentials, endpoints, model auto-download, external Provider fallback, and automatic final decisions are prohibited.
- Final post-remediation generated-synthetic PaddleOCR smoke passed with output digest `581ed7dad0973c3a999ce6e1b48bc9368452e5f6f9aab3fdc3e8c1fbe72437c1`, aggregate digest `6545119c4a18c2e788024521a3e77fbdd38b4fc902a01900063d79327b1c6a9c`, field/physical-line header/numeric/public-provider review exposure `1.0000/1.0000/1.0000`, and initialization/prediction network attempts `0/0`.
- Final independent Claude review returned `ACCEPT_WITH_MINOR` at BLOCKER/MAJOR/MINOR/NOTE `0/0/4/8`. It confirmed B1/M1-M9 and MA-1 closed. The four bounded minors remain: broad/over-inclusive native table detection; native low-confidence evaluator wiring exercised only through a fake backend because production native lines are confidence 1.00; no expensive smoke rerun inside the independent review after final native remediation, although the later Hermes final-source run produced the digests above; and duplicate native word extraction per native page.
- Final-tree evidence: backend `641 passed, 92 deselected`, strict mypy 67, frontend Vitest 32/build, P4 golden 198, P4 preflight 97, local preflight focused/runtime 43 plus real engine initialization, migration 4, contracts, scans, and Compose passed. Final `make check` exited 0 after documentation sync.
- Readiness failure caching is fail-closed and restart-required. Ordinary CI deliberately does not require model binaries; exact local runtime/model validation remains a separate mandatory `make p4-local-ocr-preflight` gate.
- Active local-only P4 engineering is complete. If representative real-corpus validation is desired, the next boundary is P4-B QUALITY corpus approval and missing human-label/independent-review evidence; this is a validation gate, not code debt. Otherwise the work may hand off to the next separately approved phase. P4-C external Provider work is deferred/not required for local-only scope; no account or approval request is active.
- Public synthetic-demo remediation `96413d2…` preserves local API behavior when `NEXT_PUBLIC_HYC_PUBLIC_DEMO` is absent and blocks backend calls/server persistence when it is exactly `1`. Its independent review was `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 6): a static approval assertion is vacuous; no runtime fetch-spy/effect coverage exists; source-slicing tests are formatting-brittle; public status copy can remain server-oriented; no committed `vercel.json`/`.vercelignore` pins the flag or Root Directory; and root `.env.example` does not feed the Compose web image build. These residuals are not fixed. Controller frontend verification was 36 passed plus build. Verified 2026-08-03 KST production evidence is Vercel `hanyangchem_qc` deployment `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y`, `READY` at `https://hanyangchem-739r15g9t-judy-ng-ii-nii-s-projects.vercel.app` with alias `https://hanyangchemqc.vercel.app` and `sourceCommit=cf6d6327172fb09da0fe0e3b12159f6596553c41`. Next.js 15.5.22 completed compile/lint/type validity, five static routes and `/api/health` in 57s; root HTTP 200 and health `{"status":"ready"}` passed. Alias browser QA found the public boundary/title, no `Failed to fetch`, no localhost resources, alias-only resources, zero console messages/errors, and only local synthetic approval on team-lead interaction. Production/Preview flags are saved. This proves only that exact synthetic frontend boundary; backend, DB, worker, OCR, models, and original documents remain local/intranet-only. Future missing/incorrect flag/configuration can still fall back to localhost-fetch mode and must repeat deployment-API/browser verification. The later documentation commit is docs-only with `frontend/` unchanged from `cf6d632…`, so no rebuild is required solely for unchanged frontend bytes; Git history is authoritative for its tip. The reviewer ran Vitest 36, `tsc`, and `eslint`, not a build or Playwright.
- The complete design, evidence, limitations, setup distinction, and prohibitions are in [`research/2026-08-03-local-only-low-quality-pdf-ocr.md`](research/2026-08-03-local-only-low-quality-pdf-ocr.md).

The historical accepted/delivered P4-A and preflight record below remains authoritative for those increments. This local-only delivery does not grant P4-B/P4-C, representative-corpus quality, external Provider, deployment, or production approval.

## 현재 handoff

- Authoritative P4 plan and acceptance record: [`plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md`](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).
- P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442` remains accepted, fresh-main fast-forward integrated, and delivered to `origin/main`.
- P4-A Offline/Synthetic is complete, independently accepted, committed, fresh-main fast-forward integrated, and delivered to `origin/main` at source/integration baseline `aeedceb2c3b7008439a9c72e3984be77f6135e51` (`feat: complete P4-A offline synthetic evaluator`). That commit is a direct descendant of `2d5c02dbc612f9b612f27a36263b95e842c24e75`.
- Final controller QA passed. The fresh independent read-only review of the final 25-path candidate returned `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 3); it recomputed unchanged before/after-review digests for the 16-path source-only set (`0d5c259f59293f35e4cf6b83ffff13820c3c07194f5db48e54d8c8b1d09db632`) and 25-path full candidate (`ba938518beca8f3718abdf4eb44430e26b3a775aea8f8b33dc5dc01937218f23`). The latter is capture-time accepted-candidate evidence, not the digest of the commit containing this nine-file closure.
- A fresh Orca integration worktree was created from fetched `origin/main` at baseline `2d5c02d…`. `git merge --ff-only aeedceb…` succeeded without a merge commit or rebase; non-force `git push origin HEAD:main` succeeded. At capture time integration HEAD, `origin/main`, and `git ls-remote origin refs/heads/main` all equaled `aeedceb…`; baseline/source ancestry and clean implementation/integration worktrees were verified.
- The commit containing this nine-file documentation closure is a newer descendant of `aeedceb…`; Git history is authoritative for its exact SHA and remote-tip status. `aeedceb…` remains the P4-A source/integration baseline, not the continuing tip.
- Post-integration documentation commits `1d98e4cf17b37e0ea95eadcbe69418778d1a614f` and `afe58a0fe556e8ae94b11926dd572ef9b2e60ee5` are historical ancestors after `aeedceb…`.
- The pre-P4-B four-path maintenance increment was independently accepted with final `VERDICT: ACCEPT` (blocker 0, major 0, minor 0). Its exact review-freeze digest remained `7ed91a678ba1dd72c30f7e9b58d5e5066fdcf41f8cde2b9da8239447345a85ce` before and after review.
- Maintenance source/delivery commit `cad1ab48b7ab1923638fe8600f23ef640efdab73` (`fix: stabilize P4-A geometry validation`) is the direct child of `afe58a0…`. A fresh `origin/main` fast-forward and non-force delivery succeeded. At capture time local integration HEAD, `origin/main`, and `git ls-remote` main all equaled `cad1ab4…`; ancestry and clean integration status passed. Git history is authoritative for the exact SHA and remote-tip state of any later documentation-only descendant.
- The maintenance closes the former schema Decimal-context and dead internal polygon-counter notes. Polygon validation arithmetic is pinned to precision 28 / `ROUND_HALF_EVEN`; public `missing_polygon_count` and `invalid_polygon_count` remain Literal-zero compatible. Strict required geometry and fail-closed invalid-geometry behavior remain unchanged.
- Fail-closed P4 preflight source/delivery commit `fce19681f75cac8f95bb6cde95ad50351cf9e309` (`feat: add fail-closed P4 preflight contracts`) directly descends from fresh `origin/main` baseline `4866f7a992cd8e40dc95b43b1b2adaa13d989752`. Independent Agy/Gemini reviews returned `ACCEPT` with blocker/major/minor 0/0/0. Final evidence was preflight 97 passed, golden 192, Ruff, strict mypy 52/0, backend 607 passed/77 deselected, frontend Vitest 32/build, migration contract 4, scans, and Compose.
- Fresh `origin/main` ff-only integration and non-force push of `fce19681…` succeeded. At capture time integration HEAD, `origin/main`, and remote main were equal to `fce19681…`. This is accepted/delivered offline/local preflight contract evidence only; it is not P4-B/P4-C/full-P4 completion.
- The [P4-C public-source due-diligence note](research/2026-08-02-p4c-ocr-provider-due-diligence.md) recommends Azure AI Document Intelligence `prebuilt-layout` / REST `2024-11-30` / Korea Central as the first research candidate only. It is `NOT SELECTED / NOT APPROVED`; no account, endpoint, credential, Provider call, legal approval, or AP-02 approval exists in this record.
- Private local inventory is aggregate-only: 4 candidate documents and 0 eligible because neither human-label evidence nor independent-review evidence is present. The set is non-representative and is not a QUALITY corpus.
- No real representative corpus, external Provider/OCR/AI, credential, network call, real PDF/XLS/XLSX, deployment, migration, DB/API/frontend/service change, or production activation was used.

## Lane decisions

|Lane|Status|What the next session may do|
|---|---|---|
|P4-A — Offline/Synthetic foundation|`COMPLETE_ACCEPTED_DELIVERED_TO_ORIGIN_MAIN`|Preserve original source/integration baseline `aeedceb…`, maintenance delivery `cad1ab4…`, and their capture-time evidence; do not expand the synthetic-only scope.|
|P4 local-only OCR|`COMPLETE_ACCEPTED_COMMITTED_FRESH_MAIN_FF_INTEGRATED_DELIVERED_TO_ORIGIN_MAIN`|Preserve source/integration baseline `91fd4a8…`, final review `ACCEPT_WITH_MINOR` 0/0/4 with 8 notes, final controller evidence, and the local-only boundary.|
|P4-B — Approved corpus benchmark|`BLOCKED_QUALITY_CORPUS_APPROVAL` / future validation gate|If representative real-corpus validation is desired, complete the [`P4-B QUALITY packet`](approvals/P4B_QUALITY_CORPUS_DECISION_PACKET.md) and supply human-label plus independent-review evidence before any run. This is not unfinished code debt.|
|P4-C — External Provider benchmark/selection|`BLOCKED_AP02_PROVIDER_OPT_IN` / deferred, not required for local-only scope|Only if a future external Provider is separately requested, complete a [`P4-C Provider-specific AP-02 packet`](approvals/P4C_PROVIDER_AP02_DECISION_PACKET.md) before any call. No account request is active.|

P4-B approval does not unlock P4-C, and P4-C approval does not establish corpus representativeness. CI remains fixture-provider-only, network-free, and credential-free. Missing KPI expands Human Review/manual fallback and never permits auto-finalization.

The delivered preflight/local OCR contracts do not change these lane decisions. P4-B remains blocked because aggregate local inventory is 4 candidate documents and 0 eligible, and the research-only Azure candidate does not satisfy any formal field in the P4-C decision packet.

## P4-A final maintenance evidence

- Strict/versioned golden, fixture, stage, candidate, report, and benchmark-output schemas with canonical JSON and Decimal/SHA-256 dataset→stage→candidate→report→output binding, exact cardinality, and order.
- Deterministic eight-stage runner with fail-closed upstream propagation, compatible stage/error states, independent stored candidate payloads, canonical warning/error ordering, rejection of every non-empty observed-warning subset when extraction is non-successful, and no warnings on failed/skipped stages.
- Nontrivial report evidence: exact fields 35/44, one page mismatch, one non-unit IoU, plus duplicate, unmapped, unapproved-normalization, value-mismatch, concave, self-intersecting, degenerate, and malformed fail-closed paths.
- Executable disjoint 20-edge matrix with exact reason binding across `CANDIDATE_ONLY`, `REVIEW_REQUIRED`, `MANUAL_FALLBACK`, and `STABLE_FAILURE`; no invented IoU threshold.
- Maintenance controller selector passed 9. `make p4-golden-check`: 192 passed. Backend gates passed Ruff, strict mypy 49 files/0 errors, pytest 510 passed/77 deselected, and compileall. Full `make check` exited 0, including frontend Vitest 32 and Next production build, migration contract 4, scans, and Compose.
- `make p4-benchmark-fixture` was repeated twice and retained the accepted output `354d7c10d7c6380c855876ef72d11148523ea12f1b346b8c5f3552ec416bfd23`, report `7b0601d2f57547db32a1c9897efa30211a14fd9ff645b2a9a4fcabf57da28933`, and fixture `05f777392052c3b29be32abe1d7852312baff966fd5ac1fdc88cc6479ae918d0` digests.
- Controller probes rejected truncated, swapped, foreign, and digest-tampered benchmark outputs; ambient precisions 12/28/50 and `ROUND_UP`, `ROUND_DOWN`, `ROUND_CEILING`, `ROUND_FLOOR`, and `ROUND_HALF_EVEN` produced identical canonical output/report bytes and digests; all 20 dispositions were bound.
- Final regression evidence also includes P2 PostgreSQL 10 and P3 PostgreSQL 67; disposable Docker containers/networks/volumes ended at 0/0/0. P3 browser E2E was not run because P4-A changes no runtime/API/UI/workflow path.
- Independent review history: the original 25-path acceptance returned `ACCEPT_WITH_MINOR` (0/0/3). The later exact four-path maintenance candidate closed the two remaining source-quality notes and returned final `VERDICT: ACCEPT` (0/0/0) with its freeze digest unchanged before/after. The original verdict and notes remain historical evidence, not live open findings.

## Safe next action

1. Preserve `91fd4a8…` as the local-only OCR source/integration baseline, `96413d2…` as its pre-closure descendant, and obtain the closure/live tip from Git history.
2. If real-corpus validation is desired, obtain P4-B QUALITY approval plus human-label and independent-review evidence before reading/running the corpus; otherwise hand off to the next separately approved phase.
3. Keep P4-C deferred. Do not request an account/credential or invoke an external Provider unless provider-specific P4-C approval is separately requested and completed.
4. The verified production artifact is `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y` at the recorded alias. For any future public synthetic deployment, preserve the frontend-only invariant; because a missing/incorrect flag can return localhost-fetch mode, verify that deployment's browser network plus live identity/behavior from deployment API.

This P4 section supersedes only section 7, “안전한 다음 단계”, in the historical P3 handoff below. All P3 scope, evidence, counts, accepted debt, delivery proof, and prohibitions remain truthful historical evidence.

# P3 delivery handoff and post-push closure (historical)

## 0. 현재 post-push closure

- Current gate: P0A/P0B/P1/P2/P3 source complete/accepted; P3 committed, fresh-main fast-forward integrated, and delivered to `origin/main`.
- Source commit: `91465f0413d0c0ca2633577078ec1300a6096442` (`feat: complete P3 vertical slice`), exactly 52 files, 8911 insertions, 119 deletions.
- Parent/fresh baseline: `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`. Before integration, clean local `main` and `origin/main` both equaled this commit.
- Integration: `git merge --ff-only 91465f0413d0c0ca2633577078ec1300a6096442`; no merge commit or rebase.
- Fresh integrated gates: `make bootstrap` and `make check`; Ruff; strict mypy 39; backend 346 passed/77 deselected; frontend Vitest 32 and Next production build; migration contract 4; scans/Compose; P2 PostgreSQL 10; P3 PostgreSQL 67; real Playwright 3/3. All passed.
- Cleanup: HYC containers/networks/volumes 0/0/0; only user-owned n8n remained running and untouched.
- Delivery: push succeeded as `b7bc4a8..91465f0 main -> main`. After fetch, local `main`, `origin/main`, and `git ls-remote` main all equaled `91465f0413d0c0ca2633577078ec1300a6096442`; both the baseline and source commit are ancestors of `origin/main`; main and candidate worktrees were clean immediately before this documentation-only reconciliation. Git history is authoritative.
- Boundary: this closure does not authorize or claim deployment, release, public service, real-data import/apply, external OCR/AI, production/non-disposable migration, production DB-role activation, P4/P5 start, or production readiness. Fixture-only N-1/N-2/N-5 and P2 N-M3 remain accepted debt to revisit before production activation.

The sections below preserve the pre-integration handoff snapshot and its then-valid next-step instructions as historical evidence; they do not override this closure.

## 1. 인계 상태 (historical pre-integration snapshot)

- Worktree: `/Users/hipgiinii/orca/workspaces/한양화학_v0/hanyang-p3-vertical-20260801`
- Branch: `JudyandGIINII/hanyang-p3-vertical-20260801`
- Base HEAD: `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`
- Gate: P3 source complete/accepted; exact-candidate Git integration pending
- Git state at this document time: uncommitted, unintegrated, unpushed
- Pre-doc-final freeze: changed/untracked 50 files; source hash `51f3bbb1d23970484813e893e51fd781f89fb781d02fac2db5cb475b00cac7f2`
- Hash caveat: 위 hash는 최종 source candidate를 문서 변경 전에 동결한 증거다. 이 문서를 포함한 post-doc tree hash로 사용하면 안 된다.

P2는 source commit `996056b`와 first integration-documentation commit `58e963c`가 fresh `origin/main` baseline `1e96836`에서 통합·전달된 상태다. P3 source acceptance는 P2의 Git 이력을 바꾸지 않으며, P3 자체의 commit/integration/push가 이미 수행됐다는 뜻도 아니다.

## 2. P3가 전달하는 것

P3는 synthetic calcium-chloride-bead fixture 하나로 다음 수직 흐름을 PostgreSQL/FastAPI/Next.js에 연결한다.

1. 수동 입고 생성, canonical material LOT, inbound allocation
2. SHA-256 문서 저장과 checksum deduplication
3. fixture extraction candidate와 NUMERIC confidence, page/bbox
4. 사람의 extraction review/confirm 및 section↔allocation 확정
5. inspection 생성 시 effective specification/value snapshot 고정
6. 공급사/HYC/internal 결과 분리와 Decimal 기반 fail-closed 판정
7. internal-result collection replace/clear, 재평가와 제출
8. INSPECTOR/LEAD 역할 분리, optimistic lock, 승인 원자성
9. 승인 snapshot/audit/outbox/idempotency response의 원자 저장
10. revision/retest lineage와 split-LOT trace
11. finalized evidence 및 confirmed extraction lineage의 DB 불변성
12. API-backed UI의 authoritative status와 real Playwright flow

## 3. 아키텍처 및 synthetic-data 경계

```text
Next.js UI -> FastAPI routes/services -> SQLAlchemy/PostgreSQL
                       |                         |
                       |                         +-> DB constraints/triggers/row locks
                       +-> pure Decimal domain  +-> snapshot/audit/outbox/idempotency
                       +-> local StoragePort
                       +-> FixtureExtractionProvider
```

- UI는 fixture reducer가 아니라 실제 loopback API/DB 상태를 읽는다.
- E2E는 route interception, mock persistence, SQLite, in-memory persistence를 사용하지 않는다.
- extraction은 `FixtureExtractionProvider`만 사용하며 OCR/LLM output은 후보일 뿐 최종 판정이 아니다.
- 실제 PDF/XLS/XLSX, 실데이터 import/apply, 외부 OCR/AI/NAS/Drive/ERP, 비일회성 DB는 사용하지 않았다.
- API/web은 검증 중 loopback에만 노출됐고 disposable Compose 자원은 종료 후 제거됐다.
- user-owned n8n은 범위 밖이며 QA 전후 계속 running 상태로 untouched였다.

## 4. Canonical commands와 검증 수치

Repository root에서 사용하는 canonical entrypoint:

```sh
make bootstrap
make check
make p2-postgres-check
make p3-postgres-check
make p3-e2e
git diff --check
python3 scripts/scan_secrets.py
python3 scripts/check_sensitive_documents.py
```

최종 독립 backend review:

- `PASS`; blocker 0, major 0, medium 0
- P3 PostgreSQL 67
- mutation-first reverse-order probe 6 cycles
- terminal-first focused serialization 27
- P2 PostgreSQL regression 10
- substantive `make check`: backend 346 passed/77 PostgreSQL deselected, strict mypy 39 files, frontend Vitest 32, migration contract 4

최종 독립 UI/API review:

- real `make p3-e2e` Playwright 3/3
- 별도 real live-stack HTTP/browser smoke: desktop 및 375×812
- expected concurrent status pairs: intake 201+409, inspection 201+409, approval 200+409
- completed winning-payload sequential replay: byte-identical
- invalid upload: empty 422, over-limit 413, residue 0
- P3 API 67, repository fingerprint unchanged, cleanup 0/0/0/0

Hermes controller QA:

- `make bootstrap && make check`: Ruff, mypy 39, backend 346/77 deselected, frontend 32, Next build, migration 4, scans, Compose 전부 통과
- P2 PostgreSQL 10; P3 PostgreSQL 67; real Playwright 3
- `backend/tests/integration/api/test_db_serialization.py`: 27 tests × 3 fresh cycles = 81
- QA 동안 frozen pre-doc candidate hash 유지
- 종료 후 HYC containers/networks/volumes 0/0/0; user-owned n8n만 running

## 5. 핵심 불변식과 강제/검증 위치

|불변식|주요 강제 위치|대표 검증|
|---|---|---|
|OCR/fixture extraction은 후보만 생성하고 사람 확인 전 확정 금지|`backend/src/hyc_api/services/p3.py`, extraction contracts|`test_vertical_slice.py`, Playwright happy/hold flows|
|공급사/HYC/internal 결과와 판정을 분리하고 Decimal만 사용|`backend/src/hyc_domain/judgment.py`, `backend/src/hyc_data/repositories.py`|P2 domain tests, `test_internal_substitute_hold.py`, P3 API 67|
|누락·미매핑·저신뢰·internal incomplete는 fail closed|P3 service evaluation/submit guards|`test_internal_substitute_hold.py`, `inspection-hold.spec.ts`|
|canonical LOT와 inbound allocation 분리, cross-LOT lineage 금지|P3 fixture seed/service and DB link constraints|`test_split_lot_trace.py`, `test_vertical_slice.py`, `test_db_serialization.py`|
|internal-results PUT은 full collection replace/clear이고 GET은 mutation-free|`backend/src/hyc_api/routes/inspections.py`, `backend/src/hyc_api/services/p3.py`|`test_vertical_slice.py` replace/clear/GET regressions|
|승인 재평가·snapshot·approval·audit·outbox·idempotency는 원자적|`backend/src/hyc_data/repositories.py`, P3 service|`test_approval_atomicity.py`, `test_idempotency_races.py`|
|no-row idempotency race loser는 stable 409, winner replay는 byte-identical|`backend/src/hyc_api/services/p3.py` exact constraint savepoint|`test_idempotency_races.py`|
|finalized supplier/internal/sample evidence I/U/D는 DB에서 거부되고 approval과 직렬화|Alembic `20260801_0004`, deterministic parent-case `FOR UPDATE`|`test_evidence_immutability.py`, `test_db_serialization.py`|
|confirmed extraction run/field/section/link I/U/D/reparent는 DB에서 거부|Alembic `20260801_0004`, partial unique indexes and parent-run locks|`test_vertical_slice.py`, `test_db_serialization.py`|
|first confirmation은 단일 run/section/link만 남기고 loser residue 0|P3 confirm transaction and exact uniqueness mapping|genuine first-confirm tests in `test_vertical_slice.py` and focused serialization suite|
|invalid upload은 422/413이며 path를 노출하거나 storage residue를 남기지 않음|`backend/src/hyc_api/storage.py`, document route mapping|`test_document_dedup.py`, independent live API smoke|
|UI status는 서버 authoritative state와 일치|`frontend/src/components/inspection/InspectionWorkspace.tsx`, API client|Playwright 3/3, desktop/375×812 smoke|

All historical blocker/major findings are fixed: cross-LOT lineage, repeated internal-result replace/clear, finalized evidence I/U/D, reconfirm/confirmed review DB immutability, genuine first-confirm race, no-row idempotency races, invalid-upload mapping/residue, approval/evidence serialization, and confirmed extraction run/field/section/link serialization with cross-LOT rebind denial.

## 6. 수용된 non-production debt

- N-1: fixture-only validation/auth ordering
- N-2: GET fixture seeding
- N-5: in-memory session eviction
- P2 N-M3: broad DB-direct app-role writer가 case/evidence table 직접 권한을 모두 가진 경우 unfinalized case를 `LEAD_REVIEW`로 생성하고 유효 근거를 넣어 중간 상태 이력을 우회할 수 있는 defense-in-depth gap

N-1/N-2/N-5는 synthetic P3 source acceptance를 막지 않는다. N-M3도 P2에서 accepted technical debt였지만, 모두 production readiness를 의미하지 않으며 production DB-role activation 전에 재검토해야 한다.

## 7. 안전한 다음 단계

1. 권한 있는 controller가 이 worktree의 exact candidate와 문서 diff를 재확인한다.
2. Pre-doc source hash와 post-doc tree를 혼동하지 않고 docs-inclusive exact manifest/status를 별도로 동결한다.
3. 별도 Git 권한에 따라 exact candidate를 단일 의도된 source/docs commit 세트로 커밋한다.
4. fresh `origin/main` baseline에서 fast-forward 가능성과 candidate identity를 검증한다.
5. fresh integration worktree에서 canonical gates를 재실행한다.
6. 명시적 push 권한이 있을 때만 remote-base/ancestry를 확인하고 push한다.
7. 통합 결과를 DEVLOG/KANBAN/traceability와 Hermes Kanban에 동기화한다.

Historical P3 checkpoint에서는 P4/P5가 unstarted였다. 이 과거 문구는 현재 P4-A remediation 상태를 설명하는 문서 상단을 override하지 않으며, P3 source acceptance나 Git integration만으로 pilot/production 단계를 자동 시작하지 않는다는 경계는 계속 유효하다.

## 8. 금지 작업

- 이 handoff 자체를 commit/push/merge/deploy 권한으로 해석하지 않는다.
- main/shared CWD mutation, reset/restore/stash/rebase 또는 무단 Git 작업을 하지 않는다.
- 실 PDF/XLS/XLSX를 커밋·업로드·미러링·외부 전송하지 않는다.
- 실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP 호출을 하지 않는다.
- production/non-disposable migration 또는 production DB-role activation을 하지 않는다.
- public service exposure, deployment, release, production-ready 선언을 하지 않는다.
- n8n을 중지·재시작·삭제·설정 변경하지 않는다.
