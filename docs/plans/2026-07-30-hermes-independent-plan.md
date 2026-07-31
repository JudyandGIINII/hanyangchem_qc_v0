# 한양화학 수입검사 디지털화 및 LOT 추적 시스템 — Hermes 독립 구현 계획

> **For Hermes:** 최종 통합 계획 승인 후 `orca-codex-primary-hermes-qa` 워크플로로 단계별 구현한다. 이 문서는 구현 권한이 아니라 독립 계획 근거다.

**Goal:** 원본 문서 무결성, 검사 당시 기준 버전, 결정론적 판정, 사람 검토·팀장 승인, 전 변경 감사가 끊기지 않는 수입검사 MVP를 구축한다.

**Architecture:** PostgreSQL을 정본으로 하는 모듈형 모놀리스와 별도 비동기 작업자를 먼저 구축한다. OCR/LLM은 후보 추출용 Port/Adapter로 격리하고, 판정 엔진·상태 전이·승인은 외부 AI와 분리된 순수 도메인 규칙과 DB 제약으로 이중 방어한다. 첫 실행 가능한 범위는 실제 샘플 한 종류를 관통하는 얇은 수직 슬라이스로 제한하되 데이터 모델은 품목·공급사·샘플 수를 하드코딩하지 않는다.

**Tech Stack:** Next.js/React/TypeScript, FastAPI/Python 3.12(프로젝트 전용 `uv`), SQLAlchemy 2, Alembic, PostgreSQL, Celery+Redis, PDF.js, Pytest, Vitest, Playwright, Docker Compose.

---

## 1. 독립 분석 기준

### 읽은 현재 자료

- 정본 요구사항: `Prd.md` 전체 3,525개 문서 라인
- 기준 원본: `qm301-7-rb-import-inspection` (stable source alias) — PRD 기준 38개 템플릿/119개 항목
- 레거시 출력 골격: `inbound-inspection-raw-data` — 공통 필드 뒤에 항목·결과 열이 가로 반복되고 실제 데이터 행은 아직 없음
- 이미지 기반 샘플: 염화칼슘 COA 1개, 내수 8P 패키지 검사성적서 1개
- 저장소 상태: 소스·테스트·설정 파일이 없는 신규 저장소, `main`은 아직 첫 커밋 전, 모든 현재 자료가 untracked

### 가장 위험한 오해

1. **공급사 Specification을 한양화학 기준으로 취급하는 것** — 공급사 판정과 HYC 판정은 데이터·화면·보고서에서 별도 필드여야 한다.
2. **OCR/LLM 결과를 자동 확정하는 것** — 추출 후보와 confidence만 만들며, 저신뢰·필수 누락·논리 충돌은 반드시 검토 큐로 간다.
3. **`receipt_lots.inbound_receipt_id`만으로 LOT 관계를 고정하는 것** — PRD의 “동일 LOT 분할 입고/다대다 수용”과 충돌한다. 정본 LOT와 입고 배분 Join을 분리해야 한다.
4. **활성 기준을 수정하거나 최신 기준으로 과거를 재판정하는 것** — 검사 생성 시 기준 버전을 고정하고 승인 Snapshot을 불변 저장해야 한다.
5. **앱 코드만으로 감사·불변성을 보장하는 것** — 우회 API/운영 실수에 대비해 트랜잭션, DB 제약, 최소 권한 DB 역할, append-only 이벤트로 방어해야 한다.

## 2. 구현 전 결정 레지스터

