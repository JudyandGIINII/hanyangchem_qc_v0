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

## 2026-08-01 — P2 pure-domain/DB implementation candidate

### Implemented candidate scope

- Ported the useful parts of the older read-only `/tmp/hanyang_p2` candidate onto current `origin/main` without overwriting the delivered FE8 frontend. Added standard-library-only Decimal/unit, specification selection, canonical LOT identity, judgment, workflow, canonical snapshot, stable failure-code, and lease-recovery contracts.
- Added the initial SQLAlchemy persistence models and frozen Alembic revision `20260731_0002`. This pre-review candidate attempted PostgreSQL serialization/immutability/privilege guards, but Claude later proved that its app role was not operationally representative, snapshot/finalization authority was incomplete, and DRAFT finalization remained possible. Those initial capability claims are retracted and superseded by the remediation entry below; the command measurements remain historical evidence only.
- Added portable boundary/state/constraint/idempotency/snapshot tests and PostgreSQL owner/app-role/concurrency/trigger tests. The PostgreSQL runner uses a unique Compose project, loopback-only random port, synthetic credentials, tmpfs storage, upgrade→downgrade→upgrade migration replay, and cleanup assertions.
- Preserved supplier specification/decision, HYC decision, and internal result paths as separate values. The engine emits only `ACCEPTED / REJECTED / ON_HOLD`; `RETEST / SPECIAL_ACCEPTED` remain workflow-only transitions requiring the quality-manager role, reason where applicable, and deterministic re-evaluation.

### Actual builder verification

- `uv lock --project backend --check` — exit 0; `XDG_CACHE_HOME="$PWD/.uv-cache" uv sync --project backend --extra dev` — exit 0.
- Focused portable P2 gate — `136 passed`; Ruff passed and strict mypy passed across 28 source files.
- `sh backend/scripts/run_p2_postgres_tests.sh` — exit 0: 7 PostgreSQL tests passed, followed by the explicit PostgreSQL migration upgrade→downgrade→upgrade cycle; the unique Compose container/network/volume cleanup assertions passed.
- `make check` — exit 0: contract/client drift, Ruff, strict mypy (28 source files), backend pytest `307 passed, 7 deselected` with one upstream Starlette/httpx warning, compileall, frontend lint/typegen/typecheck, frontend Vitest 3 files/`32 passed`, production build, migration contract `4 passed`, secret scan, sensitive-document scan, and Compose rendering all passed.
- Protected P0B SHA-256 values remain `61caebd06f8ee7697c77a2f3c07265e1578b10924fea6fbd74e53bd76f818e23` for `backend/scripts/import_spec_workbook.py` and `c0799b0413f093b06de41d56f9c27b20e388cb2448ef55e39de6e78120dba801` for its integration test, byte-identical to current `origin/main`.

### Gate and continuing boundary

This is `P2_IMPLEMENTATION_CANDIDATE_QA_PENDING`, not P2 complete or accepted. Hermes and Claude independent QA remain required, P3 remains blocked, and FE8 remains a separate verified fixture-only frontend increment. No real source PDF/XLS/XLSX content was accessed or copied; no real-data apply/import, external OCR/AI, non-disposable migration, Git add/commit/push/merge/reset/rebase/stash, deployment, or service exposure occurred.

## 2026-08-01 — P2 Claude review remediation candidate

Claude's read-only review returned `REQUEST_CHANGES` with 5 BLOCKER, 9 MAJOR, and 7 MINOR findings. The earlier P2 builder entry above is retained as historical measurement evidence, but its five capability claims about AP-03 identity, authoritative finalization, value-complete snapshots, exact/context-independent Decimal behavior, and realistic PostgreSQL privilege/finalization guards were overstated and are superseded by this remediation record.

The remediation implements the exact AP-03 v1 key and conflict evidence, LEAD-only separated quality approval with distinct ADMIN master-data participation only for LOT merge, persisted-input in-transaction re-evaluation, internally derived canonical snapshots with repository/PostgreSQL hash verification, versioned local Decimal context, realistic app-role DML/append-only privileges, ACTIVE/effective spec enforcement, bounded merged-LOT resolution, strict numeric persistence, DB allowlists/operator parity, coded optimistic/authorization failures, explicit BOTH_ALL and ON_HOLD precedence, SQLAlchemy versioning, the complete deterministic 15-state workflow, and every requested minor/negative gate. ADR 0003/0004, the integrated plan, traceability, Kanban, and the detailed closure artifact were synchronized.

Post-remediation verification (superseded by the final re-review remediation measurement below): `uv lock --project backend --check` and `uv sync --project backend --extra dev` exited 0; the final `make check` exited 0 with Ruff, strict mypy 28 files, backend 344 passed/9 PostgreSQL deselected, migration contract 4 passed, FE8 frontend 32 passed plus build, scans, and Compose rendering. The final disposable PostgreSQL runner exited 0 with 9 tests, upgrade→downgrade→upgrade, empty autogenerate diff, realistic privilege/denial probes, and empty container/network/volume cleanup inventory. `git diff --check` passed; protected P0B hashes remained byte-identical to `origin/main`; frontend/contracts/API/worker/fixtures had no diff.

Detailed finding-by-finding evidence is in `docs/reviews/2026-08-01-p2-claude-remediation.md`. State is `P2_CLAUDE_REVIEW_REMEDIATED_CANDIDATE_REREVIEW_PENDING`, not accepted or complete. No real source access, real-data apply/import, external OCR/AI, non-disposable migration, prohibited Git operation, deployment, or service exposure occurred.

## 2026-08-01 — P2 Hermes controller-QA H1 correction

Hermes controller QA found that finalization denied plain `ACCEPTED` only for a
re-evaluated `REJECTED` candidate, so a persisted fail-closed `ON_HOLD` candidate could
still be changed to plain `ACCEPTED` when a LEAD supplied a reason. The repository guard
now permits plain `ACCEPTED` only for an engine `ACCEPTED`; accepting either `REJECTED`
or `ON_HOLD` requires the existing reasoned `SPECIAL_ACCEPTED` state. A portable
repository regression creates `ON_HOLD` from missing required internal evidence, proves
plain acceptance is denied even with a reason and leaves zero partial mutation after
rollback, then proves reasoned special acceptance succeeds.

This targeted correction changes no migration, PostgreSQL SQL, privilege, API, contract,
worker, or frontend behavior. P2 remains a remediated candidate awaiting Hermes and
Claude re-review, not accepted or complete.

The new test first failed because the plain acceptance call did not raise. After the
repository guard correction, the focused adjacent approval slice passed 5 tests with 37
deselected. At the later N1/N2/N3 remediation checkpoint, `make check` passed with backend
344 passed/9 PostgreSQL deselected and the disposable PostgreSQL runner passed 9 tests plus
migration roundtrip and empty drift; the final-minor-hardening entry below supersedes those
historical counts.

## 2026-08-01 — P2 final Claude re-review N1/N2/N3 remediation candidate

N1 closed the remaining PostgreSQL-boundary gap: both persisted `REJECTED` and `ON_HOLD`
candidates are denied when a DB-direct transaction attempts plain `ACCEPTED`, even with a
reason. The regression failed against the pre-fix trigger (`DID NOT RAISE`), then passed
after the accepting-override predicate was expanded. It proves complete rollback of case
status/candidate/final/version plus snapshot, approval, audit, and outbox rows, with positive
controls for normal `ACCEPTED` and reasoned `SPECIAL_ACCEPTED`.

