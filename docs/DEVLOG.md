# DEVLOG

## 2026-07-30 — PRD 구현 계획 독립 수립·비교·통합

### 요청

`Prd.md`를 바탕으로 Hermes와 Claude Code Opus 5가 각각 독립 구현 계획을 만들고, 양쪽 장점만 통합한 최종 계획을 보고·문서화한다.

### 수행

- `Prd.md` 전체와 기준/Raw Excel 구조, 이미지 기반 PDF 성격을 확인했다.
- 현재 저장소가 소스·커밋 없는 신규 프로젝트이며 모든 원본이 untracked임을 확인했다.
- Claude Code CLI를 `--model opus --effort medium --permission-mode plan --tools Read`로 호출했다. CLI JSON `modelUsage`에서 canonical model `claude-opus-5`, `is_error=false`를 확인했다.
- Hermes 계획을 먼저 고정한 뒤 Claude에게 `Prd.md`만 읽게 하여 서로의 계획을 보지 않은 상태의 독립 산출물로 보존했다.
- PRD 내부 모순, LOT cardinality, spec scope, 엔진/상태 분리, 승인 불변성, OCR golden, 검증/운영 게이트를 비교해 통합 계획을 작성했다.
- 52개 FR 전부와 UI/매칭/데이터/API/보고서/보안/감사/NFR/OCR/AT/DoD를 Phase·owner·planned test·gate에 연결한 추적 매트릭스를 작성했다.
- Alfred 1차 read-only QA의 HIGH/MEDIUM 5건(P0 승인 경계, LOT identity, API idempotency, 전수 추적, AT-013 production seam)을 보정했다.
- Alfred R1 adapter validator는 `PASS READY_FOR_HERMES_REVIEW`, substantive audit는 `PASS`, 이전 5건 모두 `RESOLVED`, 신규 HIGH/MEDIUM blocker 0을 반환했다.
- 통합 계획의 상태를 `PLAN_REQUIRES_USER_APPROVAL`로 유지하고 AP-01~05와 P0B 명시적 구현 승인을 구현 전 gate로 확정했다.
- 세션 Todo와 Hermes Kanban board `hanyang-chemical-v0`, card `t_7d493a1e`를 생성·동기화했다.

### 생성 문서

- `README.md`
- `AGENTS.md`
- `docs/plans/2026-07-30-hermes-independent-plan.md`
- `docs/plans/2026-07-30-claude-opus5-independent-plan.md`
- `docs/plans/2026-07-30-integrated-implementation-plan.md`
- `docs/TRACEABILITY_MATRIX.md`
- `docs/reviews/2026-07-30-integrated-plan-alfred-qa.md`
- `docs/DEVLOG.md`
- `docs/KANBAN.md`
- `.agent/plans/ALF-20260730-HYC-INTEGRATED-PLAN-QA*/` — 두 차례 Alfred request/response/invocation 증빙

### 의도적으로 하지 않은 것

- 애플리케이션 코드·의존성·DB·migration·외부 OCR 호출
- Git add/commit/push/remote 생성
- 실 PDF/XLSX의 이동·수정·외부 전송
- 배포 또는 공개 서비스 노출

### 다음 게이트

1. 사용자에게 두 독립 계획의 비교와 QA 보정 완료 결과를 보고한다.
2. AP-01~05와 P0B 구현 착수에 대한 명시적 승인을 받기 전 구현하지 않는다.

## 2026-07-30 — AP-01~05 및 P0A/P0B/P1 구현 승인

### 승인 범위

- 사용자가 AP-01~05를 권장 기본값대로 승인했다.
- P0A read-only evidence freeze, P0B fixture/importer dry-run bootstrap, P1 repository/contract foundation 구현을 승인했다.
- 민감 실 PDF/XLSX는 AP-05에 따라 Git과 외부 전송에서 계속 제외한다.
- 실데이터 apply/import, 외부 OCR/AI, P2 이후, 배포·서비스 공개는 승인되지 않았다.

### 실행 방식

- 민감 실원본과 `.agent` coordination artifact를 제외한 계획 baseline을 먼저 `origin/main`에 커밋·푸시한다.
- 이후 Orca orchestration Run/Task/Dispatch provenance와 isolated worktree를 사용하고 Codex CLI를 primary builder로 둔다.
- Hermes가 실제 diff, 테스트, lint/typecheck/build, Git ancestry를 독립 검증한다.

### P0A 완료