|ID|분류|결정|안전한 기본 제안|잘못 결정했을 때 비용/게이트|
|---|---|---|---|---|
|D-01|즉시|파일·DB 배치 위치와 데이터 외부 반출 범위|파일럿은 사내망 Docker Compose + NAS/로컬 저장, 공개 인터넷 노출 금지|외부 AI/OCR 및 클라우드 전송의 법무·보안 재작업. **AP-0 승인 필요**|
|D-02|즉시|정본 LOT 식별과 분할 입고 관계|`material_lots` + `receipt_lot_allocations` 다대다 구조, 검사 건은 배분 단위를 참조하고 추적은 정본 LOT로 집계|핵심 FK 마이그레이션 비용. PRD 원칙상 1:1 하드코딩 금지|
|D-03|즉시|파일럿 인증원|로컬 계정+Argon2id+RBAC, SSO는 Auth Port 뒤 후속 Adapter|사용자/승인자 식별 재매핑. 사내 SSO가 필수면 P1 전 변경|
|D-04|즉시|실제 PDF/Excel의 Git 저장 허용 여부|원본은 보안 저장소에 두고 Git에는 허가된 비식별/마스킹 fixture와 해시 manifest만 저장|영업·개인·품질정보 유출. 현재 untracked 원본은 분류 전 커밋 금지|
|D-05|설정 격리|Primary/Mirror 저장소|개발 `LocalStorageAdapter`, 파일럿 `NasStorageAdapter`, Drive는 선택 Mirror|Adapter 교체로 흡수 가능|
|D-06|설정 격리|OCR Provider/모델/보존|`FixtureExtractionProvider`부터 구현, golden benchmark 후 선택; 외부 전송 기본 OFF|Provider별 비용·정확도·보존 정책. benchmark 전 고정 금지|
|D-07|설정 격리|샘플·누락·반올림 정책|불명확 항목은 `MANUAL`/`HOLD`, Decimal `ROUND_HALF_UP`도 항목별 명시 전 전역 강제 금지|판정 결과가 달라질 수 있으므로 기준 버전에 포함|
|D-08|설정 격리|보고서 템플릿|데이터 Contract/Snapshot 먼저, 표현 템플릿은 버전 Adapter|디자인 변경은 낮은 비용, Contract 변경은 높은 비용|
|D-09|파일럿 이후|OCR confidence 임계값|필드 유형별 운영 설정; 초기에는 자동 확정 없이 모두 검토 가능|KPI 기준선 확보 후 조정|
|D-10|파일럿 이후|RPO/RTO·보존기간·NAS/Drive 이중화|백업/복구 기능은 구현하되 목표값은 `PENDING_POLICY`|운영 승인 전 생산 전환 금지|
|D-11|파일럿 이후|AQL 자동 계산, ERP/BOM, 장비 연계|MVP 비활성; 이벤트·Port와 nullable 외부 코드만 준비|YAGNI 위반 방지|

## 3. 제안 아키텍처

### 3.1 배포 단위

초기에는 마이크로서비스 대신 다음 4개 프로세스의 **모듈형 모놀리스**로 시작한다.

1. `web`: Next.js UI
2. `api`: FastAPI, 동기 업무 명령/조회, 트랜잭션 경계
3. `worker`: 문서 전처리·OCR·보고서·복제 작업
4. `scheduler`: NAS/Drive 수집 주기 작업(Phase 5에서 활성)

공유 업무 코드는 `backend/src/hyc_inspection` 한 패키지에 두되 `domain → application → ports → adapters` 의존 방향을 강제한다. OCR 작업자가 판정 테이블을 직접 확정하지 못하도록 DB 역할과 application command를 분리한다.

### 3.2 핵심 경계

- **Domain:** 기준/단위/샘플/누락/출처/판정, 문서·검사 상태 전이. FastAPI·SQLAlchemy·Celery를 import하지 않는 순수 Python.
- **Application:** command/query handler, Unit of Work, RBAC policy, idempotency, 감사 이벤트 생성.
- **Ports:** storage, OCR/extraction, queue, auth, ERP, clock, malware scanner, report renderer.
- **Adapters:** PostgreSQL/SQLAlchemy, NAS/local/Drive, fixture/OCR provider, Celery, PDF/XLSX.
- **API:** Pydantic DTO와 OpenAPI. 도메인 객체를 직접 노출하지 않는다.
- **Frontend:** 생성된 OpenAPI client + 화면별 feature module. 서버 상태 전이를 UI에서 재구현하지 않는다.

### 3.3 트랜잭션과 비동기

- 입고·기준·검토·승인 명령은 단일 PostgreSQL transaction에서 상태·version·audit event를 함께 저장한다.
- 비동기 요청은 같은 transaction에서 `outbox_events`를 기록한다. dispatcher가 Celery로 전송하고 `event_id`/업무 idempotency key로 중복 실행을 흡수한다.
- 외부 OCR 결과는 `document_extractions` 새 버전으로만 추가한다. 실패 재처리는 과거 시도를 덮어쓰지 않는다.
- 승인 명령은 inspection row lock + expected version + idempotency record를 사용하고, Snapshot·approval·audit를 원자적으로 생성한다.

### 3.4 무결성 방어

- 원본 파일은 먼저 격리 영역에 스트리밍 저장하며 동시에 SHA-256을 계산한다. MIME magic, 확장자, 크기, 페이지 수, 암호화/손상, malware scan 결과를 확인한 뒤 immutable object로 승격한다.
- `documents.checksum_sha256`은 중복 정본을 가리키고, 업무별 재사용은 link table로 표현한다.
- 활성 기준과 승인 검사본은 앱 권한으로 직접 UPDATE/DELETE할 수 없다. 정정은 `revision_of_id`가 있는 새 버전이다.
- 최종 판정은 반드시 approval과 `decision_snapshot`을 가진다.
- 감사 이벤트는 before/after 전체 민감 payload 대신 필드 수준 redaction 정책과 correlation ID를 사용한다.