N2 carries the PRD receipt-lot nullable `model_id` on the normalized
`receipt_lot_allocations` record. Repository and PostgreSQL selection now match the pure
domain contract: unique highest specificity across material/supplier/model, nullable
fallback, ACTIVE/effective filtering, cross-model exclusion, and fail-closed equal-rank or
overlap ambiguity. Four focused portable repository tests cover those branches. N3 aligned
that checkpoint to `344 passed, 9 PostgreSQL deselected`; the final-minor-hardening entry
below supersedes those historical counts.

Final candidate verification: `uv lock --project backend --check`, focused N1/N2 tests,
`make check`, the 9-test disposable PostgreSQL runner with upgrade→downgrade→upgrade and
empty model/migration drift, contract/client drift, `git diff --check`, protected P0B byte
identity, scope inventory, and zero-container/network/volume cleanup all passed. P2 remains
an unaccepted candidate awaiting Hermes independent QA and fresh Claude source-diff
re-review; no P3, integration, push, deployment, real data, OCR, or AI action was performed.

## 2026-08-01 — P2 final minor hardening N-M1/N-M2 verified candidate

Claude's fresh read-only review passed with no blocker or major and identified two new
minors. N-M1 is closed by immutable follow-up migration `20260801_0003`, whose PostgreSQL
`BEFORE INSERT` guard rejects every inspection-case insert carrying a non-null
`final_decision`; downgrade removes only that trigger/function and returns to frozen
revision `20260731_0002`. The app-role regression first failed at `0002` with
`DID NOT RAISE` after the attack transaction supplied a hash-valid snapshot, distinct LEAD
approval, finalization audit, and outbox event; after `0003`, it passed with zero partial
case/evidence state, while a normal unfinalized insert committed.

N-M2 is closed by replacing the document transition `frozenset` scan with an ordered tuple
and a map keyed by `(current, target, role)`, plus import-time cardinality enforcement. The
focused matrix covers all 13 existing role paths, wrong-role denial, required-reason
semantics, and uniqueness. A dedicated pure-domain regression also proves supplier-only
and model-only scopes at equal specificity fail closed for the same matching context.

Current verification supersedes the earlier 344/9/28 and PostgreSQL 9 measurements while
retaining them above as historical evidence. `uv lock --project backend --check` and
`make check` exited 0: Ruff, strict mypy 29 files, backend `346 passed, 10 PostgreSQL
deselected`, migration contract 4, FE8 32 plus lint/typecheck/build, compileall,
contract/client drift, scans, and Compose rendering passed. The disposable PostgreSQL
runner exited 0 with 10 tests, upgrade→downgrade→upgrade, empty autogenerate drift, and
cleanup assertions. Frozen `20260731_0002` remained exactly
`546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`.

This is a verified P2 candidate awaiting final Hermes QA and a fresh Claude source-diff
review, not accepted, integrated, pushed, deployed, released, or P3-started. No real source
access, real-data apply/import, external OCR/AI, non-disposable migration, or prohibited Git
operation occurred.

## 2026-08-01 — P2 final source-gate acceptance

Independent Hermes QA is green, and the absolute-final Claude read-only source-diff review
at `/tmp/hyc-p2-absolute-final-claude-review.md` (SHA-256
`6a1ef045b9bbdfadb322a04819875a0b53ca2ec045bf09cfce8157918aa68848`) returned `PASS`:
BLOCKER 0, MAJOR 0, MINOR 1. B1–B5, M1–M9, m1–m7, H1, N1, N2, N3, N-M1, and N-M2
are closed. This entry supersedes the current-state pointers in the dated candidate entries
above; their measurements remain historical evidence.

The independently reproduced final gates were `make check` exit 0; backend `346 passed,
10 PostgreSQL deselected`; strict mypy 29 files; migration contract 4; FE8 frontend 32 plus
lint/typecheck/build; scans and Compose rendering; and the PostgreSQL runner's 10 passed plus
upgrade→downgrade→upgrade, empty drift, and cleanup inventory 0/0/0. Alembic head is
`20260801_0003`; frozen `20260731_0002` remains exactly
`546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`.

N-M3 is accepted follow-up/technical debt, not fixed. Its precondition is an app-role
DB-direct writer with broad direct INSERT/UPDATE on `inspection_cases` and INSERT on all
required append-only evidence tables. Such a writer can insert an unfinalized case already at
`LEAD_REVIEW` and finalize it with complete valid evidence, bypassing intermediate status
history; N1 decision integrity, mandatory evidence, and finalized-row immutability still hold.
Revisit this defense-in-depth gap before any production DB-role activation.

At this dated source-gate checkpoint, P2 was source-complete and accepted; that acceptance alone
did not authorize Git integration or remote publication. P3 and every production/operations gate
remained blocked and unapproved; no real-data apply/import, external OCR/AI, non-disposable
migration, deployment, or service exposure was performed.

## 2026-08-01 — P2 post-integration documentation closure

Under separate explicit user authorization, source commit `996056b` (`feat: implement P2 domain
and database invariants`) was fast-forward integrated from fresh `origin/main` baseline `1e96836`
into the clean fresh-main integration branch. Fresh integration QA passed: `make bootstrap` and
`make check` both exited 0, with backend `346 passed, 10 PostgreSQL deselected`, strict mypy 29,
migration contract 4, frontend 32 plus lint/typecheck/build, scans/Compose, disposable PostgreSQL
10 passed, and controller-verified cleanup. At this pre-push documentation edit, remote delivery
had not yet occurred. P3 remains blocked/not authorized; real-data apply/import, external OCR/AI,
non-disposable migration, deployment, release, and service exposure remain unauthorized. N-M3
remains accepted and unfixed for review before production DB-role activation.

## 2026-08-01 — P2 first-push verification and post-push documentation reconciliation

The first authorized push delivered range `1e96836..58e963c` to `origin/main`. Fetch/readback
equality verified `origin/main` at `58e963c`, and ancestry verification proved source commit
`996056b` is an ancestor of that delivered remote state. Therefore `58e963c` is the verified
first-push/integration-evidence commit and a durable ancestor, not a continuing/current/live final
tip. This uncommitted post-push documentation reconciliation, when later controller-committed and
pushed, will become a later descendant and final remote tip; Git history is authoritative for the
current live tip. P2 remains complete, accepted, committed, fresh-main integrated, and delivered
to `origin/main` under separate explicit user authorization. P3 remains blocked/not authorized;
N-M3 remains accepted and unfixed before production DB-role activation; real-data apply/import,
external OCR/AI, non-disposable migration, deployment, release, operations, and service exposure
remain unauthorized and unperformed.

## 2026-08-01 — P3 vertical-slice implementation candidate builder verification

The separately authorized P3 work was continued in the isolated worktree at exact unchanged
base `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`. The inherited uncommitted implementation
adds Alembic head `20260801_0004`, PostgreSQL-backed FastAPI intake/document/inspection/LOT
routes and services, fixture-only local actors with RBAC, OpenAPI/generated-client updates, an
API-backed Next.js inspection workspace, a synthetic calcium-chloride-bead seed, disposable
PostgreSQL integration coverage, and three Playwright scenarios. All changes remain uncommitted.