- 로컬 실원본 4개(PDF 2, XLSX 2)의 SHA-256, byte size, mtime을 before/after로 계산했고 동일함을 재검증했다.
- 이 historical before/after 관찰·동일성 확인은 수행됐지만, 원본 v1 tracked artifact는 단일 canonical snapshot과 `source_immutable_before_after: true`만 보존한다. explicit per-source before/after 관찰은 2026-07-31 controller reverification sidecar가 최초 tracked evidence다.
- XLSX ZIP/XML metadata만 읽어 worksheet 수를 관찰했으며 cell value는 읽거나 evidence에 복제하지 않았다.
- workbook worksheet 수는 각각 38개와 3개였다. `38 templates / 119 item rows`의 business 의미는 P0B parser 전까지 `UNVERIFIED_UNTIL_P0B_PARSER`로 유지한다.
- `docs/evidence/2026-07-30-p0a-source-manifest.json`과 `docs/evidence/2026-07-30-p0a-evidence-freeze.md`를 생성했다.
- 원본 Git 추가, DB/import, fixture 복제, 외부 전송, migration은 실행하지 않았다.

## 2026-07-31 — P0B review remediation candidate

### 범위와 결과

- 이전 P0B candidate와 중단된 synthetic test 추가분을 분류해 보존하고, `backend/scripts/import_spec_workbook.py`를 fail-closed ZIP/XML/relationship/row validator로 보강했다.
- 두 구조 프로파일(`masked-marker-v1`, `qm301-legacy-structural-v1`)은 모두 read-only dry-run만 수행한다. 출력은 결정론적 masked JSON이며 DB write, formula 실행, 외부 link/OCR/AI 호출은 없다.
- ZIP duplicate/encryption/unsupported compression/corrupt member/input-size cap, DTD/entity, relationship duplicate/external/traversal, marker/legacy row ambiguity, shared strings, CLI JSON error backstop을 temporary synthetic workbooks로 검증했다.
- `.gitignore`의 민감 문서 규칙은 root-only 규칙에서 recursive basename 규칙으로 보정했다.

### 실제 검증 명령

- `XDG_CACHE_HOME="$PWD/.uv-cache" uv lock --project backend --check` — exit 0
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0
- 이 verification record는 후속 P0B correction lane의 full-suite evidence로 대체됐다. 이전 test count는 현재 gate의 근거가 아니다.
- `python3 -m compileall -q backend/scripts backend/tests` — exit 0

### 현재 gate

P0A는 complete 상태다. P0B remediation candidate는 후속 correction lane의 final QA/controller acceptance 대기 상태로 전환됐다. P1/P2는 P0B QC 후에만 조건부 진행 권한이 있으며, 이 기록은 어느 phase의 완료나 독립 최종 승인을 주장하지 않는다. 실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, deployment/service exposure는 계속 미승인이고 실행하지 않았다.

## 2026-07-31 — P0B independent-QA correction candidate

### Correction scope

- XML protection uses an encoding-neutral Expat preflight that rejects DTD/entity declarations before ElementTree receives a part. After ZIP entry/type/encryption/member/total-size bounds, every bounded member (including binary/media) is read before semantic parsing, so CRC/decompression corruption fails closed. `[Content_Types].xml` requires the official `Types` root and exactly one canonical `/xl/workbook.xml` override with the non-macro `.xlsx` workbook content type.
- `_rels/.rels` is required and must contain exactly one official transitional/strict `officeDocument` relationship resolving internally to `xl/workbook.xml`. Every archive `.rels` part requires the official package root, non-empty unique Id/Type/Target, absent/`Internal` TargetMode only, an in-package OPC-relative target, and an existing resolved member. Absolute, external, URI-like, percent/query/fragment/control-character, backslash, and escaping traversal targets fail closed; legitimate `..` is accepted only when normalization remains in the package root. Workbook worksheet relationship-type and target safeguards remain in force.
- The legacy QM301 profile now requires its first complete item row at row 11 and rejects a moved/deleted first item block.
- The expectation fixture is validated as a complete, exact contract: schema, P0A evidence/observation provenance, alias/digest, positive canonical integer counts, and fail-closed discrepancy policy. The typed baseline preserves the approved source digest and compares it with the actual input digest. Ordered, masked `QUALITY_REVIEW_REQUIRED` evidence reports `SOURCE_DIGEST_MISMATCH` before any `STRUCTURAL_COUNT_MISMATCH`; no auto-correction or apply occurs.
- Synthetic sentinel values are explicitly labeled `TEST_FIXTURE_*_NO_CREDENTIAL`; this preserves secret detection while classifying the test values as fixtures rather than credentials.
- The source-document manifest is metadata-only (not masked) and links to the committed P0A evidence paths, schema/observation, and source aliases/digests without a source body.

