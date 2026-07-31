# P3 준비 — Frontend 8단계 Fixture Workflow 구현 계획

**상태:** `IMPLEMENTED_INDEPENDENTLY_VERIFIED_AND_DOCS_GATE_PASSED`; P3/product/operations acceptance 전이며 P2/P3 backend/domain completion, backend 연결, real auth, 또는 production support를 주장하지 않는다. Git integration/push는 아직 pending이다.

**정본:** `Prd.md`, `docs/plans/2026-07-30-integrated-implementation-plan.md`의 P3/§8, `docs/TRACEABILITY_MATRIX.md`, fixture UX 작업 계약.

## 목적과 범위

Next.js App Router 위에 결정적인 합성 fixture만 사용하는 한국어 수입검사 작업공간을 만든다. 흐름은 목록 → 입고/LOT → 문서 검토 → 매칭 → 자체검사 → 제출 → 팀장 검토 → LOT 추적이다. 순수 타입/fixture/reducer/guard/decimal-string helper는 `frontend/src/lib/inspection/`에, client workspace는 `frontend/src/components/inspection/`에 둔다. 초기 fixture는 불변·결정적이며 시간, 난수, browser storage, 네트워크를 사용하지 않는다.

각 단계는 다음을 보여 준다: 작업 큐 검색/필터와 KPI, 입고·정본 LOT·분할 allocation, 원문/OCR/수기/최종값과 confidence 교차검토, 명시적 section↔allocation 확인, 가변 문자열 샘플 및 `INTERNAL_TEST_PENDING` hold, fail-closed 제출 preflight, INSPECTOR/LEAD/ADMIN 역할 시뮬레이션과 LEAD 승인 동결, 그리고 규격·문서·감사를 포함한 결정적 LOT trace이다.

## 안전 경계와 제외

- 실제 PDF/XLS/XLSX, 과거 실제 파일명, OCR/provider 호출, 업로드, API mutation/persistence/auth, backend/domain/migration 변경은 포함하지 않는다. 역할 전환은 simulation이며 real authentication/authorization이 아니다.
- 모든 화면은 `FX-`/`SYNTHETIC` 식별자와 `Fixture UX`, `서버 저장 없음`, `실제 문서 아님` 경계를 표시한다.
- 승인 동결은 local reducer 데모이며 실제 DB snapshot/audit/RBAC/idempotency를 대체하지 않는다.
- production LOT automatic ERP link, 정정 revision, 재검사 round는 비활성·설명 상태만 제공한다. 배포·서비스 노출은 범위 밖이다.

## 구현 및 독립 검증 결과

1. strict decimal-string acceptance와 `BigInt`/string aggregate를 구현했고 사업 값 모듈에서 `Number`/`parseFloat`를 쓰지 않는다. 명시적 수동 candidate confirmation, `적합`/`부적합` qualitative allowlist, blank-row hold를 확인했다.
2. 문서 확정·매칭·자체검사 hold, 제출 차단, simulated LEAD-only/사유 필요 승인, 승인 뒤 edit denial, trace ordering을 검증했다. Guards are fail-closed for required evidence, trimmed values/sources/reasons, role/source status, LOT/quantity/unit, profile/version, thresholds, relationships, trace, internal confirmation, and post-submit mutation.
3. Local reducer snapshot builder is private/non-exported. The exact entire `internalTests` contract, explicit `null` threshold serialization, value-complete snapshot fields, and recursive freeze were independently source-verified; this does not represent a production DB snapshot/audit/RBAC/idempotency contract.
4. Sidebar/workspace, labels/table headers/focusable named wrappers, `aria-current`, status-aware copy, and 44px mobile controls were reviewed. At a true 390×844 viewport inner/document/body width was 390 with no page-level overflow.
5. Before this documentation edit, source review was `APPROVE` (BLOCKER/MAJOR/MINOR 0; 31 focused tests and a 14-attack probe) and narrow UI review was `APPROVE` (HIGH/MEDIUM/LOW 0; standalone BUILD_ID `yxIU8dalJEwMZG9Hg5YIz`). The exact source-only 10-file manifest was `5b7f222fa5bba991499c3be4e8b49231fba59bb66b1b50dcc1e43ed29ddb6335` at `bfeb7c1267a41ff95da6c1abf1a30f6d7fb56ea5`, status digest `754834d90ae0c30075a0e611383abc9f99e6c157d335c7e6ddcd6ff8cb569692`; it is pre-docs evidence, not a docs-inclusive final-manifest claim. Earlier `6b79...`, `4447...`, `0797...`, `987956...`, `b96da...`, and `97c508...` candidates are superseded and not final evidence.
6. Controller `make bootstrap && make check` exited 0: backend pytest 172 passed (one upstream Starlette/httpx deprecation warning), Ruff, strict mypy 15 files, compileall, generated-client drift, migrations, secret/sensitive scans, Compose config, frozen pnpm install, ESLint, next typegen, artifact-free tsc, frontend Vitest 3 files/32 tests, and production build. Protected P0B importer/masked dry-run test remained byte-identical to accepted base; `/tmp/hanyang_p2` was not imported.

## 게이트

이 fixture increment는 P3 backend vertical slice 또는 P2 domain/DB gate를 우회하지 않는다. P0A/P0B/P1은 complete/accepted이고 P2는 authorized/not started 상태를 유지한다. Independent source/UI verification and the passed docs-inclusive controller gate do not authorize real-data apply/import, backend mutation, real auth, OCR/AI, ERP, non-disposable migration, deployment, service exposure, or production support. Git integration/push remains pending until the fresh-main regression and remote-race gates pass.