## 4. 계획된 신규 파일 구조

아래 경로는 모두 **Create 예정**이며 현재 존재하지 않는다.

```text
.
├── README.md
├── AGENTS.md
├── .gitignore
├── .env.example
├── Makefile
├── compose.yaml
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── migrations/
│   │   ├── env.py
│   │   └── versions/
│   ├── src/hyc_inspection/
│   │   ├── api/{main.py,deps.py,errors.py,routers/}
│   │   ├── domain/
│   │   │   ├── common/{decimal.py,errors.py,events.py,ids.py}
│   │   │   ├── master/models.py
│   │   │   ├── specifications/{models.py,parser.py,selection.py}
│   │   │   ├── receipts/{models.py,states.py}
│   │   │   ├── documents/{models.py,states.py,matching.py}
│   │   │   ├── inspections/{models.py,states.py,policies.py}
│   │   │   ├── judgment/{engine.py,units.py,samples.py,snapshot.py}
│   │   │   └── approvals/policies.py
│   │   ├── application/{commands,queries,services,uow.py,authz.py,idempotency.py}
│   │   ├── ports/{storage.py,extraction.py,queue.py,auth.py,clock.py,scanner.py,reports.py,erp.py}
│   │   ├── adapters/
│   │   │   ├── db/{models.py,repositories.py,uow.py}
│   │   │   ├── storage/{local.py,nas.py,drive.py}
│   │   │   ├── extraction/{fixture.py,provider.py,pdf_preprocess.py}
│   │   │   ├── queue/celery_app.py
│   │   │   └── reports/{raw_excel.py,integrated.py,lot_trace.py,quality_stats.py}
│   │   └── workers/{tasks.py,outbox.py}
│   ├── scripts/{import_spec_workbook.py,import_raw_data.py,seed_dev.py}
│   └── tests/
│       ├── unit/{domain,judgment,specifications}/
│       ├── integration/{api,db,workers,reports}/
│       ├── contract/
│       ├── golden/
│       └── fixtures/
├── frontend/
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── next.config.ts
│   ├── src/app/
│   ├── src/features/{receipts,documents,ocr-review,inspections,specs,approvals,lot-trace,reports}/
│   ├── src/lib/{api,auth,forms,status}/
│   └── tests/{unit,e2e}/
├── contracts/
│   ├── extraction/v1.schema.json
│   ├── errors/v1.schema.json
│   └── generated/openapi.json
├── fixtures/
│   ├── manifests/source-documents.yaml
│   ├── golden/calcium-chloride-coa/{expected.json,annotations.json}
│   ├── golden/domestic-8p-package/{expected.json,annotations.json}
│   └── spec-import/qm301-7-expected.json
├── infra/
│   ├── docker/{api.Dockerfile,web.Dockerfile,worker.Dockerfile}
│   ├── postgres/init/
│   └── observability/
├── scripts/{bootstrap.sh,check.sh,backup.sh,restore-verify.sh,secret-scan.sh}
└── docs/
    ├── adr/
    ├── plans/
    ├── runbooks/
    ├── DEVLOG.md
    ├── KANBAN.md
    ├── SECURITY.md
    └── USER_GUIDE.md
```

## 5. 단계별 구현 로드맵

### Phase 0 — Evidence freeze와 AP-0 결정

**목표:** 실제 원본을 안전하게 분류하고 구현 전 불변식·결정·샘플 기준선을 고정한다.

**작업**

1. `Create: docs/adr/0001-deployment-and-data-residency.md` — D-01/D-03/D-04 승인 기록.
2. `Create: docs/adr/0002-lot-identity-and-receipt-allocation.md` — 정본 LOT와 입고 배분 관계 확정.
3. `Create: fixtures/manifests/source-documents.yaml` — 파일명, SHA-256, 유형, 허용된 fixture 상태, 민감도만 기록하고 원본 내용은 복제하지 않는다.
4. `Create: docs/OCR_BENCHMARK.md` — golden annotation 규칙, 지표, provider 비용/보존 비교 형식.
5. `Create: docs/TRACEABILITY_MATRIX.md` — FR/AT/DoD를 단계·테스트에 연결.
6. 기준 Excel importer spike는 temp 출력만 만들고 DB 적용은 하지 않는다.

**검증/게이트**

- manifest hash가 실제 원본과 일치하되 원본 파일은 변경되지 않아야 한다.
- 38개 시트/119개 항목이라는 PRD 관찰을 importer dry-run으로 재검증한다. 불일치하면 PRD를 임의 보정하지 않고 discrepancy report를 만든다.
- AP-0: 데이터 배치/반출, LOT 모델, 인증원, fixture Git 정책을 사용자가 승인해야 Phase 1 진행.