### Actual verification

- `XDG_CACHE_HOME="$PWD/.uv-cache" uv lock --project backend --check` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend pytest -q` — `79 passed in 3.69s`.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend python -m compileall -q backend/scripts backend/tests` — exit 0.
- `git diff --check` — exit 0 after trailing-whitespace correction.

### Current gate and limitation

P0A remains complete. This is a P0B correction candidate only; final independent QA and controller acceptance remain pending. P1/P2 may proceed only after P0B QC. No real-source dry-run was performed in this lane, and no real-data apply/import, external OCR/AI call, non-disposable migration, deployment, or service exposure was performed.

## 2026-07-31 — P0B third focused remediation candidate

### Correction scope

- `[Content_Types].xml` now produces a deterministic member-to-media-type map: exact canonical `Override` takes precedence, otherwise a case-insensitive `Default` extension applies. Malformed, duplicate, non-canonical, or unmapped declarations fail closed; directory entries and `[Content_Types].xml` are correctly exempted.
- Every XML media type (`application/xml`, `text/xml`, and syntactically valid `+xml`) receives the encoding-neutral DTD/entity-safe XML preflight even when the ZIP member has a non-XML filename. Every `.rels` part is parsed and must resolve to exactly the package relationships media type. Workbook, worksheet (including the standardized Strict equivalent), and present shared-strings types are exact-gated.
- Every relationship now has a conservative documented ASCII NCName-compatible Id, absolute URI Type with an RFC 3986 scheme and no whitespace/control character, exact allowed attributes, no children, and only whitespace text. Existing uniqueness, Internal-only target, in-package resolution, source existence, root `officeDocument`, and worksheet-role checks remain enforced. Root `_rels/foo.xml.rels` now correctly uses `foo.xml` as its source without relaxing target escape rejection.
- Synthetic regressions cover XML/DTD payloads in `.bin`, malformed `+xml`, WordprocessingML-as-worksheet, wrong/missing/duplicate content-type declarations, shared-strings typing, relationship lexical/structural violations, a valid `urn:` Type, and a root-level source relationship with an existing internal target.

### Actual verification

- `XDG_CACHE_HOME="$PWD/.uv-cache" uv lock --project backend --check` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend pytest -q` — `94 passed in 4.41s`.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend python -m compileall -q backend/scripts backend/tests` — exit 0.
- `git diff --check` — exit 0.

### Current gate and limitation

P0A remains complete. P0B remains pending final independent QA and controller acceptance; P1/P2 are conditionally authorized only after P0B QC. No real-source dry-run was run. No real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure was performed.

## 2026-07-31 — P0B fourth focused remediation candidate (RFC 3986 / OPC lexical canonicality)

### Correction scope

- Relationship `Type` now receives complete deterministic ASCII RFC 3986 lexical validation: a valid scheme, non-empty remainder, only URI characters, and only well-formed `%HH` triplets. Whitespace/control/non-ASCII, backslash, quotes, braces, `|`, malformed percent sequences, and scheme-only values fail closed; official `http` types, `urn:masked:relationship`, and valid percent-encoded URI types remain accepted.
- A shared conservative OPC URI-path-segment validator now applies to ZIP member names, Content-Type `Override` part names, and internal relationship `Target`s. It rejects whitespace/control/non-ASCII, backslash, query/fragment, URI/drive forms, forbidden punctuation, empty and non-canonical member segments, and all percent-encoded package paths (including malformed encodings). `[Content_Types].xml` remains the required standardized bracket-spelled OPC control-member exception. Literal `.`/`..` are allowed only in a relationship target when normalization remains inside package root.
- Every `Relationships` root must have no attributes, while whitespace-only root text and `Relationship` tails remain accepted and exact `Relationship` children remain required. Relationship IDs remain unique, but different IDs may intentionally resolve to the same target because OPC permits multiple typed relationships to one part.
- Synthetic-only regressions cover space/tab/control/non-ASCII/forbidden-punctuation/malformed-percent member names, overrides, and targets; safe parent traversal; full relationship-Type lexical cases; root attributes; whitespace preservation; and same-target distinct relationship IDs.