The first observed `make p3-e2e` run failed all three scenarios because randomized loopback web
ports were rejected by API CORS preflight. Fixture mode now permits only HTTP `localhost` or
`127.0.0.1` origins on an explicit port pattern; normal mode retains its configured exact-origin
policy. A later P2 PostgreSQL run exposed a migration portability error because `0004` granted to
an absent default app role; the migration now grants only when the configured, identifier-validated
role exists and never creates or activates a production role. Both failed Compose projects were
torn down and verified empty. Subsequent E2E/full-suite output was redirected to `/tmp` logs and
only concise failure/pass summaries were inspected.

The unchanged secret scanner then correctly rejected credential-like assignment names in the
fixture-session contract and locals. The scanner was not edited, weakened, bypassed, or given a
path exclusion. Non-secret fixture session values were renamed to `session_handle` throughout the
API, OpenAPI contract, regenerated TypeScript client, frontend, and tests while preserving Bearer
`Authorization` behavior; `python3 scripts/scan_secrets.py` and the full gate then passed. Hermes
explicitly approved the two cumulative-test updates: the extraction port now expects authorized P3
`REVIEW_REQUIRED`, and the P2 portable NUMERIC inventory now includes persisted extraction review
confidence.

Approval handling was tightened before final verification. A stale approval `If-Match` now returns
409, and approval re-evaluation, approval, decision snapshot, audit, outbox, plus completion of the
approval idempotency record are committed in one transaction. Fault injection proves zero partial
approval/snapshot/audit/outbox/idempotency state; replay proves one approval/snapshot/completed
idempotency result. The PostgreSQL-marked P3 suite also covers checksum dedupe, internal-test hold,
separate-actor RBAC, split-LOT trace, revision/retest lineage, and finalized-evidence immutability.

Final commands actually observed from the repaired source state:

- `make bootstrap` — exit 0; backend resolution/check and frozen pnpm install completed.
- `make check` — exit 0: Ruff, strict mypy 39 source files, backend `346 passed, 16
  deselected` with one upstream Starlette/httpx deprecation warning, frontend lint/typecheck/build
  and Vitest 3 files/`32 passed`, migration contracts `4 passed`, OpenAPI/generated-client drift,
  secret scan, sensitive-document scan, and Compose rendering passed.
- `make p2-postgres-check` — exit 0: 10 PostgreSQL tests plus the disposable migration
  upgrade→downgrade→upgrade/drift checker passed. Project
  `hyc-p2-test-1785566649-48124` left containers/networks/volumes `0/0/0`.
- `make p3-postgres-check` — exit 0: 6 PostgreSQL tests (one upstream warning) plus the
  disposable migration upgrade→downgrade→upgrade/drift checker passed. Project
  `hyc-p3-pg-1785566670-48655` left containers/networks/volumes `0/0/0`.
- `BUILDKIT_PROGRESS=plain make p3-e2e` — exit 0: Playwright `3 passed` against loopback
  disposable PostgreSQL/FastAPI/Next.js, using neither interception/mocks nor SQLite/in-memory
  persistence. Project `hyc-p3-e2e-1785566695-49210` left containers/networks/volumes `0/0/0`.
- `git diff --check` — exit 0. The changed-path inventory matched the approved cumulative
  allowlist, including the two explicitly approved cumulative-test paths; no unignored
  `__pycache__`, `.pyc`, `.next`, Playwright report/result, or `node_modules` noise was present.

This is `P3_IMPLEMENTATION_CANDIDATE_BUILDER_VERIFIED_HERMES_QA_PENDING`. It is not P3
accepted, integrated, committed, pushed, deployed, released, or production-ready. Hermes
independent QA/review/integration remains required. P2 N-M3 remains accepted and unfixed and must
be revisited before production DB-role activation. No real PDF/XLS/XLSX, real-data apply/import,
external OCR/AI/NAS/Drive/ERP, non-disposable database, public exposure, deployment, release,
secret, or prohibited Git operation was used or performed.

## 2026-08-01 — P3 completion-remediation implementation candidate builder verification

Hermes independently reproduced three integration blockers and dispatched a bounded remediation
against the existing uncommitted P3 candidate at unchanged base
`b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`. Tests were added first; the initial disposable
PostgreSQL run reproduced all three product defects as four focused failures: cross-allocation
inspection creation returned 201, the second internal-result PUT returned 500, finalized evidence
INSERT was accepted, and the original unfinalized positive-control query needed an explicit
PostgreSQL type-safe form. Every failed disposable project executed its cleanup trap.

The remediation makes the reviewed extraction document's confirmed section→allocation link
authoritative before inspection idempotency reservation. A mismatch returns the stable 409 message
`Extraction allocation lineage mismatch`, persists no inspection/idempotency/audit/outbox/snapshot
effect, and the same key can then create against the correctly linked allocation. Internal-result
PUT now rejects duplicate submitted spec IDs, retains one row per case/spec through a database
unique constraint, replaces the exact sample indexes/values through per-parent uniqueness, and
always advances the case optimistic version for a successful unfinalized replacement; stale
`If-Match` remains 409 and database integrity errors are not converted to success.

Alembic head `20260801_0004` now guards supplier results, internal results, and sample measurements
on INSERT, UPDATE, and DELETE whenever either the OLD or NEW linked case is finalized. DELETE
returns OLD and INSERT/UPDATE return NEW. Distinct disposable `hyc_app_test` tests deny all three
verbs and both relinking directions with zero residue, while unfinalized insert/update/delete
controls commit successfully and clean up their rows. Frozen P2 migrations `20260731_0002` and
`20260801_0003` remain byte-identical; N-M3 remains accepted and unfixed.

Final commands actually observed from the remediation candidate:

- `make bootstrap && make check` — exit 0: Ruff, strict mypy 39 files, backend `346 passed,
  20 PostgreSQL deselected`, frontend lint/typegen/typecheck/Vitest 32/build, migration contracts
  4, generated-contract drift, secret/sensitive-document scans, and Compose rendering passed.
- `make p2-postgres-check` — exit 0: 10 PostgreSQL tests and disposable migration
  upgrade→downgrade→upgrade/drift verification passed.
- `make p3-postgres-check` — exit 0: 10 PostgreSQL tests, including exact-lineage, repeat-PUT,
  finalized app-role negative, relinking, and unfinalized positive controls, plus disposable
  migration upgrade→downgrade→upgrade/drift verification passed.
- `make p3-e2e` — exit 0: Playwright 3/3 passed against loopback disposable
  PostgreSQL/FastAPI/Next.js without interception, mocks, SQLite, or in-memory persistence.
- `git diff --check`, frozen-migration SHA-256 verification, sensitive/secret scans, artifact scan,
  changed-path inventory, and the aggregate disposable Compose project inventory all passed; every
  P2/P3/E2E project left containers/networks/volumes `0/0/0`.

This remains `P3_IMPLEMENTATION_CANDIDATE_BUILDER_VERIFIED_HERMES_QA_PENDING`: an uncommitted
remediation candidate awaiting Hermes independent QA/review/integration. It is not accepted,
integrated, committed, pushed, deployed, released, production-ready, or authorization for real
data, external OCR/AI, non-disposable migration, public exposure, or production DB-role activation.

## 2026-08-01 — P3 second security remediation implementation candidate