**중단 조건:** 실제 문서의 저장·외부 전송 권한이 불명확하거나 LOT 의미가 현업과 충돌하면 코드 구현을 시작하지 않는다.

### Phase 1 — 저장소·계약·개발환경 기반

**목표:** 재현 가능한 로컬 스택과 계약 검증을 만든다.

**작업**

1. `Create: backend/pyproject.toml`, `frontend/package.json`, `compose.yaml`, `.env.example`, `.gitignore`.
2. Python 3.12를 프로젝트 전용 `uv`로 고정하고 전역 `python3`는 변경하지 않는다.
3. PostgreSQL/Redis/API/worker/web healthcheck와 비밀 placeholder를 구성한다.
4. `Create: contracts/extraction/v1.schema.json` 및 Pydantic 모델/round-trip contract test.
5. 표준 오류, correlation ID, UUIDv7 또는 UUID4 정책, UTC 저장/Asia-Seoul 표시 계약을 정의한다.
6. CI에서 backend lint/type/test, frontend lint/type/test/build, migration replay를 병렬 실행한다.

**완료 기준**

- 빈 DB에서 `alembic upgrade head`가 재실행 가능하다.
- extraction fixture가 JSON Schema/Pydantic 양쪽을 통과하고 unknown/누락 필드는 fail-closed된다.
- secret placeholder 외 실제 key가 저장소에 없다.

**롤백:** 기반 lockfile/compose/CI만 되돌릴 수 있으며 운영 데이터는 아직 없다.

### Phase 2 — 도메인 커널·DB 불변식

**목표:** UI/OCR 전에 기준·LOT·문서·검사·판정·승인 정본을 구현한다.

**작업 순서**

1. `Create: domain/common/decimal.py`; float 입력 거부 및 Decimal serialization 경계 테스트.
2. master/spec 도메인과 migration 작성. 활성 기준 유효기간 중복은 transaction lock + DB exclusion/unique constraint로 방어.
3. `material_lots`, `inbound_receipts`, `receipt_lot_allocations`, 문서/section/link를 migration으로 작성.
4. supplier/internal result, sample measurement의 XOR FK CHECK, mapping status, source/missing/sample policy를 작성.
5. 문서/검사 상태 머신을 순수 transition table로 작성하고 허용되지 않은 전이를 모두 테스트.
6. idempotency table, optimistic version, outbox, audit event, approval/decision snapshot, correction revision을 작성.
7. DB role/trigger guard로 finalized mutation과 audit deletion을 차단한다.

**테스트 우선 순서**

- 실패 테스트: float, 잘못된 단위 차원, 겹치는 ACTIVE 기준, terminal-state 직접 수정, approval 없는 final decision, internal/supplier sample FK 동시 지정, stale version, 중복 idempotency request.
- 최소 구현 후 단위 → repository integration → migration replay 테스트.

**완료 기준:** UI나 OCR 없이도 API/도메인 테스트가 기준 v1 고정, 다대다 LOT, 상태 전이, 승인 불변성을 증명한다.

### Phase 3 — 첫 번째 얇은 수직 슬라이스

**목표:** Fixture extraction으로 한 건의 실제 업무 흐름을 끝까지 작동시킨다. 외부 OCR은 아직 호출하지 않는다.

**Slice 시나리오**

1. 검사자가 염화칼슘 비드 master/spec v1을 승인 전 seed로 검토·활성화한다.
2. 입고·정본 LOT·입고 배분을 수동 등록한다.
3. 샘플 COA를 업로드해 immutable hash와 중복 후보를 생성한다.
4. `FixtureExtractionProvider`가 schema-valid 후보·confidence·bounding box를 반환한다.
5. OCR review 화면에서 수기값/추출값/원문 위치를 비교하고 최종값·사유를 확정한다.
6. document section과 receipt allocation을 후보 매칭하고 검사자가 확정한다.
7. inspection 생성 시 spec v1을 고정한다.
8. Decimal/단위/매핑/누락/출처 정책으로 후보 판정을 만든다.
9. 자체검사 필수 항목 미완료이면 `INTERNAL_TEST_PENDING/ON_HOLD`이고 승인 버튼이 서버에서 차단된다.
10. 자체 측정값 입력 후 재평가하고 검사자가 제출한다.
11. 팀장은 반려 또는 승인한다. 승인은 approval+snapshot+audit+outbox를 한 transaction으로 고정한다.
12. LOT 조회에서 입고·문서·검사·판정·감사 연결을 확인한다.