### Actual verification

- `XDG_CACHE_HOME="$PWD/.uv-cache" uv lock --project backend --check` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend pytest -q` — `127 passed in 5.90s`.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend python -m compileall -q backend/scripts backend/tests` — exit 0.
- `git diff --check` — exit 0.

### Current gate and limitation

P0A remains complete. P0B remains pending final independent QA and controller acceptance; P1/P2 are conditionally authorized only after P0B QC. No real-source dry-run was run. No real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure was performed.

## 2026-07-31 — P0B final independent approval and acceptance

### Final evidence recorded

- The frozen P0B candidate tracked diff has SHA-256 `7f7be3324c4040bfc4b47a35f7d3643d22eb618ea380a2d30acbc0aaaf4b5b2c`.
- Final independent review performed 67 in-memory probes and returned `APPROVE`: HIGH 0, MEDIUM 0. The one accepted LOW lexical-contract note is that generic scheme-specific URI semantics are defense-in-depth, because consumed relationship roles use exact allowlists.
- Controller evidence records `127 passed`; the approved real QM301 dry-run produced 38 templates/119 rows with discrepancy 0, DB write/apply 0, unchanged source hash/size/mtime, and tracked sensitive documents 0.

### Gate result and continuing boundary

P0A and P0B are complete and accepted. P1 is authorized and ready, but this approval record does not claim that P1 has started or passed. P2 is authorized only after the P1 contract gate and has not started or passed. Real-data apply/import, external OCR/AI, non-disposable migration, deployment, and service exposure remain unauthorized. This documentation-only sync ran no code tests and did not access source PDF/XLS/XLSX evidence.

## 2026-07-31 — P1 repository/contract foundation candidate

### Candidate scope

- Added Python 3.12 `uv` project declarations for FastAPI, Pydantic v2 settings, SQLAlchemy/Alembic/psycopg, Redis, strict Ruff/mypy and the retained P0B importer suite.
- Added API and worker liveness/readiness seams, loopback-only Compose services, minimal Next.js health UI, P1 no-op Alembic baseline, local secret/tracked-sensitive-document scans, and CI workflow.
- Added strict extraction/error contracts, deterministic schema/OpenAPI/client generation entrypoints, synthetic-only extraction port tests, and UTC-to-Asia/Seoul display helper. No external OCR/AI provider or real source data path was implemented.

### Gate state and boundary

This is a P1 **candidate under Hermes independent QA**, not complete or accepted. P2 remains blocked on the independent P1 contract gate. The candidate does not authorize real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure. No PDF/XLS/XLSX source evidence was opened by this P1 work.

### Local verification record

- `python3 -m compileall -q backend/src backend/scripts backend/tests scripts` — exit 0.
- `docker compose config --quiet` — exit 0. Docker daemon access is unavailable in this sandbox, so no Compose service was started.
- `python3 scripts/scan_secrets.py`, `python3 scripts/check_sensitive_documents.py`, and `git diff --check` — exit 0.
- Required dependency resolution could not run: the sandbox DNS lookup for `pypi.org` and `registry.npmjs.org` fails, and Corepack's default cache is outside the writable sandbox. Therefore `uv lock/sync/run`, schema/OpenAPI/client artifact generation, backend pytest/Ruff/mypy/Alembic, and pnpm frozen install/lint/typecheck/test/build remain unverified. These failures are environmental blockers, not a P1 gate pass.

## 2026-07-31 — P1 Hermes-audit remediation verification

### Successful commands actually run

