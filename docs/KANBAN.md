# KANBAN — 한양화학 v0

> 정본 실행 보드는 Hermes Kanban `hanyang-chemical-v0`이다. 이 문서는 프로젝트 내 사람이 읽을 수 있는 mirror다.

## 현재 작업

|Card|상태|내용|완료 조건|
|---|---|---|---|
|`t_7d493a1e`|Completed|PRD 기반 독립 계획 2개 비교·통합·문서화|Opus 5 증빙 확인, 비교표/통합 계획/전수 추적, Alfred R1 formal+substantive PASS, DEVLOG/링크 검증 완료|
|`t_715483aa`|Completed|P0B correction candidate final independent review/acceptance|P0A/P0B complete·accepted, final independent `APPROVE` 확인|
|P1-local-candidate|Completed / accepted|P1 repository/contract foundation|User-authorized Hermes direct final QA passed the P1 contract gate and enabled the subsequently accepted P2 source increment|
|FE8-frontend-fixture|Completed / independently verified / delivered to `origin/main`|Deterministic synthetic eight-flow frontend workflow|Source/UI approvals, post-doc and fresh integration full gates, standalone/desktop/390px QA, active probe, remote-race, push and post-push verification passed; not P2/P3 backend/domain completion|
|P2-domain-db-candidate|Completed / accepted / committed / fresh-main integrated; remote publication pending|P2.1–P2.8 pure domain and DB invariants|Source commit `996056b` was fast-forward integrated from fresh `origin/main` baseline `1e96836` after separate user authorization. Fresh `make bootstrap` and `make check` passed; N-M3 remains an accepted follow-up before production DB-role activation; P3 remains blocked|

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
- P2 final minor hardening source: N-M1 adds immutable Alembic head `20260801_0003`, requiring every new inspection case to be unfinalized, while frozen `20260731_0002` retains SHA-256 `546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`. N-M2 keys document transitions by current+target+role with duplicate-key detection; the supplier-only/model-only equal-rank ambiguity has a dedicated fail-closed unit regression. `make check` passed with backend 346 passed/10 PostgreSQL deselected, strict mypy 29 files, migration contract 4, and FE8 frontend 32; the disposable PostgreSQL runner separately passed 10 tests plus migration/autogenerate roundtrip and verified cleanup. The earlier 344/9/28 and PostgreSQL 9 measurements remain historical and are superseded by this current evidence.
- P2 final acceptance: Hermes independently reproduced `make check` exit 0, backend `346 passed, 10 PostgreSQL deselected`, strict mypy 29 files, migration contract 4, FE8 frontend 32 plus lint/typecheck/build, scans/Compose, PostgreSQL 10 plus upgrade→downgrade→upgrade and empty drift, and cleanup 0/0/0. Final Claude report `/tmp/hyc-p2-absolute-final-claude-review.md` returned `PASS` with BLOCKER 0, MAJOR 0, MINOR 1 and closed B1–B5, M1–M9, m1–m7, H1, N1–N3, N-M1, and N-M2.
- P2 post-integration closure: separately user-authorized source commit `996056b` is fast-forward integrated in the clean branch from fresh `origin/main` baseline `1e96836`. Fresh `make bootstrap` and `make check` exited 0 with backend 346 passed/10 PostgreSQL deselected, strict mypy 29, migration 4, FE8 frontend 32 plus lint/typecheck/build, scans/Compose; disposable PostgreSQL 10 passed and cleanup was verified. Remote publication is authorized and pending.
- Accepted follow-up N-M3 is not fixed: a DB-direct app-role writer with broad direct `inspection_cases` plus evidence-table privileges can insert an unfinalized case already at `LEAD_REVIEW` and finalize it with complete valid evidence, bypassing intermediate status history. N1 decision integrity, mandatory evidence, and finalized-row immutability still hold. Review this defense-in-depth gap before any production DB-role activation.
- 구현 상태: `P0A_P0B_P1_P2_COMPLETE_ACCEPTED; P3_BLOCKED_NOT_AUTHORIZED`

## 승인 현황

|Gate|결정|상태|
|---|---|---|
|AP-01|사내망 Docker Compose·공개 배포 없음|승인|
|AP-02|외부 OCR/AI 기본 OFF 및 향후 opt-in 절차|승인|
|AP-03|canonical LOT + inbound allocation 데이터 모델|승인|
|AP-04|Local Auth/RBAC 및 ADMIN 비승인권|승인|
|AP-05|실 PDF/XLSX Git 커밋 금지·마스킹 fixture 정책|승인|
|Implementation|P0A/P0B/P1/P2|P0A/P0B/P1/P2 complete·accepted; separate user authorization committed and fresh-main-integrated P2 (`996056b`), while remote publication remains pending; P3 and product/operations gates remain unauthorized|
|Still prohibited|실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포/서비스 공개|미승인|

## 실행 Backlog

1. P0A read-only evidence freeze — Completed, source immutable PASS
2. P0B evidence tooling/fixture bootstrap와 ADR — Completed/accepted
3. P1 Repository/Contract foundation — Completed/accepted through user-authorized Hermes direct QA
4. P2 Pure domain + DB invariants — Completed/accepted, committed, and fresh-main integrated (`996056b`); remote publication pending; N-M3 retained as pre-production-privilege follow-up
5. P3 Fixture 기반 첫 수직 Slice — FE8 frontend fixture increment independently verified; P3 backend vertical slice remains pending/blocked and unauthorized
6. P4 OCR Golden/Provider benchmark
7. P5 Core MVP
8. P6 수집/운영/Pilot

P1 contract gate는 통과했고 P2는 독립 Hermes+Claude source gate를 통과해 complete·accepted다. Acceptance 자체와 별도로 사용자가 Git 작업을 승인해 `996056b`가 fresh-main integration branch에 fast-forward 통합되었다. 원격 publication은 승인되었으나 pending이며, 이는 deployment, release 또는 운영 활성화를 뜻하지 않는다. P3는 계속 blocked/미승인이고, 실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포와 서비스 공개는 계속 시작하지 않는다.