**주요 Create 경로**

- Backend routers/handlers: `backend/src/hyc_inspection/api/routers/{masters,specs,receipts,documents,inspections,approvals,lot_trace}.py`
- Fixture adapter: `backend/src/hyc_inspection/adapters/extraction/fixture.py`
- UI: `frontend/src/features/{receipts,documents,ocr-review,inspections,approvals,lot-trace}/`
- Tests: `backend/tests/integration/api/test_vertical_slice.py`, `frontend/tests/e2e/inspection-happy-path.spec.ts`, `frontend/tests/e2e/inspection-hold.spec.ts`

**완료 기준**

- AT-002, 003, 005~010, 013의 Fixture 기반 핵심 계약이 통과한다.
- 승인 후 직접 수정 API/DB 시도가 모두 거부되고 원본·추출·수정·최종값이 조회된다.
- 외부 OCR 장애를 시뮬레이션해도 수동 입고/자체검사는 가능하다.

**중단/롤백:** Slice가 schema 변경을 요구하면 아직 운영 데이터가 없을 때 migration을 교정하고 ADR을 갱신한다. UI로 우회하지 않는다.

### Phase 4 — OCR/문서 파싱 파일럿

**목표:** 실제 두 PDF를 대상으로 provider를 비교하되 자동 확정은 하지 않는다.

**작업**

1. 승인된 비식별 fixture와 annotation tool/JSON을 만든다.
2. text-layer 확인 → render → rotate/deskew/contrast → table detection → provider extraction → schema/logic validation을 단계별 artifact로 보존한다.
3. provider 결과를 동일 `ExtractionPort`와 schema로 정규화한다.
4. 두 문서 유형별 header/row/sample/bounding-box golden tests를 만든다.
5. 소수점/%/O-0/1-l/도장/병합셀/다중 LOT/암호화·손상 PDF 엣지 fixture를 합성 또는 마스킹 생성한다.
6. benchmark report는 정확도, recall/precision, correction time, latency, 비용, 보존정책을 분리한다.
7. 선택 provider와 model/prompt/schema version을 ADR로 고정하며 외부 전송 OFF가 기본이다.

**완료 기준:** AT-001/004 golden 조건과 PRD KPI 산식이 재현 가능하다. KPI 목표 미달이면 사람 검토율이 올라갈 뿐 자동 통과로 보정하지 않는다.

### Phase 5 — Core MVP 완성

**목표:** 모든 역할·상태·보고서·부적합 흐름과 38개 기준 Draft import를 완성한다.

**작업 묶음**

1. Local RBAC 사용자/서비스 계정, 최소 권한 API, 로그인 제한/세션 만료.
2. 38개 sheet import dry-run → 오류 보고 → DRAFT 생성 → 관리자 검토/활성화. 원문 좌표와 source document hash 보존.
3. 패키지 문서 가변 샘플/정성 결과, item alias 승인, conflict/unmapped hold.
4. 재검사 회차, 반려/재제출, 부적합/처리방안/특채/증빙/완료일.
5. Raw Data 호환 + Long + Documents + optional Audit 시트.
6. 승인 Snapshot 기반 통합 보고서, LOT 추적, 월별/공급사 품질 통계.
7. 기준/코드 import dry-run, feature flag 중앙 설정.
8. 관리자·검사자·팀장·조회자별 Playwright 시나리오.

**완료 기준:** AT-001~013 전체 및 DoD의 기능 항목이 추적표에서 green. 보고서는 live mutable table이 아니라 승인 Snapshot을 읽는다.

### Phase 6 — 운영 수집·관측·복구

**목표:** NAS/Drive와 비동기 운영을 안전하게 활성화한다.

**작업**

1. NAS stabilizing watcher: 크기/mtime 안정화, temp/lock 제외, 처리 완료 정책.
2. Drive cursor 기반 polling; API quota/backoff와 중복 idempotency.
3. outbox dispatcher, at-least-once worker, retry/circuit breaker, DLQ/replay 권한.
4. metrics/logs/traces, queue/storage/provider health, 실패 큐·복제 상태 UI.
5. backup/restore runbook과 disposable restore rehearsal.
6. malware scan, MIME/size/page/decompression limits, signed view URL, download audit.

**완료 기준:** worker를 임의 종료해도 원본·업무 상태가 유실되지 않고 재처리가 중복 승인/중복 보고서를 만들지 않는다.

### Phase 7 — 파일럿/UAT와 생산 전환 게이트

**목표:** 실제 품질팀 데이터로 정확도·업무시간·복구성을 측정하고 운영 승인 여부를 결정한다.