- `XDG_CACHE_HOME="$PWD/.uv-cache" uv lock --project backend --check` and `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend pytest -q` — `146 passed, 1 warning`; the byte-identical accepted P0B importer suite separately returned `127 passed in 5.91s`.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend ruff check --force-exclude backend/src backend/scripts backend/tests` — exit 0; only the accepted P0B importer and its accepted integration test are exact-path excluded.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend mypy --config-file backend/pyproject.toml backend/src backend/scripts` — `Success: no issues found in 11 source files`; the accepted P0B importer is exact-path excluded.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend python -m compileall -q backend/src backend/scripts backend/tests`, `... python backend/scripts/generate_contracts.py --check`, and `... python backend/scripts/check_migrations.py` — exit 0. The migration check performs disposable SQLite upgrade→downgrade→upgrade; it does not claim PostgreSQL runtime coverage.
- `python3 scripts/scan_secrets.py`, `python3 scripts/check_sensitive_documents.py`, `docker compose config --quiet`, `git diff --check`, and a no-diff assertion over both accepted P0B files — exit 0.

### Remediation details and remaining blockers

- Root pytest is deterministic through `pytest.ini`; no shell-only source-path state is required. API/worker readiness catches connection exceptions and returns typed 503 envelopes. Contract artifacts are repository source candidates with strict `extra=forbid`, required UUID/time fields, Decimal-string schema boundaries, and matching health/error OpenAPI responses. The secret scan now scans docs/tests and permits only explicit line-level placeholder/fixture/redacted allowances.
- `corepack pnpm --dir frontend install` cannot resolve `registry.npmjs.org` in this sandbox, so `frontend/pnpm-lock.yaml`, the generated OpenAPI TypeScript client, frozen install, and frontend checks cannot yet be verified. `docker info` is denied access to the local Docker socket, so disposable Compose build/up, live health probes, and in-Compose PostgreSQL migration cycling cannot run here. These are environmental blockers, not a P1 gate pass.

P1 remains `CANDIDATE_UNDER_HERMES_QA`; P2 remains blocked. No source PDF/XLS/XLSX was accessed, and no real-data apply/import, external OCR/AI, non-disposable migration, deployment, or external service exposure occurred.

## 2026-07-31 — P1 focused frontend remediation candidate

### Changes made

- Pinned `next` and the matching `eslint-config-next` from `15.4.5` to `15.5.22`, retaining the Next 15 architecture; `frontend/pnpm-lock.yaml` was regenerated with `pnpm` 10.32.1 in offline lockfile-only mode.
- Converted the ESLint 9 flat config to `FlatCompat` with a deterministic config-file base directory. This adapts Next 15's legacy `next/core-web-vitals` shareable config instead of importing its extensionless CommonJS subpath as an ESM flat-config array.
- Execution demonstrated that the generated-client drift script leaked its temporary directory on generation failure. It now uses a deterministic frontend cwd and `try`/`finally` cleanup; the leaked temporary directories from this verification were removed.

### Actual verification and remaining boundary

- `CI=true corepack pnpm --dir frontend install --lockfile-only --offline --no-frozen-lockfile` — exit 0; the lock imports `next@15.5.22`, `eslint-config-next@15.5.22`, and direct `@eslint/eslintrc@3.3.6` for the compatibility bridge.
- `corepack pnpm --dir frontend install --frozen-lockfile` recognized the up-to-date lockfile, then failed while downloading packages because this Codex sandbox cannot resolve `registry.npmjs.org`. Consequently lint, typecheck, test, build, and generated-client drift validation could not run: their package binaries are absent. The generated client was not rewritten, but regeneration stability is not yet verified.
- Docker/PostgreSQL runtime verification remains for the Hermes controller because this Codex sandbox cannot access the Docker socket. This is not a P1 contract-gate pass.

P1 remains `CANDIDATE_UNDER_HERMES_QA`, not complete or accepted; P2 remains blocked on the independent P1 contract gate. No source PDF/XLS/XLSX was accessed, and no real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure occurred.

## 2026-07-31 — P0A/P1 Claude Opus blocker remediation candidate

### P0A evidence and boundary correction

- Replaced current-tree P0A filename-as-evidence fields with stable aliases plus `filename_sha256`; the COA alias is `calcium-chloride-coa-2025-04-23`. Historical Git contained filename metadata already; no history rewrite was authorized, so this is forward masking only.
- Added the controller-only, alias-only two-pass P0A reverification sidecar and linked it from the original v1 manifest/freeze without changing the accepted P0B importer contract or its required v1 workbook-observation path.
- Recorded the separately approved controller-only local real-source dry-run at [`docs/evidence/2026-07-31-p0b-controller-real-dry-run.json`](./evidence/2026-07-31-p0b-controller-real-dry-run.json). Command template only: `uv run --project backend python backend/scripts/import_spec_workbook.py --dry-run <APPROVED_LOCAL_QM301_PATH>`. Masked-output SHA-256: `122c2be494f5d5b66c555303e08e41b9717b08e3de579b311afebf3badb9517c`; 38 templates, 119 rows, zero discrepancies, zero database writes, `apply_performed: false`, source unchanged. Claude did not access or rerun the source.

### P1 candidate correction

- Added one shared canonical Decimal-string regex for Pydantic runtime and JSON Schema; binary floats, non-finite values, exponent notation, whitespace, plus signs, and noncanonical spellings fail closed.
- Added non-sensitive API/worker generic 500 envelopes with correlation UUIDs, fail-closed readiness defaults, URI-authority credential scanning, content/path-bound fixture policy, extension-pattern sensitive-document prevention, Next type generation before standalone typecheck, and disposable PostgreSQL `tmpfs`.
- Expanded static command scope to `backend/src`, `backend/scripts`, `backend/alembic`, root `scripts`, and `backend/tests`; local aggregate checks include `docker compose config --quiet`.

### Gate

This is a candidate patch only. Hermes must rerun the bounded checks and Compose; no runtime success is claimed here. P1 remains `CANDIDATE_UNDER_HERMES_QA`, and P2 remains blocked. No real PDF/XLS/XLSX was accessed, no real-data apply/import occurred, and no external OCR/AI, deployment, or service exposure was performed.

## 2026-07-31 — P1 frontend verification follow-up

### Focused changes

- Replaced the anonymous ESLint default-export array with named `config`, eliminating `import/no-anonymous-default-export`.
- Updated the generated-client drift checker to invoke its project-local `node_modules/.bin/openapi-typescript` executable directly. It reports spawn errors safely, removes its temporary directory in `finally`, and compares generated and committed clients as raw bytes.

### Hermes controller verification

- Frozen install for the locked `next@15.5.22` and `eslint-config-next@15.5.22` — exit 0.
- `corepack pnpm --dir frontend lint` — exit 0, warning-free.
- `corepack pnpm --dir frontend typecheck` — exit 0.
- `corepack pnpm --dir frontend test` — exit 0, `1 passed`.
- `corepack pnpm --dir frontend build` — exit 0, production build completed.
- `corepack pnpm --dir frontend check:client` — exit 0; generated client matches byte-for-byte.
- `git diff --check` — exit 0.

Docker/PostgreSQL runtime verification remains pending Hermes controller. P1 remains `CANDIDATE_UNDER_HERMES_QA`, not complete or accepted; P2 remains blocked on the independent P1 contract gate. No source PDF/XLS/XLSX was accessed, and no real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure occurred.

## 2026-07-31 — P1 focused Compose collision/reproducibility remediation

### Focused change and existing Hermes evidence

- Parameterized only the loopback-published API and web host ports: `HYC_API_HOST_PORT` defaults to 18000 for container port 8000, and `HYC_WEB_HOST_PORT` defaults to 13000 for container port 3000. PostgreSQL and Redis remain unexposed.
- Added the placeholder-only local host-port values to `.env.example` and documented default startup and health URLs: `http://127.0.0.1:18000/health/ready` and `http://127.0.0.1:13000/api/health`.
- Pinned image-build `uv` to `0.11.14`, matching CI, rather than installing an unbounded latest package.
- Hermes controller successfully built the Compose images. The original full startup correctly aborted and cleaned up because `127.0.0.1:8000` was occupied by another approved local backend; that backend was not disturbed.