The final independent Claude backend/DB/security review returned `REQUEST_CHANGES` with B-1,
M-1, and M-2 plus five minors. Tests were added first. A disposable PostgreSQL red run then
proved that a CONFIRMED run returned 200 for a field rewrite/reconfirmation, `{MOISTURE}` followed
by `{PURITY}` retained both rows, and inspection GET emitted derived UPDATE statements. The first
test draft also exposed and corrected one UUID/string assertion mismatch without weakening the
product regressions. Every red-run project and its explicitly scoped wrapper temp tree was removed.

B-1 and M-1 are closed at the shared root. `confirm_review` accepts only `REVIEW_REQUIRED`, so a
CONFIRMED run cannot be reconfirmed with the same allocation, rebound to another allocation, or
have `manual_text`/`final_text`/source/reason rewritten. The first clean confirmation still creates
one confirmed section link. The API locks and checks existing confirmed links, and Alembic head
`20260801_0004` plus ORM metadata add the partial unique index
`uq_document_section_one_confirmed_allocation`, independently rejecting a second confirmed
allocation for the section. Tests prove unchanged fields/link cardinality, unrelated-LOT rejection
with no case/audit/outbox/snapshot/idempotency residue, and successful creation for the original
allocation using the same idempotency key.

M-2 is closed with true collection replacement. The API validates duplicate and foreign spec IDs
before mutation, deletes every existing sample, deletes results omitted from the submitted set,
then recreates exactly the submitted sample indexes and values. `results: []` is schema-valid and
clears all internal evidence on an unfinalized case. Regressions cover `{MOISTURE}` then `{PURITY}`
leaving only PURITY, wrong-spec correction back to MOISTURE, exact samples, empty clear, fresh and
stale `If-Match`, version advancement, fail-closed re-evaluation and submit rejection after clear,
and the pre-existing finalized immutability/no-500 controls.

N-3 is closed: inspection GET calls `evaluate_inspection(..., persist=False)`, and the
non-persisting path no longer dirties derived supplier/internal decisions. A PostgreSQL statement
listener proves the GET emits no INSERT, UPDATE, or DELETE. N-4 is closed: `p3-postgres-check`
creates a named exact `mktemp` storage tree, recursively deletes only that quoted path with `find
-depth -delete`, and asserts the path does not exist before its container/network/volume checks.
N-1 request-validation ordering, N-2 fixture GET seeding, and N-5 fixture-session eviction remain
disclosed fixture-mode-only follow-ups; no architecture was broadened to remove them.

Commands actually observed from the second-remediation candidate:

- `make bootstrap && make check` — exit 0: backend `346 passed, 23 PostgreSQL deselected`,
  strict mypy 39 files, Ruff/compileall, frontend lint/typegen/typecheck/Vitest 32/build,
  migration contracts 4, generated OpenAPI/client drift, scans, and Compose rendering passed.
- `make p2-postgres-check` — exit 0: 10 passed; project
  `hyc-p2-test-1785576529-12845` cleaned its exact Compose resources.
- `make p3-postgres-check` — exit 0: 13 passed, including confirmation terminality/link
  cardinality, collection replace/clear, mutation-free GET, and previous P3 controls; project
  `hyc-p3-pg-1785576792-20696` removed its exact storage tree and Compose resources.
- `make p3-e2e` — exit 0: Playwright 3/3 passed against loopback PostgreSQL/FastAPI/Next.js;
  project `hyc-p3-e2e-1785576558-13694` cleaned its exact Compose resources.
- Final `git diff --check`, frozen-migration byte-identity, secret/sensitive-document scans,
  changed-path/artifact inventory, and exact Docker/temp cleanup inventory passed.

This second remediation is still an uncommitted builder-verified candidate at
`P3_IMPLEMENTATION_CANDIDATE_BUILDER_VERIFIED_HERMES_QA_PENDING`. It does not claim Hermes
acceptance, integration, commit, push, deployment, release, production readiness, or authority for
real data, external OCR/AI, non-disposable migration, public exposure, or production role use.

## 2026-08-01 — P3 final polish (historical N-7 evidence later superseded)

Tests were added before implementation. The first disposable PostgreSQL run failed four focused
regressions: the forced simultaneous first-confirmation loser returned 500, replace and clear audit
payloads contained only `result_count`, and an internal-result update left the case at
`LEAD_REVIEW`. The pre-fix browser source likewise showed that the prominent badge and polite live
region remained bound to the local fixture reducer and could still announce `검토 필요` after the
server inspection reached `ACCEPTED`.

The UI now derives one shared display string from the authoritative inspection status whenever an
inspection exists, retaining the localized label and code (`승인 완료 · ACCEPTED`) after approval
and LOT trace; the no-inspection path explicitly identifies itself as pre-creation guidance. The
happy-path Playwright test checks the visible badge, accessible polite live region, absence of the
stale review label, visible controls, and no document-level overflow after switching to 375×812.

N-7 was provisionally considered closed by catching the named PostgreSQL partial-unique collision at the
confirmation commit boundary, rolling back the complete losing transaction, and returning the
stable 409 `Document section already has a confirmed allocation`. A barrier at the two competing
link INSERTs proves one 200, one 409, no 500, one confirmed link, unchanged losing run and field
reviews, no losing confirmation audit, and no additional inspection, snapshot, outbox, material LOT,
or allocation lineage. Independent QA later showed that pre-inserting the section made this
regression insufficient; the genuine first-section race and current evidence are recorded below.

N-6 is closed without raw quality values in audit. Each successful internal-results collection
replacement records sorted requested, retained, and removed spec item IDs plus deleted-result and
deleted-sample counts. Regressions cover retained-row sample replacement, cross-spec replacement,
and empty clear. Any such evidence update from `LEAD_REVIEW` now returns the unfinalized case to
`READY_FOR_REVIEW` or `INTERNAL_TEST_PENDING`; fresh approval cannot finalize until the inspection
is validly resubmitted, and cleared evidence remains fail-closed.

Commands actually observed for this final-polish candidate:

- Red `make p3-postgres-check`: 11 passed and 4 expected focused failures; its disposable cleanup
  trap ran.
- Targeted real-PostgreSQL concurrency/audit/eligibility command: 4 passed, 5 deselected; exact
  cleanup reported containers/networks/volumes/storage `0/0/0/0`.
- `make bootstrap && make check`: exit 0; backend `346 passed, 25 PostgreSQL deselected`, Ruff,
  strict mypy 39, compileall, frontend lint/typegen/typecheck/Vitest 32/build, migration contracts
  4, generated-contract drift, secret/sensitive scans, and Compose rendering passed.
- `make p2-postgres-check`: 10 passed. `make p3-postgres-check`: 15 passed. Both disposable
  migration and cleanup gates passed.
- `make p3-e2e`: Playwright 3/3 passed against loopback PostgreSQL/FastAPI/Next.js without route
  interception, mock persistence, SQLite, or in-memory persistence; its exact Compose resources
  were removed.
- The same loopback stack then ran the targeted authoritative-status happy-path spec 1/1 and
  reported exact containers/networks/volumes cleanup `0/0/0`.
- Frozen `20260731_0002` and `20260801_0003` SHA-256 values remained
  `546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82` and
  `8124e6420c72cca5f63bd6999116350edd8e6d00214ecd2de471ba9b4c2ea9ee`.

Fixture-only N-1 validation ordering, N-2 GET seeding, and N-5 session eviction remain disclosed
follow-ups. This remains an uncommitted builder-verified P3 candidate pending Hermes independent
QA/review/integration; it is not accepted, integrated, committed, pushed, deployed, released, or
production-ready, and it does not authorize real/external data or services.

