# KANBAN — 한양화학 v0

> 정본 실행 보드는 Hermes Kanban `hanyang-chemical-v0`이다. 이 문서는 프로젝트 내 사람이 읽을 수 있는 mirror다.

## 현재 작업

|Card|상태|내용|완료 조건|
|---|---|---|---|
|`t_7d493a1e`|Completed|PRD 기반 독립 계획 2개 비교·통합·문서화|Opus 5 증빙 확인, 비교표/통합 계획/전수 추적, Alfred R1 formal+substantive PASS, DEVLOG/링크 검증 완료|
|`t_715483aa`|Completed|P0B correction candidate final independent review/acceptance|P0A/P0B complete·accepted, final independent `APPROVE` 확인|
|P1-local-candidate|Completed / accepted|P1 repository/contract foundation|User-authorized Hermes direct final QA passed the P1 contract gate; P2 is authorized but not started|
|FE8-frontend-fixture|Implemented / independently verified; docs-inclusive gate passed; integration pending|Deterministic synthetic eight-flow frontend workflow|Source `APPROVE` (0 blocker/major/minor), narrow UI `APPROVE` (0 high/medium/low), and post-doc full gate passed; not P2/P3 backend/domain completion|

## 검증 결과

- Claude Code canonical model: `claude-opus-5`, `is_error=false`
- Alfred 1차 findings: HIGH 3건·MEDIUM 2건, 총 5건을 보정했고 R1에서 모두 `RESOLVED`
- Alfred R1: 신규 HIGH/MEDIUM blocker 0, `substantive_plan_assessment: PASS`
- P0B second remediation: independent re-review의 HIGH 1건·MEDIUM 3건(OOXML/OPC semantic validation, every-`.rels` validation, all-member CRC/decompression, source-digest provenance binding)을 synthetic regression coverage로 보정했으며 재검토/controller acceptance 대기
- P0B third focused remediation: MEDIUM Content-Type-driven OPC member validation 및 complete Relationship element semantics, LOW root-level relationship-source compatibility를 synthetic-only regression으로 보정했다. `pytest -q`는 2026-07-31에 `94 passed in 4.41s`; final QA/controller acceptance 대기 상태는 변함없다.
- P0B fourth focused remediation: MEDIUM full RFC 3986 Relationship-Type lexical validation 및 canonical OPC member/Override/relationship-Target lexical validation, LOW attribute-free `Relationships` root hardening을 synthetic-only regression으로 보정했다. 서로 다른 typed relationship ID의 동일 target은 OPC 호환성을 위해 허용하며 duplicate ID만 거부한다. `pytest -q`는 2026-07-31에 `127 passed in 5.90s`였다.
- P0B final independent review: 67 in-memory probes, HIGH 0, MEDIUM 0, `APPROVE`. generic scheme-specific URI semantics의 LOW lexical-contract note는 소비 relationship role이 exact allowlist를 사용하므로 defense-in-depth로 수용됐다.
- Controller evidence: `127 passed`; approved real QM301 dry-run 38 templates/119 rows, discrepancy 0, DB write/apply 0; source hash/size/mtime unchanged; tracked sensitive documents 0.
- P1 final Hermes direct QA (explicitly authorized by the user in place of unavailable Claude reapproval): root `pytest.ini` is canonical and `--collect-only -vv` confirmed repository rootdir/configfile; direct targeted test file 12 passed; full suite 172 passed with one non-blocking upstream Starlette/httpx deprecation warning. Final `make check` exited 0 for contract/client drift, Ruff, strict mypy (15 files), pytest, compileall, frontend lint/typegen/typecheck/Vitest (1)/build, migration, secret/sensitive scans, and Compose config. Frontend Corepack pnpm runs from frontend cwd with pinned pnpm `10.13.1`; typecheck is `tsc --noEmit --incremental false`, no `tsconfig.tsbuildinfo` remains, frozen install and all gates passed, and the lockfile is unchanged. Final exact-candidate Compose controller process `proc_7e03db110d2f` exited 0 with all five services healthy, expected API/web probes, PostgreSQL migration roundtrip, and cleanup passing.
- FE8 frontend fixture closure (pre-docs): eight deterministic synthetic flows are implemented and independently approved on source (`APPROVE`, BLOCKER/MAJOR/MINOR 0) and UI (`APPROVE`, HIGH/MEDIUM/LOW 0). The source-only 10-file manifest was `5b7f222fa5bba991499c3be4e8b49231fba59bb66b1b50dcc1e43ed29ddb6335`, with unchanged review status digest `754834d90ae0c30075a0e611383abc9f99e6c157d335c7e6ddcd6ff8cb569692`; it is not docs-inclusive final evidence. Local Decimal-string/BigInt, explicit confirmation, fail-closed/reducer-only frozen snapshot, and submission/approval locks were verified. Roles are simulation only; no backend mutation, persistence, real auth, OCR/AI, ERP, apply/import, or deployment occurred. Controller `make bootstrap && make check` exited 0 (backend pytest 172; frontend Vitest 3 files/32 tests; stated static/build/scans), and the 390×844 viewport had no page-level overflow.
- 구현 상태: `P0A_P0B_P1_COMPLETE_ACCEPTED; P2_AUTHORIZED_NOT_STARTED`

## 승인 현황

|Gate|결정|상태|
|---|---|---|
|AP-01|사내망 Docker Compose·공개 배포 없음|승인|
|AP-02|외부 OCR/AI 기본 OFF 및 향후 opt-in 절차|승인|
|AP-03|canonical LOT + inbound allocation 데이터 모델|승인|
|AP-04|Local Auth/RBAC 및 ADMIN 비승인권|승인|
|AP-05|실 PDF/XLSX Git 커밋 금지·마스킹 fixture 정책|승인|
|Implementation|P0A/P0B/P1/P2|P0A/P0B/P1 complete·accepted; the P1 contract gate passed through user-authorized Hermes direct QA; P2 authorized but not started|
|Still prohibited|실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포/서비스 공개|미승인|

## 실행 Backlog

1. P0A read-only evidence freeze — Completed, source immutable PASS
2. P0B evidence tooling/fixture bootstrap와 ADR — Completed/accepted
3. P1 Repository/Contract foundation — Completed/accepted through user-authorized Hermes direct QA
4. P2 Pure domain + DB invariants — Ready/authorized; not started
5. P3 Fixture 기반 첫 수직 Slice — FE8 frontend fixture increment independently verified; P3 backend vertical slice remains pending
6. P4 OCR Golden/Provider benchmark
7. P5 Core MVP
8. P6 수집/운영/Pilot

P1 contract gate는 통과했다. P2는 Ready/authorized이나 아직 시작하지 않았다. 실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포와 서비스 공개는 계속 시작하지 않는다.