### Current verification and gate

- `docker compose config --quiet` — exit 0 with the default `.env.example` values and again with `HYC_API_HOST_PORT=18123 HYC_WEB_HOST_PORT=13123`; the rendered override maps loopback 18123→container 8000 and 13123→container 3000.
- `XDG_CACHE_HOME="$PWD/.uv-cache" uv run --project backend ruff check --force-exclude backend/src backend/scripts backend/tests` — exit 0; `... mypy --config-file backend/pyproject.toml backend/src backend/scripts` — `Success: no issues found in 11 source files`.
- `corepack pnpm --dir frontend lint` and `corepack pnpm --dir frontend typecheck` — exit 0.
- `git diff --check` — exit 0.
- Full Compose runtime health probes and the disposable PostgreSQL cycle remain pending a Hermes rerun using the parameterized non-conflicting host ports. This is not a P1 contract-gate pass.

P1 remains `CANDIDATE_UNDER_HERMES_QA`, not complete or accepted; P2 remains blocked on the independent P1 contract gate. No source PDF/XLS/XLSX was accessed, and no real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure occurred.

## 2026-07-31 — P1 focused web standalone runtime healthcheck remediation

### Hermes rerun evidence and focused fix

- Hermes Compose rerun found PostgreSQL, Redis, API, and worker healthy, but the web service unhealthy. The Next standalone server logged a bind only to its container hostname (`http://<container-id>:3000`); its container-loopback healthcheck then failed with `ECONNREFUSED 127.0.0.1:3000`.
- The production stage of `frontend/Dockerfile` now pins `HOSTNAME=0.0.0.0` and `PORT=3000` alongside `NODE_ENV=production`. This makes Next standalone listen on all container interfaces at port 3000. `compose.yaml` remains unchanged: web publication is still loopback-only at `127.0.0.1:${HYC_WEB_HOST_PORT:-13000}:3000`.