- 공급사/자재/스캔 난이도별 UAT 표본을 품질팀이 승인한다.
- PRD KPI를 정확도·자동확정률·수정시간으로 분리해 산출한다.
- 접근권한, 감사 누락 0, 원본/기준 연결 100%, restore rehearsal을 확인한다.
- RPO/RTO·보존·외부 AI·Primary/Mirror·운영 책임자를 확정한다.
- 생산 전환은 별도 승인이다. 테스트 통과만으로 외부 배포·실데이터 import를 허용하지 않는다.

## 6. DB 및 상태 머신 세부 계획

### LOT 관계 보정

PRD 표의 `receipt_lots.inbound_receipt_id`는 분할 입고 다대다 정책을 충분히 표현하지 못하므로 다음처럼 분리한다.

- `material_lots`: 공급사+품목+공급사 LOT+생산일의 정본 identity. identity 불충분 시 provisional UUID와 conflict 상태.
- `inbound_receipts`: 거래/입고 event.
- `receipt_lot_allocations`: receipt↔material_lot join, 수량·단위·수기/확정값·확정자.
- `inspection_cases.receipt_lot_allocation_id`: 해당 입고 배분의 검사 업무.
- 조회/보고는 `material_lot_id`로 분할 입고를 합친다.

이 결정은 API 명칭과 PRD 용어에 영향을 주므로 ADR과 OpenAPI description으로 사용자 용어를 보존한다.

### 주요 DB 제약

- nullable 외부 코드는 `WHERE code IS NOT NULL` partial unique index.
- 동일 checksum 정본은 unique, 업무 link는 별도 table.
- sample measurement는 internal/supplier result 중 정확히 하나만 참조하는 XOR CHECK.
- final decision은 approval/snapshot FK 없이는 저장 불가.
- active spec 기간 겹침은 scope key+date range exclusion constraint 또는 동등 transaction-safe guard.
- finalized inspection/document 원본/audit는 app role UPDATE/DELETE 금지 + trigger guard.
- 모든 업무 테이블 `version`으로 stale update를 409 처리.
- 모든 timestamp는 timezone-aware UTC.
- custom formula는 임의 Python/eval 금지. MVP는 allowlisted formula DSL이 없으면 `MANUAL`.

### 상태 전이 검증

- `DocumentTransitionService`: 현재 상태+명령+actor+preconditions → 새 상태/event.
- `InspectionTransitionService`: submit/return/approve/retest/hold/special-accept를 중앙 검증.
- UI는 허용 액션을 표시만 하며 권한의 정본이 아니다.
- property/state tests가 terminal→mutable, missing internal→accepted, inspector self-approval, admin business approval을 거부한다.

## 7. OCR·Golden Dataset 계획

### Golden schema

각 문서 fixture는 다음을 가진다.

- source hash와 redaction 상태
- page dimensions/DPI/rotation
- document section/LOT 경계
- header field raw/normalized/expected value
- test row raw item/spec/result/unit
- sample index와 개별 값
- page/bounding box polygon
- confidence 자체는 정답이 아니라 provider 관측값
- `must_review_reasons`와 허용 normalization

### 평가 원칙

- exact match와 normalized semantic match를 분리한다.
- 행 recall/precision, 숫자/단위 exactness, LOT, 누락 탐지율을 별도 지표로 낸다.
- provider benchmark가 실패해도 fixture/manual adapter로 핵심 업무를 계속할 수 있어야 한다.
- OCR 값 수정은 새 `field_review` event이며 raw extraction을 보존한다.
- 원문에서 보이지 않는 값을 LLM이 추론해 채우면 실패다.

## 8. 판정 엔진 계획

### 순수 입력/출력

`evaluate_inspection(spec_snapshot, supplier_results, internal_results, unit_registry, policy_version) -> DecisionCandidate`

- 입력은 불변 DTO이며 DB/session/provider 객체를 포함하지 않는다.
- 모든 수치는 string→Decimal로 파싱하고 float를 거부한다.
- 단위는 동일 dimension의 승인된 변환만 수행한다.
- supplier declared, supplier spec recalculated, HYC reference, internal, effective decision을 별도로 반환한다.
- required/mapping/missing/source/sample policy를 순서대로 적용한다.
- 결과는 item별 근거, conversion/formula version, warning, missing list, engine version을 canonical JSON Snapshot으로 직렬화한다.

### 테스트

- operator별 경계 바로 아래/같음/위 property tests
- `±`, inclusive/exclusive, ppm↔%, precision/rounding
- all/average/worst/min/max/manual 샘플 정책
- internal priority/all-must-pass/reference-only
- unmapped/low-confidence/missing/substitute/special/hold/reject
- 결과 순서나 JSON key 순서가 Snapshot hash를 흔들지 않는 canonicalization

