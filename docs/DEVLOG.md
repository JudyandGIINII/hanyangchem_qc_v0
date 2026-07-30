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