### Current verification and gate

- `corepack pnpm --dir frontend lint` — exit 0.
- `corepack pnpm --dir frontend typecheck` — exit 0.
- `corepack pnpm --dir frontend test` — exit 0; Vitest: `1 passed`.
- `corepack pnpm --dir frontend build` — exit 0; Next 15.5.22 production build completed.
- `docker compose config --quiet` — exit 0.
- `git diff --check` — exit 0.
- A complete Compose runtime healthcheck and disposable PostgreSQL migration cycle remain pending the Hermes rerun. This is not a P1 contract-gate pass.

P1 remains `CANDIDATE_UNDER_HERMES_QA`, not complete or accepted; P2 remains blocked on the independent P1 contract gate. No source PDF/XLS/XLSX was accessed, and no real-data apply/import, external OCR/AI, non-disposable migration, deployment, or service exposure occurred.

## 2026-07-31 — P1 final Hermes direct acceptance

### Authority and gate decision

- The user explicitly authorized Hermes on 2026-07-31 to replace the unavailable Claude final reapproval with direct controller verification, decide the P1 approval, proceed, and cancel the 18:51 Claude retry. Cron job `d7e684c0b605` was removed.
- Hermes directly recovered the final disposable Compose exact-candidate controller output for `proc_7e03db110d2f`. The process completed with exit 0: PostgreSQL, Redis, API, worker, and web were healthy; API live/ready and web probes returned HTTP 200 with expected JSON; the PostgreSQL migration roundtrip passed; and cleanup passed.
- Hermes accepted P1 and passed the P1 contract gate. The resulting current state is `P0A_P0B_P1_COMPLETE_ACCEPTED_P2_AUTHORIZED_NOT_STARTED`; P2 is authorized/unblocked but has not started.

### Final verification record

- P0A: all 4 historical filename-hash bindings remain valid; the explicit before/after two-pass comparison was 4/4 equal, `source_immutable_before_after: true`, and normalized current-tree basename hits are 0.
- P0B: the accepted importer and integration test remain byte-identical to `origin/main`; the accepted review was `APPROVE` (HIGH 0, MEDIUM 0). Controller evidence remains 127 tests and the approved real dry-run at 38 templates/119 rows, discrepancy 0, DB write/apply 0, and source unchanged.
- Pytest: root `pytest.ini` is canonical and there is no nested backend pytest configuration. `--collect-only -vv` reported repository rootdir and `configfile: pytest.ini`; a targeted direct test file passed 12 tests and the full suite passed 172. One upstream Starlette/httpx deprecation warning is non-blocking.
- `make check` exited 0, including contracts/client drift, Ruff, strict mypy across 15 files, 172 pytest tests, compileall, frontend lint/typegen/typecheck/Vitest (1)/build, migration check, secret scan, sensitive-document scan, and Compose config.
- Frontend determinism: typecheck is `tsc --noEmit --incremental false`, no `tsconfig.tsbuildinfo` remains, and the Makefile/CI run Corepack pnpm from frontend cwd with pinned pnpm `10.13.1`. Frozen install and all frontend gates passed; the lockfile is unchanged.

### Continuing boundary

No real source import/apply, external OCR/AI, non-disposable migration, deployment, or public service exposure occurred. Those operations remain unauthorized; P1 acceptance and P2 authorization do not substitute for their separate product/operations approvals.

## 2026-07-31 — FE8 frontend fixture workflow independent closure (pre-docs evidence)

### Implemented and independently reviewed scope