## 2026-08-01 — P3 last blocker: genuine empty-section first-confirm race

Independent final QA reopened M-1/N-7 after proving that the earlier concurrency regression
pre-inserted `document_sections` and therefore tested only the link partial index. The replacement
PostgreSQL regression begins with zero sections, synchronizes the two competing first section
INSERTs, and is parameterized five times. Before implementation it failed deterministically 5/5
with one 200 and one 500 from `uq_document_section_index`.

`confirm_review` now covers both the lazy section flush and final commit with one rollback-first
`IntegrityError` boundary. It maps only `uq_document_section_index`,
`uq_document_allocation_link`, and `uq_document_section_one_confirmed_allocation` to the stable 409;
all unrelated database errors still re-raise. The dead `run.conflicts = conflicts` assignment was
removed because the 422 path always rolls the transaction back.

Every green race asserts exactly one 200 and one 409, no 500, exactly one section and confirmed
link, unchanged loser run/version/conflicts and all loser review fields, no loser confirmation
audit, and no new inspection, material LOT, inbound receipt, allocation, merge approval, decision
snapshot, outbox, or idempotency residue.

Commands actually observed for this remediation candidate:

- Pre-fix targeted genuine-race run: 5 failed, each with `[200, 500]`; disposable PostgreSQL and
  storage cleanup passed.
- Post-fix targeted genuine-race runs: three successive invocations, each 5 passed (15/15 total);
  disposable PostgreSQL and storage cleanup passed.
- `make bootstrap && make check`: exit 0; backend `346 passed, 29 PostgreSQL deselected`, Ruff,
  strict mypy 39, compileall, frontend lint/typegen/typecheck/Vitest 32/build, migration contracts
  4, generated-contract drift, secret/sensitive scans, and Compose rendering passed.
- `make p2-postgres-check`: 10 passed. `make p3-postgres-check`: 19 passed, including five genuine
  first-confirm races. Both migration and exact cleanup gates passed.
- `make p3-e2e`: Playwright 3/3 passed against loopback PostgreSQL/FastAPI/Next.js, followed by
  exact disposable Compose cleanup.

The independently reported M-1/N-7 blocker is closed in this uncommitted builder candidate only.
Hermes independent QA/review/integration remains pending; no acceptance, Git integration, push,
deployment, release, production readiness, real data, or external service use is claimed.

## 2026-08-01 — P3 final remediation: concurrent idempotency and upload input contract

Tests were added first. The red canonical PostgreSQL run reported `20 failed, 19 passed`: all 18
genuine missing-row first-reservation cases (five same-payload attempts plus one different-payload
attempt for each of intake, inspection creation, and approval) reproduced success+500, and empty
and over-10-MiB uploads both returned generic 500. Its cleanup inventory was
containers/networks/volumes/storage `0/0/0/0`.

`reserve_idempotency` now inserts inside a nested transaction/savepoint. Only
`uq_idempotency_principal_scope_key` is classified; after the savepoint rollback the loser reads
the committed competing row, returns 409 `Idempotency request is already pending` for the same
hash or 409 `Idempotency key request conflict` for another hash, and never masks an unrelated
constraint. Inspection reservation moved before its lineage row lock so the real first-reservation
race can occur, while lineage failure still rolls the outer transaction back and leaves zero
inspection/idempotency/audit/outbox/snapshot residue. Stored response ordering now preserves the
first response so the winning-payload sequential replay is byte-for-byte identical.

Streaming storage raises typed empty and over-limit errors instead of `ValueError`. The document
route maps them through the normal non-sensitive envelope to 422 and 413. The exact temporary file
is always removed; when an invalid request created a previously absent storage root, that root is
removed if still empty. The 10 MiB streaming limit and checksum-deduplicated successful upload path
are unchanged. The unused `atomicity_counts` helper and its now-unused model imports were removed
after repository-wide search found no caller or documentation dependency.

Commands actually observed for this remediation candidate:

- Red `make p3-postgres-check`: 18 synchronized idempotency races failed as success+500 and both
  invalid uploads failed as 500; the 19 prior PostgreSQL tests passed.
- Final focused disposable PostgreSQL command over `test_idempotency_races.py` and
  `test_document_dedup.py`: 22 passed. It covers 15 repeated same-payload races, three
  different-payload races, unrelated-integrity allowlist behavior, concurrent checksum dedupe,
  and empty/over-limit uploads.
- `make bootstrap && make check`: exit 0; backend `346 passed, 50 PostgreSQL deselected`, Ruff,
  strict mypy 39, compileall, frontend lint/typegen/typecheck/Vitest 32/build, migration contracts
  4, OpenAPI/generated-client drift, secret/sensitive scans, and Compose rendering passed.
- `make p2-postgres-check`: 10 passed. `make p3-postgres-check`: 40 passed. Across the final
  focused and full runs, the 30 same-payload attempts produced intake 201+409, inspection
  201+409, and approval 200+409; six different-payload attempts produced success+409 conflict,
  with no race 500 and one completed row/business effect each.
- `make p3-e2e`: Playwright 3/3 passed against loopback PostgreSQL/FastAPI/Next.js. Frozen P2
  migration SHA-256 values remained `546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`
  and `8124e6420c72cca5f63bd6999116350edd8e6d00214ecd2de471ba9b4c2ea9ee`.
- Final `git diff --check`, explicit contract/scans, and exact disposable cleanup inventory passed;
  containers, networks, volumes, P3 test storage roots, and invalid-upload roots were all zero.

This is still an uncommitted builder-verified P3 implementation candidate at
`P3_IMPLEMENTATION_CANDIDATE_BUILDER_VERIFIED_HERMES_QA_PENDING`. Hermes independent
QA/review/integration remains. Fixture-only N-1 validation ordering, N-2 GET seeding, and N-5
session eviction remain disclosed; there is no acceptance, integration, commit, push, deployment,
release, production-readiness, real-data, external OCR/AI, n8n, or production-role claim.
## 2026-08-01 — P3 final DB serialization/immutability remediation candidate