## 9. 프론트엔드·UX 계획

- 목록 → 입고/LOT 등록 → 문서 업로드 → OCR review → 매칭 → 자체검사 → 제출 → 팀장 review → LOT trace의 작업 큐 중심 IA.
- 상세 화면은 좌측 supplier 문서/규격/결과, 우측 HYC 기준/자체결과를 텍스트 라벨과 색상 모두로 분리한다.
- PDF.js bounding-box overlay는 page coordinate 변환 unit test를 둔다.
- 숫자 입력은 문자열 상태로 유지해 browser float 오염을 막고 API에 canonical decimal string을 보낸다.
- autosave는 debounce+version+draft only. 409 conflict이면 overwrite하지 않고 비교 화면을 연다.
- 필수/저신뢰/부적합/보류 이유를 아이콘+텍스트+키보드 focus로 제공한다.
- 승인·특채·문서 재연결은 confirmation, 사유, expected version이 필수다.
- 작은 화면은 Tab 전환하되 MVP 기준 1440px keyboard workflow를 우선한다.

## 10. 인수 기준 추적표

|인수 기준|주 구현 단계|대표 테스트 Create 경로|핵심 검증|
|---|---:|---|---|
|AT-001 염화칼슘 COA|P4|`backend/tests/golden/test_calcium_chloride_coa.py`|행/LOT/spec/result/bbox, 도장 저신뢰, 손글씨 참고|
|AT-002 규격 분리|P2/P3|`backend/tests/unit/judgment/test_supplier_vs_hyc_spec.py`|두 규격·판정 필드 독립|
|AT-003 누락 대체|P2/P3|`backend/tests/integration/api/test_internal_substitute_hold.py`|미완료 승인 차단|
|AT-004 가변 샘플|P4/P5|`backend/tests/golden/test_domestic_8p_samples.py`|5개/3개 값 무손실|
|AT-005 교차검증|P3|`frontend/tests/e2e/cross-validation.spec.ts`|원문/OCR/수기/사유|
|AT-006 단위 변환|P2|`backend/tests/unit/judgment/test_unit_conversion.py`|공식 버전·Decimal|
|AT-007 자체 결과 우선|P2|`backend/tests/unit/judgment/test_source_policy.py`|supplier 보존, internal effective|
|AT-008 중복 문서|P3|`backend/tests/integration/api/test_document_dedup.py`|정본 1개, 재사용 link|
|AT-009 기준 버전|P2/P3|`backend/tests/integration/db/test_spec_snapshot_immutability.py`|v2 후 v1 유지|
|AT-010 승인|P3|`backend/tests/integration/api/test_approval_atomicity.py`|snapshot/audit/lock 원자성|
|AT-011 부적합|P5|`frontend/tests/e2e/nonconformance.spec.ts`|처리/승인/목표/증빙/재검사|
|AT-012 Raw Data|P5|`backend/tests/integration/reports/test_raw_excel_lossless.py`|호환+Long, 샘플 무손실|
|AT-013 LOT 조회|P3/P5|`backend/tests/integration/api/test_split_lot_trace.py`|분할 입고 전체 연결|

### Definition of Done 매핑

- Migration/seed 재실행: P1/P2/P5 migration replay suite
- 38개 기준 Draft import: P5 importer snapshot/dry-run test
- 입고/LOT·교차검증·다대다: P2/P3 API+E2E
- 두 PDF OCR/golden: P4
- HYC 판정·자체검사·가변 샘플: P2/P3/P4
- 승인·5개 최종 상태·불변성·감사: P2/P3/P5
- 4종 출력: P5 snapshot/report tests
- Unit/Integration/E2E/OpenAPI: P1부터 누적
- 운영/백업/복구/사용자 가이드: P6/P7
- 외부 Secret 없음: 모든 phase CI gate

## 11. 검증 명령 제안

아직 파일이 없으므로 아래는 구현 후의 **정확한 목표 명령**이며 현재 성공했다고 주장하지 않는다.

```bash
# bootstrap / services
uv python pin 3.12
uv sync --project backend --all-groups
pnpm --dir frontend install --frozen-lockfile
docker compose up -d postgres redis

# backend quality
uv run --project backend ruff check backend
uv run --project backend mypy backend/src
uv run --project backend pytest backend/tests/unit -q
uv run --project backend pytest backend/tests/integration -q
uv run --project backend pytest backend/tests/contract backend/tests/golden -q

# migration reversibility on disposable DB
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini downgrade base
uv run --project backend alembic -c backend/alembic.ini upgrade head

# frontend
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test

# full contract/compose smoke
./scripts/check.sh
./scripts/secret-scan.sh
./scripts/backup.sh --target /tmp/hyc-backup-test
./scripts/restore-verify.sh /tmp/hyc-backup-test

git diff --check
```