- The deterministic synthetic frontend workflow implements eight flows: queue, receipt/canonical LOT, explicit document-candidate finalization, section-allocation matching, exact Decimal internal testing, submit preflight, LEAD review, and LOT/audit timeline.
- This is fixture-only: no backend or network mutation, persistence, real authentication/authorization, OCR/AI, ERP, real-data apply/import, or deployment. Role switching is a UI simulation, not authentication or authorization.
- Business numeric semantics use Decimal strings and `BigInt`, not binary floating point. Candidate values require an explicit manual confirmation. Qualitative internal values accept only `적합`/`부적합`, and blank rows remain held.
- The local reducer fails closed for missing or trimmed-blank values/sources/reasons/evidence, non-authoritative selected roles, invalid source status, receipt/allocation LOT/quantity/unit mismatches, profile/version or canonical-trace drift, invalid/missing thresholds, incomplete internal confirmation, duplicate semantic relationships, and post-submit mutation.
- The value-complete local approval snapshot includes receipt/allocation, document values/evidence, confirmed matches, internal samples/specifications/thresholds/decisions, local calculation policy, overall decision/reasons/roles, and canonical trace. `buildFrozenSnapshot` is private/non-exported; the exact entire `internalTests` contract is validated; threshold keys serialize explicit `null`; and approved state/snapshot are recursively frozen. This is not a claim of a production DB snapshot, audit, RBAC, idempotency, or backend decision contract.

### Independent source and UI approvals

- Source approval: `APPROVE` (BLOCKER 0, MAJOR 0, MINOR 0). It independently verified the private snapshot builder, exact internal-tests contract, previous threshold/relationship/authority/snapshot closures, valid reducer approval, 31 focused existing tests, and an external 14-attack probe.
- Final narrow UI approval: `APPROVE` (HIGH 0, MEDIUM 0, LOW 0), on standalone BUILD_ID `yxIU8dalJEwMZG9Hg5YIz`. A fresh flow finalized document candidates, confirmed matching and both internal tests, reached `제출 준비`, submitted, switched to simulated LEAD, and reached `승인·동결`; frozen summary read back canonical LOT/specification and exact submission/review reasons.
- UI lock evidence: `SUBMITTED` disabled receipt 8/8, document 12/12, matching 1/1, internal 8/8, and submission 2/2 controls with no enabled business controls. `APPROVED` retained those locks and disabled team review 6/6. A true 390×844 viewport had inner/document/body width 390 with no page-level overflow.
- Both reviews verified the same source-only candidate before and after: 10-file manifest `5b7f222fa5bba991499c3be4e8b49231fba59bb66b1b50dcc1e43ed29ddb6335` (sorted path + NUL + hex SHA-256(file) + newline), `HEAD`/base/`origin/main` `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5`, and status digest `754834d90ae0c30075a0e611383abc9f99e6c157d335c7e6ddcd6ff8cb569692`. It is pre-documentation source evidence only, not a docs-inclusive final-manifest claim. Earlier `6b79...`, `4447...`, `0797...`, `987956...`, `b96da...`, and `97c508...` candidates are superseded and not final evidence.

### Controller verification before documentation

- `make bootstrap && make check` — exit 0. It covered backend pytest 172 passed (one upstream Starlette/httpx deprecation warning), Ruff, strict mypy across 15 files, compileall, generated-client drift, migrations, secret/sensitive scans, Compose config, frozen pnpm install, ESLint, next typegen, artifact-free tsc, frontend Vitest 3 files/32 tests, and production build.
- `git diff --check` — exit 0. The protected P0B importer and masked dry-run integration test were byte-identical to accepted base `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5`; isolated `/tmp/hanyang_p2` was not imported. The controller active public-surface probe also passed.

P0A/P0B/P1 remain complete/accepted and P2 remains authorized/not started. After documentation sync, `make bootstrap && make check` again exited 0 with backend 172/frontend 32 and the static/build/scan results, so the docs-inclusive controller gate passed. Feature commit `e79f00ca367bb43d3c0d370d228b9dad0e57e99c` was then fast-forwarded from fresh `origin/main` base `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5` into an isolated Orca integration worktree. The fresh tree passed frozen bootstrap and the full gate, standalone `/` and `/api/health` returned HTTP 200 on loopback BUILD_ID `U9jrUNlnVYwIknPKm1GwF`, desktop visual QA found no visible defect, true 390×844 QA measured inner/document/body width 390 with no page-level overflow, and the active adversarial probe passed 32 asserted results. Push-time fetch confirmed `origin/main` still equaled the expected base and was the merge base of the clean integration HEAD; the fast-forward delivery to `origin/main` and post-push remote equality/ancestry checks passed. This verified fixture increment does not complete P2, P3, backend/domain work, real auth, real production support, or deployment.