- Scope stayed inside the authorized isolated P3 worktree. No add/commit/push/merge/reset/restore/stash/rebase/deploy, real source evidence, external OCR/AI, non-disposable database, public exposure, or n8n mutation occurred.
- Red-first PostgreSQL reproduction paused approval after snapshot construction. A concurrent app-role supplier INSERT committed before approval and produced snapshot/live divergence; a supplier UPDATE also committed without waiting on the case. Confirmed extraction fields and allocation lineage likewise had no DB terminal guard.
- Alembic `20260801_0004` now makes every supplier/internal/sample I/U/D trigger resolve old/new case identities, lock the distinct parent cases in UUID order, and only then check `final_decision`. Approval already holds the same case row `FOR UPDATE`, so the allowed histories are evidence-before-approval (included on re-read) or approval-before-evidence (stable immutable rejection).
- Four extraction-lineage trigger families cover extraction runs, field reviews, document sections, and allocation links. They resolve both old/new run or document identities, lock authoritative extraction runs in deterministic order, and reject every mutation once any relevant run is `CONFIRMED`. A partial unique index enforces one confirmed extraction run per document; downgrade removes all four new triggers/functions and both P3 partial indexes are checked through runtime migration contracts.
- `confirm_review` locks all extraction runs for its document in UUID order, performs and flushes field/section/link work while the authoritative run is still pending, then performs the single legitimate `REVIEW_REQUIRED → CONFIRMED` update. Exact unique-constraint allowlisting now includes the confirmed-run index, preserving stable API 409 behavior for competing confirmations without masking unrelated integrity errors.
- `backend/tests/integration/api/test_db_serialization.py` passes 27 tests. Nine evidence I/U/D families run two fresh cycles each (18 approval races); 16 extraction run/field/section/link I/U/D/reparent families run two fresh cycles each (32 confirmation races). PostgreSQL `pg_blocking_pids` is the deterministic barrier: each forced-after-terminal app-role writer is proven blocked on the authoritative parent, then rejected by `finalized inspection evidence is immutable` or `confirmed extraction lineage is immutable` after the terminal transaction commits. No race returns 500 or leaves residue.
- Positive/rollback controls prove pending direct I/U/D remains legal, legitimate confirmation remains atomic, a missing-allocation confirmation rolls back all field/status/link changes, and a direct app-role confirmed allocation-link rebind to another LOT is rejected without changing lineage. Existing five-cycle first-confirmation and API rewrite/rebind regressions remain green under parent-run serialization.
- Verified commands on the final candidate: `make bootstrap && make check`; `make p2-postgres-check`; `make p3-postgres-check`; `make p3-e2e`; focused 27-test serialization suite; PostgreSQL migration upgrade→downgrade→upgrade/runtime-object/empty-drift check; `git diff --check`; generated OpenAPI/client drift; secret and sensitive-document scans. Results: backend `346 passed, 77 PostgreSQL deselected`, strict mypy 39 files, frontend Vitest 32 plus lint/typecheck/build, migration contract 4, P2 PostgreSQL 10, P3 PostgreSQL 67, Playwright 3/3, and exact disposable cleanup 0 containers/0 networks/0 volumes/0 storage trees.
- Gate remains `P3_IMPLEMENTATION_CANDIDATE_BUILDER_VERIFIED_HERMES_QA_PENDING`. This is uncommitted and awaiting Hermes independent QA/review/integration; it is not accepted, integrated, pushed, deployed, released, or production-ready. Fixture-only N-1 validation ordering, N-2 GET seeding, and N-5 session eviction remain explicit non-production debt; accepted P2 N-M3 remains a separate pre-production DB-role follow-up.

## 2026-08-01 — P3 final independent source acceptance and documentation truth sync

- Final independent backend review returned `PASS` with blocker 0, major 0, and medium 0. It passed P3 PostgreSQL 67, a mutation-first reverse-order probe for 6 cycles, the terminal-first focused 27-test suite, P2 PostgreSQL regression 10, and substantive gates with backend 346 passed/77 PostgreSQL deselected, strict mypy 39 files, frontend Vitest 32, and migration contract 4.
- Final independent UI/API review returned `PASS`. Real `make p3-e2e` passed Playwright 3/3; a separate real live-stack HTTP/browser smoke passed on desktop and 375×812. Concurrent status pairs were exactly 201+409 for intake, 201+409 for inspection, and 200+409 for approval; completed sequential replay was byte-identical; empty/over-limit uploads returned 422/413 with no residue; P3 API 67, repository fingerprint, and cleanup 0/0/0/0 remained green.
- Hermes controller independently passed `make bootstrap && make check` (Ruff; strict mypy 39; backend 346/77 deselected; frontend Vitest 32; Next build; migration 4; scans and Compose), P2 PostgreSQL 10, P3 PostgreSQL 67, real Playwright 3, and `test_db_serialization.py` 27 tests across three fresh cycles (81 total). The candidate hash remained frozen during this QA; final HYC Docker containers/networks/volumes were 0/0/0 and only user-owned n8n remained running and untouched.
- All historical blocker/major findings are fixed: cross-LOT lineage; repeated internal-result replace/clear; finalized evidence I/U/D; reconfirm and confirmed-review DB immutability; genuine first-confirm race; no-row idempotency races; invalid-upload mapping/residue; approval/evidence serialization; confirmed extraction run/field/section/link serialization; and confirmed cross-LOT rebind denial.
- The pre-doc-final freeze was base HEAD `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`, 50 changed/untracked files, and source hash `51f3bbb1d23970484813e893e51fd781f89fb781d02fac2db5cb475b00cac7f2`. This documentation sync changes the tree, so that value is deliberately recorded only as the frozen pre-doc source hash, not a post-doc hash.
- P3 is now source complete/accepted and ready for an exact-candidate commit followed by fresh-main fast-forward integration. At this documentation point it remains uncommitted, unintegrated, and unpushed; no deployment, release, public service, real-data import/apply, external OCR/AI, production migration, or production DB-role activation is authorized or performed.
- At this historical P3 source-acceptance checkpoint, accepted non-production debt remained fixture-only N-1 validation/auth ordering, N-2 GET seeding, N-5 in-memory session eviction, and the separate P2 N-M3 broad direct-role history-bypass warning; P4/P5 were then unstarted and all real data remained prohibited. Current P4-A state is recorded in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md); those records supersede only this checkpoint's P4-A state.
- Created `docs/HANDOFF.md` with the exact worktree/branch/base, delivered scope, architecture/synthetic boundary, canonical commands, verified counts, invariant enforcement/tests, accepted debt, Git state, safe next steps, and forbidden operations.
- Documentation validation commands actually run: `git diff --check`; `python3 scripts/scan_secrets.py`; `python3 scripts/check_sensitive_documents.py`; README local-link existence check; and a current-state truth scan over README, PRD, KANBAN, traceability, integrated plan, and handoff. All returned exit 0; the secret scan and tracked-sensitive-document scan printed their explicit pass messages.

## 2026-08-01 — P3 post-integration and remote-delivery closure

