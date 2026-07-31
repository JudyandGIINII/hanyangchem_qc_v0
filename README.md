# 한양화학 v0 — 수입검사 디지털화 및 LOT 추적

현재 저장소는 수입검사 업무의 원본 보존, OCR 후보 검토, 한양화학 기준 판정, 검사자 제출·팀장 승인, LOT 추적을 디지털화하기 위한 신규 프로젝트다. AP-01~05와 P0A·P0B·P1은 complete/accepted다. 사용자 명시 승인에 따른 Hermes 직접 최종 QA로 P1 contract gate가 통과됐으며, P2는 authorized but not started다.

## 현재 상태

- 정본 요구사항: [`Prd.md`](./Prd.md)
- 통합 구현 계획: [`docs/plans/2026-07-30-integrated-implementation-plan.md`](./docs/plans/2026-07-30-integrated-implementation-plan.md)
- Hermes 독립 계획: [`docs/plans/2026-07-30-hermes-independent-plan.md`](./docs/plans/2026-07-30-hermes-independent-plan.md)
- Claude Code Opus 5 독립 계획: [`docs/plans/2026-07-30-claude-opus5-independent-plan.md`](./docs/plans/2026-07-30-claude-opus5-independent-plan.md)
- 요구사항 추적 정본: [`docs/TRACEABILITY_MATRIX.md`](./docs/TRACEABILITY_MATRIX.md)
- 독립 계획 QA: [`docs/reviews/2026-07-30-integrated-plan-alfred-qa.md`](./docs/reviews/2026-07-30-integrated-plan-alfred-qa.md) — formal/substantive PASS
- P0A original read-only freeze and controller reverification: [`docs/evidence/2026-07-30-p0a-evidence-freeze.md`](./docs/evidence/2026-07-30-p0a-evidence-freeze.md), [`docs/evidence/2026-07-31-p0a-controller-reverification.json`](./docs/evidence/2026-07-31-p0a-controller-reverification.json)
- P0B final independent review: `APPROVE` — 67 in-memory probes, HIGH 0, MEDIUM 0; one accepted LOW generic scheme-specific URI-semantics note is defense-in-depth because consumed relationship roles use exact allowlists
- 구현 상태: `P0A_P0B_P1_COMPLETE_ACCEPTED; P2_AUTHORIZED_NOT_STARTED`

## 핵심 안전 원칙

1. OCR/LLM은 추출 후보만 만든다.
2. 최종 판정은 Decimal 기반 결정론적 엔진과 사람 승인으로만 확정한다.
3. 공급사 규격/판정과 한양화학 기준/판정을 분리한다.
4. 검사 생성 당시 기준 버전과 승인 Snapshot을 불변 보존한다.
5. 누락·미매핑·저신뢰·자체검사 미완은 fail-closed(`ON_HOLD`)다.
6. AP-05에 따라 현재 PDF/XLSX 실원본은 계속 Git 커밋·외부 전송 금지 대상으로 취급한다.

## 다음 단계와 계속되는 경계

P1 contract gate는 2026-07-31 Hermes 직접 QA로 통과했다. P2는 이제 시작 권한이 있지만 아직 시작하거나 완료되지 않았다. 실데이터 apply/import, 외부 OCR/AI 호출, 비일회성 migration, 배포 및 서비스 공개는 계속 미승인이다.

## P1 accepted verification

`make bootstrap`, `make contracts`, and `make check` are deterministic local entrypoints. Root `pytest.ini` is the sole canonical pytest configuration—there is no nested backend pytest config—and makes `backend/src` importable without shell-only `PYTHONPATH`. `--collect-only -vv` reported the repository rootdir and `configfile: pytest.ini`; the targeted direct test file passed 12 tests and the full suite passed 172 tests. The sole upstream Starlette/httpx deprecation warning is non-blocking.

The final `make check` exited 0, including contract/client drift, Ruff, strict mypy across 15 files, 172 pytest tests, compileall, frontend lint/typegen/typecheck/Vitest (1 test)/build, migration check, secret scan, sensitive-document scan, and Compose configuration. Ruff and mypy retain only the stated byte-identity preservation exclusions for the accepted P0B importer and its accepted integration test. Generated source artifacts are `contracts/schemas/extraction-candidate.schema.json`, `contracts/schemas/error-envelope.schema.json`, and `contracts/openapi.json`; `make contracts-check` rejects drift.

Frontend verification is deterministic: `typecheck` runs `tsc --noEmit --incremental false`, so no `tsconfig.tsbuildinfo` remains. The Makefile and CI invoke Corepack `pnpm` from the frontend working directory, selecting pinned pnpm `10.13.1`; frozen install and all frontend gates passed and the lockfile is unchanged. Compose uses disposable PostgreSQL `tmpfs`, publishes only API/web ports loopback-only, and leaves PostgreSQL/Redis unpublished. Hermes recovered the final exact-candidate controller process `proc_7e03db110d2f` directly from tracked process output: it exited 0 with PostgreSQL, Redis, API, worker, and web healthy; live/ready API and web HTTP 200 expected JSON probes; a PostgreSQL migration roundtrip; and cleanup all passing. The P1 Alembic revision remains a no-op baseline and creates no P2 business data or tables.

For the default local Compose endpoints, run `docker compose up --build -d`, then use `curl -fsS http://127.0.0.1:18000/health/ready` and `curl -fsS http://127.0.0.1:13000/api/health`. Set `HYC_API_HOST_PORT` and `HYC_WEB_HOST_PORT` in the local environment or `.env` before startup if those default host ports are occupied; container ports stay 8000 and 3000.

P1 is complete and accepted. This verification does not claim P2 implementation or relax the real-data, external OCR/AI, non-disposable migration, deployment, or public-exposure prohibitions.

## 작업 기록

- [`docs/DEVLOG.md`](./docs/DEVLOG.md)
- [`docs/KANBAN.md`](./docs/KANBAN.md)
