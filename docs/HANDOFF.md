# P3 delivery handoff and post-push closure

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

P4/P5는 현재 unstarted다. P3 source acceptance나 Git integration만으로 P4/P5, pilot, production 단계를 자동 시작하지 않는다.

## 8. 금지 작업

- 이 handoff 자체를 commit/push/merge/deploy 권한으로 해석하지 않는다.
- main/shared CWD mutation, reset/restore/stash/rebase 또는 무단 Git 작업을 하지 않는다.
- 실 PDF/XLS/XLSX를 커밋·업로드·미러링·외부 전송하지 않는다.
- 실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP 호출을 하지 않는다.
- production/non-disposable migration 또는 production DB-role activation을 하지 않는다.
- public service exposure, deployment, release, production-ready 선언을 하지 않는다.
- n8n을 중지·재시작·삭제·설정 변경하지 않는다.