기대 결과는 각 명령 exit 0, migration round-trip 후 schema 동일, E2E에서 승인/보류/중복/분할 LOT 흐름 통과, restore 대상의 row/hash manifest 일치다. 구체 테스트 개수·성능 수치는 구현 결과 전에는 기재하지 않는다.

## 12. 리스크·관측성·운영·보안

### 핵심 위협 모델

- 악성/손상 PDF, path traversal, MIME spoof, decompression bomb
- 외부 OCR로 민감 문서 반출·provider 학습/보존
- 검사자 self-approval, 관리자 업무승인 권한 혼합
- 승인/특채 API replay, stale autosave overwrite
- DB 운영자/우회 코드가 승인본·감사를 수정
- 보고서가 최신 mutable row를 읽어 과거 결과 변조
- worker retry가 문서/보고서/승인을 중복 생성
- signed URL·로그·오류 응답을 통한 원본/PII 노출

### 필수 관측성

- correlation/causation/idempotency ID가 API→outbox→worker→provider에 이어진다.
- 문서 상태별 count/age, queue depth/DLQ, OCR latency/cost/error, low-confidence rate, correction time, duplicate rate, match ambiguity, approval dwell time, storage replication failure를 metric으로 수집한다.
- 구조화 log에는 secret, 원본 문서 본문, 전체 OCR raw output을 넣지 않는다.
- readiness는 DB/queue/storage 의존성을 구분하고, OCR 장애는 API 전체 down으로 만들지 않는다.

### 운영 게이트

- 백업 암호화·접근권한·복원 리허설
- 운영 DB role과 migration role 분리
- 외부 AI provider DPA/retention/training/data-region 결정
- RPO/RTO와 보존기간 승인
- UAT 사용자/승인자 매핑 및 권한 검토
- 실데이터 import dry-run/오류 보고/사용자 승인

## 13. 범위 통제

### MVP에서 하지 않음

- ERP/MES/WMS 실시간 연동, 생산/완제품 LOT 자동 연결
- AQL sample size/Ac/Re 계산
- 검사 장비 직접 연동
- 손글씨 핵심 필드 자동 확정
- 자동 메신저/메일, 공급사 포털, CAPA 전체, 공인전자서명
- AI 최종 판정, AI 기반 규격 자유해석, 자동 전역 별칭 학습
- Kubernetes/마이크로서비스 분해, 다중 공장 완성형 기능

### 후속 seam만 둠

- `ErpPort`, BOM/production link migration은 feature flag OFF
- `AuthPort`로 SSO 교체
- `StoragePort`, `ExtractionPort`, `ReportRendererPort`
- domain event/outbox로 알림·scorecard·이상추세 확장

## 14. 권장 실행 순서와 병렬 lane

1. **AP-0:** 데이터/배포/LOT/auth/fixture 정책 승인
2. Evidence lane: source hash manifest + golden annotation 규칙
3. Contract lane: extraction/error/OpenAPI schema
4. Data lane: master/spec/LOT/document/inspection migration과 제약
5. Domain lane: Decimal/unit/spec selection/state/judgment pure tests
6. API lane: idempotent command/query, audit/outbox, RBAC
7. Web lane: 생성 client 기반 receipt/document/review/approval UX
8. Slice integration: fixture provider로 end-to-end 업무 1건
9. OCR lane: 두 PDF golden/provider benchmark — domain과 병렬 가능
10. Import/report lane: 38 sheet Draft import, Raw/통합/LOT/통계
11. Ops lane: NAS/Drive, retry/DLQ, observability, backup/restore
12. UAT/production decision packet

Data+Domain은 계약 확정 후 부분 병렬화할 수 있고, Web은 OpenAPI contract 이후 mock server로 병렬화할 수 있다. OCR provider 비교는 extraction schema 이후 독립 수행한다. 승인/불변성/보고서 Snapshot은 하나의 통합 lane으로 검증하며 분리 구현 후 자가 승인하지 않는다.

## 15. 계획 상태

- 이 문서는 Hermes가 Claude 계획을 읽기 전에 `Prd.md`와 로컬 자료만으로 작성한 독립 계획이다.
- 구현, 설치, migration, commit, push, 배포는 수행하지 않았다.
- 현재 원본 자료가 모두 untracked이므로 데이터 분류와 초기 Git baseline 정책이 AP-0에 포함된다.
- 최종 계획은 Claude Code Opus 5 독립 계획과 항목별 비교한 뒤 장점만 취해 별도 통합 문서로 확정한다.