- P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442` is `feat: complete P3 vertical slice` and contains exactly 52 files, 8911 insertions, and 119 deletions. Its parent/fresh integration baseline is `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`.
- Before integration, local `main` and `origin/main` both equaled the baseline and main was clean. The authorized integration command was `git merge --ff-only 91465f0413d0c0ca2633577078ec1300a6096442`; it succeeded as a pure fast-forward with no merge commit or rebase.
- Commands actually run on fresh integrated main were `make bootstrap`, `make check`, `make p2-postgres-check`, `make p3-postgres-check`, and `make p3-e2e`. All passed: Ruff; strict mypy 39; backend 346 passed/77 deselected; frontend Vitest 32 and Next production build; migration contract 4; secret/sensitive-document scans and Compose rendering; P2 PostgreSQL 10; P3 PostgreSQL 67; real Playwright 3/3.
- Integrated-gate teardown left HYC Docker containers/networks/volumes at 0/0/0. The only running container was user-owned n8n, which remained untouched.
- The authorized `git push origin main` succeeded with `b7bc4a8..91465f0 main -> main`. After `git fetch origin`, `git rev-parse main`, `git rev-parse origin/main`, and `git ls-remote origin refs/heads/main` all resolved remote/main truth to `91465f0413d0c0ca2633577078ec1300a6096442`. `git merge-base --is-ancestor b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf origin/main` and `git merge-base --is-ancestor 91465f0413d0c0ca2633577078ec1300a6096442 origin/main` both succeeded. Main and candidate worktrees were clean at post-push closure before this documentation-only reconciliation. Git history is authoritative for the live tip.
- Current implementation state is `P0A_P0B_P1_P2_P3_SOURCE_COMPLETE_ACCEPTED_P3_DELIVERED_TO_ORIGIN_MAIN`. This closure does not authorize or claim deployment, release, public exposure, real-data import/apply, external OCR/AI, production/non-disposable migration, production DB-role activation, P4/P5 start, or production readiness. Fixture-only N-1 validation/auth ordering, N-2 GET seeding, N-5 in-memory session eviction, and P2 N-M3 remain accepted debt for review before production activation.
- Post-push documentation truth reconciliation changed only `AGENTS.md`, `Prd.md`, `README.md`, `docs/HANDOFF.md`, `docs/KANBAN.md`, `docs/DEVLOG.md`, `docs/TRACEABILITY_MATRIX.md`, and `docs/plans/2026-07-30-integrated-implementation-plan.md`. `git diff --check`, `python3 scripts/scan_secrets.py`, and `python3 scripts/check_sensitive_documents.py` each exited 0; the scanners printed `secret scan passed` and `tracked sensitive document scan passed`.

## 2026-08-02 — P4 kickoff documentation preparation

- Historical preparation snapshot: added the authoritative [P4 kickoff plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md) and synchronized [`HANDOFF.md`](HANDOFF.md), `docs/KANBAN.md`, and `docs/TRACEABILITY_MATRIX.md`. At that checkpoint this was a documentation-only preparation increment and P4 application code/tests were unstarted; the current handoff/P4 plan supersedes that state without changing the historical fact.
- Preserved P3 closure truth: source commit `91465f0413d0c0ca2633577078ec1300a6096442` remains accepted, fresh-main fast-forward integrated, and delivered to `origin/main`. The clean starting HEAD observed for this isolated documentation worktree was `f3020e2fe90996de9b5b0e502da4360976db0a9f`, with P3 ancestry verified. That SHA is only a capture-time baseline before any later documentation commit and is not claimed as the continuing live tip or final commit.
- Historical kickoff lane status: P4-A offline/synthetic foundation was `READY_TO_START_IN_NEW_SESSION`; P4-B was `BLOCKED_QUALITY_CORPUS_APPROVAL`; P4-C was `BLOCKED_AP02_PROVIDER_OPT_IN`. Current P4-A status is in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md); those records supersede only its old readiness state. P4-B corpus approval cannot authorize external Provider transmission, and a Provider-specific opt-in cannot establish corpus representativeness.
- Recorded a strict versioned golden/schema/artifact contract; deterministic exact/normalized/row/numeric/unit/LOT/required-missing/page/polygon metric formulas; denominator, duplicate, ignored-field and allowed-normalization handling; immutable version bindings/report digest; suggested ownership/path boundaries; synthetic edge matrix; approval packets; verification order; stop/rollback rules; and a copy/paste next-session prompt.
- Inspected the current extraction seam before planning: `backend/src/hyc_api/extraction.py`, `backend/src/hyc_api/contracts.py`, and `backend/tests/contract/test_extraction_contract.py`. `ExtractionCandidate.provider_name` is currently the synthetic-only `Literal["synthetic-fixture"]`; the plan requires a deliberate backward-compatible contract and generated schema/OpenAPI/client drift design if provider identity/versioning is introduced.
- Historical observation: confirmed that `make p4-golden-check` and `make p4-benchmark-fixture` did not exist at that kickoff handoff and were planned first-slice outputs. Their implemented/final evidence is recorded in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md). CI remains fixture-provider-only, network-free, credential-free, and deterministically ordered with stable clocks.
- No real representative corpus approval was evidenced, no Provider-specific AP-02 opt-in was granted, and no real PDF/XLS/XLSX body or external OCR/AI call was used. No application/test/fixture/dependency/migration/script/configuration/credential path was edited.
- No add, commit, push, merge, rebase, reset, restore, stash, deploy, main/shared-CWD mutation, production/non-disposable migration, production DB-role activation, public exposure, n8n change, real-data import/apply, or external transmission was performed by this writer. At that historical checkpoint, the user had authorized Hermes/controller to QA and deliver the preparation handoff with a normal commit and non-force push; current P4-A acceptance/delivery state is recorded in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).

## 2026-08-02 — P4-A Offline/Synthetic source acceptance and documentation truth sync (historical pre-final-review checkpoint)

- Implemented the P4-A offline/synthetic foundation only: strict/versioned golden, fixture, stage, candidate, report, and benchmark-output schemas; canonical JSON plus Decimal/SHA-256 digest chaining; exact dataset/stage/candidate/report/output binding, cardinality, and order; and a deterministic eight-stage runner with fail-closed upstream propagation and stage/error compatibility.
- Candidate payloads are stored independently and runtime never copies golden answer keys. The accepted nontrivial report has exact field 35/44, one page mismatch, one non-unit IoU, and exercises duplicate, unmapped, unapproved-normalization, and value-mismatch paths. Candidate-observed warnings, canonical warning/error order, and the absence of warnings on skipped/unsupported failed stages are covered.
- The executable 20-edge matrix binds disjoint `CANDIDATE_ONLY`, `REVIEW_REQUIRED`, `MANUAL_FALLBACK`, and `STABLE_FAILURE` dispositions to exact reason codes. Metrics cover exact/normalized fields, row precision/recall, missing confusion metrics, by-kind metrics, and page/polygon Decimal IoU; `PAGE_MISMATCH` has no IoU, no acceptance threshold was invented, and concave, self-intersecting, degenerate, and malformed geometry fail closed. The existing synthetic-only `ExtractionProvider` seam remains preserved.
- Independent review/remediation history at this checkpoint: initial `REJECT` exposed integrity gaps; remediation closed B-1..B-4, M-1..M-6, and m-1..m-5. Post-remediation `ACCEPT_WITH_MINOR` found only N-1/N-3 plus design notes; Codex closed N-1/N-3. The final review had not yet run at this historical checkpoint; current verdict is in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).
- Latest remediation evidence at this checkpoint superseded the earlier focused count: the selector passed `20 passed, 42 deselected`; `make p4-golden-check` passed 183. `make p4-benchmark-fixture` remained byte-identical with output SHA-256 `354d7c10d7c6380c855876ef72d11148523ea12f1b346b8c5f3552ec416bfd23`, report SHA-256 `7b0601d2f57547db32a1c9897efa30211a14fd9ff645b2a9a4fcabf57da28933`, fixture SHA-256 `05f777392052c3b29be32abe1d7852312baff966fd5ac1fdc88cc6479ae918d0`.
- Latest `make backend-check` passed Ruff, strict mypy across 49 source files, backend `501 passed, 77 deselected`, and compileall. `make check` exited 0 with contract/client drift, backend, frontend lint/typegen/typecheck, Vitest 32, Next production build, migration contract 4, secret scan, sensitive-document scan, and Compose config.
- Controller adversarial probes rejected truncated, swapped, foreign, and digest-tampered `BenchmarkOutput`; ambient Decimal precision 12 and 50 produced identical canonical results; all 20 edge dispositions were exactly bound. P4/P2/P3 disposable Docker containers/networks/volumes ended at 0/0/0.
- Historical source-freeze/Git boundary: worktree `/tmp/hyc_p4a`, branch `JudyandGIINII/hanyang-p4a-offline-synthetic-20260802`, base HEAD `2d5c02dbc612f9b612f27a36263b95e842c24e75`. The pre-documentation source candidate was exactly 16 paths with sorted-path+NUL+bytes+NUL SHA-256 `cf30f5c1cfad535143a0ed7fe8002e44e84ec0a67aaa9dcf15d06e32edfd5541`; later source/documentation edits invalidated it as a full candidate hash. At this checkpoint only, P4-A remained uncommitted/unintegrated/unpushed pending controller QA/final review; current status is in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).
- Boundaries remain: P4-B is independently `BLOCKED_QUALITY_CORPUS_APPROVAL`; P4-C is independently `BLOCKED_AP02_PROVIDER_OPT_IN`; neither is satisfied by P4-A. No real PDF/XLS/XLSX corpus, external Provider/OCR/AI, credential, network, deployment, DB/migration/API/frontend/service change, real-data operation, or production activation occurred. No full-P4/P5 or production-readiness claim is made, and P2/P3 accepted debts remain unchanged.
- Documentation-writer verification: `git diff --check`, `python3 scripts/scan_secrets.py`, and `python3 scripts/check_sensitive_documents.py` exited 0; the scanners printed `secret scan passed` and `tracked sensitive document scan passed`. A local link-target validation checked 24 Markdown links with 0 missing. The source-only freeze was independently recomputed after excluding these nine documentation paths and remained exactly 16 paths / `cf30f5c1cfad535143a0ed7fe8002e44e84ec0a67aaa9dcf15d06e32edfd5541`. The current-state stale scan found no live P4-A unstarted/absent-target claim; the sole old readiness-token match is explicitly labeled as the superseded historical kickoff state. This writer changed only the nine authorized documentation files and performed no add/commit/push/merge/rebase/reset/restore/stash/deploy.

## 2026-08-02 — P4-A final-acceptance remediation worker verification (historical pre-final-review checkpoint)

- Closed the fresh review's two actionable findings. The runner now rejects any non-empty candidate-observed warning tuple when extraction will fail or be skipped, while successful extraction keeps exact candidate-observed warning/declaration binding. The scoring and metric-validation paths now use explicit precision 28 with `ROUND_HALF_EVEN` for polygon area, clipping intersections, IoU, and ratios instead of inheriting ambient rounding.
- Added an exhaustive 14-case warning regression covering every non-empty subset of the three warning codes across edge-016 and edge-017, plus a precision 12/28/50 × `ROUND_UP`/`ROUND_DOWN`/`ROUND_CEILING`/`ROUND_FLOOR`/`ROUND_HALF_EVEN` sweep. The exact focused selector recorded in the P4 plan passed `20 passed, 42 deselected`; `make p4-golden-check` passed 183.
- `make p4-benchmark-fixture` was invoked twice and each target's internal cross-timezone byte comparison passed. Output/report/fixture SHA-256 remained exactly `354d7c10d7c6380c855876ef72d11148523ea12f1b346b8c5f3552ec416bfd23`, `7b0601d2f57547db32a1c9897efa30211a14fd9ff645b2a9a4fcabf57da28933`, and `05f777392052c3b29be32abe1d7852312baff966fd5ac1fdc88cc6479ae918d0`.
- `make backend-check` passed Ruff, strict mypy 49, backend `501 passed, 77 deselected`, and compileall. `make check` exited 0 with contracts/client drift, the same backend results, frontend lint/typegen/typecheck/Vitest 32/Next build, migration 4, scans, and Compose. `make p3-e2e` was not run because this remediation changes no runtime, API, UI, or workflow path, so P3 browser E2E was not applicable.
- Scope remained generated non-sensitive synthetic data only. No P4-B/C, provider, credential, network, DB, API, frontend, migration, Compose, external service, deployment, Git mutation, or production activation occurred. At this historical checkpoint the source/doc mutations had invalidated the prior review and final QA/review/delivery had not yet occurred; current status is in [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).

### 2026-08-02 post-integration documentation closure

- P4-A Offline/Synthetic is complete, independently accepted, committed, fresh-main fast-forward integrated, and delivered to `origin/main`. Final controller focused selector passed 15 with 47 deselected; `make p4-golden-check` passed 183; `make backend-check` passed Ruff, strict mypy 49 files/0 errors, backend 501 passed/77 deselected, and compileall. `make check` exited 0 with frontend lint/typegen/typecheck, Vitest 32, Next production build, migration contract 4, secret/sensitive-document scans, and Compose config. P2 PostgreSQL passed 10, P3 PostgreSQL passed 67, and disposable Docker containers/networks/volumes ended at 0/0/0. P3 browser E2E was not run because P4-A changed no runtime/API/UI/workflow path.
- `make p4-benchmark-fixture` remained repeatable with output `354d7c10d7c6380c855876ef72d11148523ea12f1b346b8c5f3552ec416bfd23`, report `7b0601d2f57547db32a1c9897efa30211a14fd9ff645b2a9a4fcabf57da28933`, and fixture `05f777392052c3b29be32abe1d7852312baff966fd5ac1fdc88cc6479ae918d0`.
- Fresh final independent read-only review of the final 25-path candidate returned `ACCEPT_WITH_MINOR`, BLOCKER 0, MAJOR 0, MINOR 3. It recomputed unchanged before/after-review digests: source-only 16 paths `0d5c259f59293f35e4cf6b83ffff13820c3c07194f5db48e54d8c8b1d09db632`; full candidate 25 paths `ba938518beca8f3718abdf4eb44430e26b3a775aea8f8b33dc5dc01937218f23`. The full digest is accepted-candidate capture-time evidence and is not claimed for this docs-only descendant.
- Accepted minor notes remain disclosed and are not blocker/major or source-fixed claims: (1) strict required geometry currently makes dead `missing_polygons`/`invalid_polygons` counters unrepresentable; clean them before optional-geometry semantics change; (2) schema-level polygon validation arithmetic was empirically stable but is not under the scorer's explicit Decimal context; close it before P4-B real-corpus geometry expansion; (3) ambiguous DEVLOG “below” wording was corrected in this docs closure to link directly to [`HANDOFF.md`](HANDOFF.md) and the [P4 plan](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).
- Source/integration commit `aeedceb2c3b7008439a9c72e3984be77f6135e51` (`feat: complete P4-A offline synthetic evaluator`) directly descends from baseline `2d5c02dbc612f9b612f27a36263b95e842c24e75`. A fresh Orca integration worktree was created from fetched `origin/main` at that baseline; `git merge --ff-only aeedceb…` succeeded without merge commit/rebase, and non-force `git push origin HEAD:main` succeeded. At capture time, post-fetch integration HEAD, `origin/main`, and remote main all equaled `aeedceb…`; baseline/source ancestry and clean implementation/integration worktrees passed. The commit containing this nine-file documentation closure is a newer descendant of `aeedceb…`; Git history is authoritative for its exact SHA and remote-tip status. `aeedceb…` remains the P4-A source/integration baseline, not the continuing tip.
- Product/authority boundary is unchanged: P4-A proves deterministic generated synthetic evaluator/schema/scoring/artifact integrity only. P4-B remains `BLOCKED_QUALITY_CORPUS_APPROVAL` without an approved representative/de-identified corpus manifest, retention/classification/hash/approval evidence. P4-C remains `BLOCKED_AP02_PROVIDER_OPT_IN` without provider/model/version/region, DPA/retention/training/subprocessor, credential/budget/cost cap, disable/rollback, and provider-specific approval evidence. No real corpus benchmark or external Provider invocation may begin before the named gate; no deployment, release/tag, public exposure, production DB/service change, real-data import/apply, external OCR/AI call, or production-readiness claim occurred.
