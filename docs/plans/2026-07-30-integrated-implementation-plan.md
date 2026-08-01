# 한양화학 수입검사 디지털화 및 LOT 추적 시스템 — 통합 구현 계획

**문서 상태:** `P0A_P0B_P1_P2_P3_SOURCE_COMPLETE_ACCEPTED_P3_GIT_INTEGRATION_PENDING`
**정본 요구사항:** `Prd.md`  
**독립 입력:** `2026-07-30-hermes-independent-plan.md`, `2026-07-30-claude-opus5-independent-plan.md`  
**요구사항 추적 정본:** [`../TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md) — 52개 FR, UI/매칭/데이터/API/보고서, 보안/감사/NFR/OCR, AT/DoD를 Phase·owner·planned test·gate에 연결  
**독립 QA:** [`../reviews/2026-07-30-integrated-plan-alfred-qa.md`](../reviews/2026-07-30-integrated-plan-alfred-qa.md) — Alfred R1 formal/substantive **PASS**, 이전 HIGH/MEDIUM 5건 모두 `RESOLVED`, 신규 HIGH/MEDIUM blocker 0  
**작성 원칙:** 두 계획의 공통 결론과 상호 보완되는 장점만 채택했다. 충돌 사항은 PRD의 fail-closed 원칙, 데이터 무결성, 실행 가능성 순으로 판정했다.  
**권한 경계:** AP-01~05는 승인됐다. P0A/P0B/P1/P2/P3 source increments는 complete·accepted이고 P2는 독립 Hermes QA와 final Claude source-diff gate를 통과한 뒤 별도 Git 승인으로 committed, fresh-main integrated, `origin/main`에 delivered 됐다. 2026-08-01 별도 사용자 승인에 따라 구현한 P3 수직 Slice도 final independent backend/UI/API review와 Hermes controller QA를 통과했다. 다만 P3는 이 문서 작성 시점 uncommitted/unintegrated/unpushed exact candidate이며, source acceptance는 Git integration, deployment, release 또는 운영 활성화를 뜻하지 않는다. P4/P5는 unstarted이고 실데이터 apply/import, 외부 OCR/AI, 비일회성/production migration, production DB-role activation, public service exposure는 미승인이다.

---

## 1. 결론 요약

권장 구현은 **PostgreSQL 정본 + FastAPI 모듈형 모놀리스 + 별도 Celery 작업자 + Next.js UI**다. OCR/LLM은 문서에서 구조화 후보와 confidence를 만드는 Adapter일 뿐이며, 확정값은 사람이 검토한다. 최종 판정은 외부 AI와 완전히 분리된 Decimal 기반 결정론적 도메인 엔진이 산출한 후보를 검사자 제출과 팀장 승인으로 확정한다.

첫 개발 목표는 “OCR 전체 자동화”가 아니다. **염화칼슘 비드 한 건을 Fixture extraction으로 입고/LOT → 원본 업로드·해시 중복 → 사람 검토 → 기준 버전 고정 → 판정 → 자체검사 보류 → 제출/승인 → 불변 Snapshot/감사 → LOT 조회까지 실제 UI/API로 관통하는 얇은 수직 슬라이스**다. 이 Slice가 통과한 뒤에만 실제 OCR Provider를 비교한다.

### 최우선 설계 결정

1. 정본 LOT와 입고 이벤트를 분리한다: `material_lots` ↔ `inbound_receipts`를 `receipt_lot_allocations`가 연결한다.
2. 기준 프로파일은 공통 범위를 표현하도록 `material_id NOT NULL`, `supplier_id NULL`, `model_id NULL`을 직접 보유한다.
3. 공급사 규격/공급사 판정과 한양화학 기준/판정을 데이터·API·화면·보고서에서 별도 필드로 유지한다.
4. 엔진 후보는 `ACCEPTED / REJECTED / ON_HOLD`만 반환한다. `RETEST / SPECIAL_ACCEPTED`는 사람의 상태 전이 결과다.
5. 검사 회차(retest)와 승인본 정정 revision은 서로 다른 축이다.
6. 승인 당시 문서 hash, 기준 값, 결과, 엔진/정책 버전, 판정 근거를 Snapshot에 값으로 복사한다. FK만 저장하지 않는다.
7. 불변성과 감사는 앱 가드만 믿지 않고 DB 제약·권한·트리거로 이중 방어한다.

## 2. 두 독립 계획 비교와 통합 선택

|영역|Claude Code Opus 5의 강점|Hermes의 강점|통합 선택|
|---|---|---|---|
|PRD 해석|C1~C11로 내부 모순을 구체화: 공통 spec scope 불가, 자체 우선/BOTH_ALL 충돌, 엔진 결과와 workflow 상태 혼선, 재검사/정정 축 혼선|현재 저장소·untracked 원본·데이터 배치/반출·fixture Git 정책까지 실행 전 위험으로 연결|Claude의 모순 목록을 채택하고 Hermes의 AP-0 운영 결정을 결합|
|아키텍처|Port별 구체 메서드, 동기/비동기 경계, domain import 0 검증, Provider raw output reference|실제 배포 단위, correlation/outbox, 원본 격리·승격, 보고서 Snapshot, 복구 흐름|모듈형 모놀리스+worker, pure domain, Outbox, Port/Adapter 전부 채택|
|LOT 모델|문서↔LOT M:N과 분할 입고 계약 테스트를 명확히 요구|입고 1:N `receipt_lots`만으로는 정본 동일 LOT 분할을 충분히 표현하지 못함을 지적하고 canonical lot+allocation 제안|Hermes의 `material_lots`+`receipt_lot_allocations`를 채택, Claude의 M:N 계약 테스트를 적용|
|기준/판정|공통 spec scope 모순, 3개 엔진 후보와 5개 업무 종결상태 분리, GIST 기간 중복 제약|기준 import 승인 게이트, canonical Snapshot, unit/sample/missing/source policy 순서와 파일럿 격리|양쪽 장점을 결합해 DB scope와 순수 엔진 계약을 고정|
|수직 Slice|OCR/NAS/Drive 없이도 업무 완주해야 한다는 구조적 증거와 정확한 API 흐름|파일 해시 격리, fixture extraction, true LOT trace, correction/audit까지 운영 안전성 포함|Fixture 기반 Slice를 첫 제품 increment로 확정|
|OCR|Golden 채점기를 Provider보다 먼저, exact/semantic 지표 분리, provider raw output ref|외부 전송 기본 OFF, 승인된 비식별 fixture, scanner/file validation, 대표성 승인 게이트|두 방식을 결합. Claude 초안의 임의 “10건 미만 중단” 숫자는 채택하지 않고 품질팀 승인 표본으로 대체|
|보안/권한|ADMIN은 업무 승인 권한이 없다는 직무분리, idempotency request hash, import-linter|malware/MIME/page/decompression 방어, 실문서 Git 분류, DB 역할 분리, restore rehearsal|모두 채택. 비상 권한도 별도 permission+사유+감사|
|실행 계획|Create 경로와 acceptance test 이름이 구체적|AP-0, phase 진입/중단/롤백, Orca/Codex 실행 lane, 실제 문서화·Kanban 동기화|작은 dependency task+검증 gate로 재구성|

### 채택하지 않은 부분

- 근거 없는 OCR 최소 문서 수·일정·성능 수치: 품질팀이 문서 유형/공급사/난이도별 대표성을 승인하도록 바꾼다.
- 단순 `inbound_receipts 1:N receipt_lots`만으로 동일 정본 LOT를 그룹 집계하는 방식: 정본 identity와 입고 배분을 분리한다.
- 전역 Soft Delete만으로 승인 불변성을 표현하는 방식: Snapshot/audit는 append-only이며 finalized 업무 데이터 정정은 신규 revision으로만 한다.
- OCR Provider, 클라우드, RPO/RTO, 반올림 정책의 조기 고정: Adapter/버전 설정으로 격리하고 파일럿 근거 후 승인한다.

## 3. AP-0 — 구현 전 사용자 결정 게이트

|ID|결정|권장 기본값|승인 전 허용 범위|
|---|---|---|---|
|AP-01|배포·데이터 위치|사내망 Mac/Linux Docker Compose, DB+원본은 사내 저장소; 공개 배포 없음|문서·설계만|
|AP-02|외부 AI/OCR 전송|기본 OFF. 데이터 보존·학습·지역·계약 검토 후 Provider별 opt-in|Fixture Provider만|
|AP-03|정본 LOT 모델과 identity policy|`material_lots`+`receipt_lot_allocations`; 파일럿 key는 공급사+품목+NFKC/trim LOT No., production date는 기본 key 아님; 공급사별 재사용 근거가 있으면 versioned policy로 확장|스키마 ADR/테스트 설계|
|AP-04|인증원·역할|파일럿 Local Auth+Argon2id; `INSPECTOR/LEAD/ADMIN/VIEWER/SERVICE`, ADMIN은 승인 불가|Auth Port/권한 표 설계|
|AP-05|현재 PDF/XLSX의 Git 보관|실원본은 커밋 금지, 승인된 마스킹 fixture+hash manifest만 Git|hash/분류 dry-run|
|AP-06|Primary/Mirror storage|개발 Local, 파일럿 NAS Primary; Drive는 선택 Mirror|Storage Port 구현|
|AP-07|판정 정책 기본|누락·미매핑·저신뢰·자체검사 미완은 `ON_HOLD`; 불명 규격은 `MANUAL`|순수 엔진 fail-closed 테스트|
|AP-08|생산 전환 조건|AT/DoD, UAT, 권한 검토, backup/restore rehearsal, RPO/RTO 승인 후 별도 전환 승인|로컬 파일럿까지만|

AP-01~05는 2026-07-30 권장 기본값대로 승인됐다. P0A/P0B/P1/P2/P3 source increments는 complete·accepted이고 각 source gate가 통과했다. P3는 2026-08-01 별도 구현 승인과 최종 독립 review/controller QA를 완료했지만 exact-candidate Git integration은 아직 수행하지 않았다. AP-06~08의 파일럿/생산 활성화, P4/P5 착수, 실데이터 apply/import, 외부 OCR/AI, 비일회성/production migration, production DB-role activation, 배포와 서비스 공개는 별도 승인 대상이며 현재 blocked/미승인이다.

## 4. 목표 아키텍처

### 4.1 프로세스와 의존 방향

```text
Next.js Web ─HTTP/OpenAPI─> FastAPI API ─transaction─> PostgreSQL
                                  │                         │
                                  │                         └─ outbox_events
                                  │                                  │
                                  ├─ JudgmentEngine (pure/sync)      └─ Relay → Redis/Celery
                                  ├─ StoragePort                            ├─ ingest/hash/scan
                                  ├─ AuthPort                               ├─ preprocess/OCR/parse
                                  └─ ReportRendererPort                     ├─ report/mirror
                                                                             └─ DLQ/replay
```

의존 방향은 `domain ← application ← ports/adapters ← api/workers/infrastructure`다. `domain`은 FastAPI, SQLAlchemy, Celery, OCR SDK를 import하지 않는다. CI의 import-linter가 이를 강제한다.

### 4.2 동기 처리

- 입고/LOT 등록·확정
- 문서/LOT 매칭 확정
- 최종값 Human Review
- 기준 버전 선택·고정
- 판정 엔진 실행
- 자체검사 입력
- 제출/반려/승인/특채/재검사 전이
- LOT 조회

판정은 저비용 순수 함수이고 승인 직전 동일 transaction에서 최신 입력으로 재실행해야 하므로 큐로 보내지 않는다.

### 4.3 비동기 처리

- 수집, malware/MIME 검증, 전처리, OCR, 구조화
- 대용량 기준/마스터 import dry-run·적용
- 보고서 렌더링, Mirror 복제
- Outbox relay, retry, DLQ

모든 consumer는 `event_id`와 업무 idempotency key를 기록해 at-least-once 재처리를 무해하게 만든다.

### 4.4 Port 계약

- `StoragePort.put/get/exists/checksum/copy/signed_view_url/health_check`
- `DocumentSourcePort.list_new/fetch/mark_processed`
- `ExtractionPort.extract(document_ref, schema_version) -> RawExtraction`
- `ParserPort.parse(raw, parser_profile) -> ExtractionCandidate`
- `ReportRendererPort.render(report_kind, approved_snapshot) -> bytes`
- `ClockPort.now`, `IdPort.new_id`, `MalwareScannerPort.scan`
- `AuthPort.authenticate/resolve_roles`
- `ErpPort`는 MVP no-op, 호출 경로는 feature flag OFF

Provider 원문은 DB에 전체 복제하지 않고 보안 저장소의 immutable `raw_output_ref`와 hash를 참조한다.

## 5. 계획된 신규 파일 구조

아래는 모두 현재 없는 **Create 대상**이다.

```text
Create: README.md
Create: AGENTS.md
Create: .gitignore
Create: .env.example
Create: Makefile
Create: compose.yaml
Create: backend/pyproject.toml
Create: backend/alembic.ini
Create: backend/migrations/{env.py,versions/}
Create: backend/src/hyc_inspection/api/{main.py,deps.py,errors.py,routers/}
Create: backend/src/hyc_inspection/domain/common/{decimal.py,errors.py,events.py,ids.py}
Create: backend/src/hyc_inspection/domain/master/models.py
Create: backend/src/hyc_inspection/domain/specifications/{models.py,parser.py,selection.py}
Create: backend/src/hyc_inspection/domain/receipts/{models.py,states.py}
Create: backend/src/hyc_inspection/domain/documents/{models.py,states.py,matching.py}
Create: backend/src/hyc_inspection/domain/inspections/{models.py,states.py,policies.py}
Create: backend/src/hyc_inspection/domain/judgment/{engine.py,units.py,samples.py,snapshot.py}
Create: backend/src/hyc_inspection/domain/approvals/policies.py
Create: backend/src/hyc_inspection/application/{commands/,queries/,services/,uow.py,authz.py,idempotency.py}
Create: backend/src/hyc_inspection/ports/{storage.py,extraction.py,queue.py,auth.py,clock.py,scanner.py,reports.py,erp.py}
Create: backend/src/hyc_inspection/adapters/db/{models.py,repositories.py,uow.py}
Create: backend/src/hyc_inspection/adapters/storage/{local.py,nas.py,drive.py}
Create: backend/src/hyc_inspection/adapters/extraction/{fixture.py,provider.py,pdf_preprocess.py,parser.py}
Create: backend/src/hyc_inspection/adapters/queue/celery_app.py
Create: backend/src/hyc_inspection/adapters/reports/{raw_excel.py,integrated.py,lot_trace.py,quality_stats.py}
Create: backend/src/hyc_inspection/workers/{tasks.py,outbox.py}
Create: backend/scripts/{import_spec_workbook.py,import_raw_data.py,seed_dev.py}
Create: backend/tests/{unit/,integration/,contract/,golden/,fixtures/,factories/}
Create: frontend/package.json
Create: frontend/pnpm-lock.yaml
Create: frontend/src/app/
Create: frontend/src/features/{receipts,documents,ocr-review,inspections,specs,approvals,lot-trace,reports}/
Create: frontend/src/components/{SupplierPanel.tsx,InternalPanel.tsx,PdfViewer.tsx,BoundingBoxOverlay.tsx,SampleGrid.tsx,DecisionBadge.tsx,CrossCheckField.tsx,WarningList.tsx}
Create: frontend/src/lib/{api,auth,decimal,forms,status}/
Create: frontend/tests/{unit,e2e}/
Create: contracts/{extraction/v1.schema.json,errors/v1.schema.json,generated/openapi.json}
Create: fixtures/manifests/source-documents.yaml
Create: fixtures/golden/{calcium-chloride-coa/,domestic-8p-package/}
Create: fixtures/spec-import/qm301-7-expected.json
Create: infra/docker/{api.Dockerfile,web.Dockerfile,worker.Dockerfile}
Create: infra/observability/
Create: scripts/{bootstrap.sh,check.sh,backup.sh,restore-verify.sh,secret-scan.sh}
Create: docs/adr/
Create: docs/runbooks/
Create: docs/{TRACEABILITY_MATRIX.md,OCR_BENCHMARK.md,SECURITY.md,USER_GUIDE.md,DEVLOG.md,KANBAN.md}
```

## 6. 구현 로드맵과 의존성

### P0A — 승인 전 읽기 전용 Evidence/결정 패킷

**실행 상태:** `COMPLETE` — [`../evidence/2026-07-30-p0a-evidence-freeze.md`](../evidence/2026-07-30-p0a-evidence-freeze.md), 원본 before/after hash·size·mtime 재검증 PASS.  
**선행:** 없음.  
**허용:** 기존 파일 읽기, 현재 hash/metadata 산출, 문서·계획·추적표 작성만 허용한다. 신규 parser/애플리케이션 코드 작성, DB/import 실행, fixture 복제, 외부 전송은 금지한다.  
**목표:** 원본을 변경·유출하지 않고 현재 관찰과 AP-0 질문을 고정한다.

|Task|작업|산출물/검증|완료 게이트|
|---|---|---|---|
|P0A.1|기존 도구로 PDF/XLSX hash·형식·크기·민감도 관찰|planning evidence; 원본 mtime/hash 전후 비교|원본 불변, 본문/secret 미복제|
|P0A.2|PRD와 현재 tool extraction의 38 sheets/119 rows 관찰 차이를 기록|검증 전 수치에는 `UNVERIFIED` 표시|코드·DB 없이 discrepancy만 보고|
|P0A.3|AP-01~08와 모순 C1~C6 기록|통합 계획과 향후 `docs/adr/` 후보|사용자 AP-01~05 답변|
|P0A.4|FR/정책/NFR/AT/DoD 추적 정본 작성|`docs/TRACEABILITY_MATRIX.md`|각 행에 Phase/owner/planned test/gate 존재|

### P0B — 승인 후 Evidence tooling/fixture bootstrap

**선행:** AP-01~05와 **P0B 구현 착수에 대한 명시적 사용자 승인**.  
**목표:** 승인된 범위 안에서 재현 가능한 importer dry-run과 비식별 fixture를 만든다.
**실행 상태:** `COMPLETE_ACCEPTED` — frozen tracked diff SHA-256 `7f7be3324c4040bfc4b47a35f7d3643d22eb618ea380a2d30acbc0aaaf4b5b2c`; final independent review `APPROVE` after 67 in-memory probes (HIGH 0, MEDIUM 0). generic scheme-specific URI semantics의 accepted LOW note는 consumed relationship role의 exact allowlist 때문에 defense-in-depth다. Controller evidence: `127 passed`; approved real QM301 dry-run 38 templates/119 rows, discrepancy 0, DB write/apply 0, source hash/size/mtime unchanged, tracked sensitive documents 0.

|Task|작업|산출물/테스트|완료 게이트|
|---|---|---|---|
|P0B.1|tests-first 기준 workbook parser 작성|`backend/scripts/import_spec_workbook.py --dry-run`; `backend/tests/integration/importers/test_spec_workbook_dry_run.py`|원본 read-only, DB write 0|
|P0B.2|38 sheets/119 rows 재검증과 discrepancy fixture|`fixtures/spec-import/qm301-7-expected.json`|불일치 자동 보정 금지, QUALITY review|
|P0B.3|AP-05가 허용한 hash manifest/마스킹 fixture만 생성|`fixtures/manifests/source-documents.yaml`|원본 Git/외부 전송 없음, 민감도 승인|
|P0B.4|승인 답변을 ADR로 확정|`docs/adr/0001-*`~`0004-*`|ADR와 계획/추적표 일치|

**중단:** 원본 Git/외부 전송 권한, LOT identity policy, 승인자 identity가 불명확하거나 AP-0 답이 계획과 충돌하면 P1을 시작하지 않고 계획을 개정한다.

### P1 — Repository/Contract foundation

**선행:** AP-01~05 및 accepted P0B (충족). **실행 상태:** P1은 사용자 승인 Hermes 직접 QA 후 complete/accepted 되었고 P1 contract gate를 통과했다. P2도 독립 Hermes QA와 final Claude source-diff gate 후 complete/accepted다.
**목표:** 재현 가능한 개발환경과 계약을 먼저 만든다.

1. `compose.yaml`, backend `uv` Python 3.12, frontend pnpm/TypeScript strict, lockfiles, CI를 생성한다. 전역 Python은 변경하지 않는다.
2. PostgreSQL/Redis/API/worker/web healthcheck와 placeholder-only `.env.example`을 만든다.
3. extraction/error schema를 JSON Schema+Pydantic으로 정의하고 round-trip/unknown-field/required-field contract tests를 먼저 작성한다.
4. UTC 저장/Asia-Seoul 표시, decimal string, UUID, correlation/error envelope를 API contract로 고정한다.
5. OpenAPI 생성과 frontend client drift check를 CI에 넣는다.

**대표 Create tests**

- `backend/tests/contract/test_extraction_contract.py`
- `backend/tests/contract/test_openapi_contract.py`
- `frontend/src/lib/api/generated.ts`

**게이트:** clean machine bootstrap, migration 빈 head, schema round-trip, lint/type/test/build, secret scan이 실제 명령으로 통과하고 Hermes가 독립 증빙을 승인해야 P2로 간다.

**2026-07-31 remediation evidence:** backend lock/sync, root pytest (`172 passed`, including unchanged accepted P0B `127 passed`), P1 Ruff/mypy, compileall, contracts drift, SQLite upgrade→downgrade→upgrade, secret/sensitive scans, Compose config, and diff checks passed locally. Hermes controller verified frozen installation with `next`/`eslint-config-next` 15.5.22, warning-free frontend lint, typecheck, Vitest (`1 passed`), production build, and byte-for-byte generated-client drift check. The ESLint 9 `FlatCompat` bridge exports a named config, and the drift checker executes project-local `openapi-typescript`, safely reports spawn errors, and cleans its temporary directory. Hermes also built the Compose images successfully; the original startup correctly aborted and cleaned up because its `127.0.0.1:8000` host binding collided with another approved local backend. Compose uses parameterized loopback host ports (default API 18000, web 13000), while container ports remain 8000/3000 and PostgreSQL/Redis remain unpublished. On the focused rerun PostgreSQL, Redis, API, and worker were healthy, but web was unhealthy because Next standalone bound only to the container hostname and its `127.0.0.1:3000` healthcheck received `ECONNREFUSED`. The production web image now fixes `HOSTNAME=0.0.0.0` and `PORT=3000`; host publication stays loopback-only. Full runtime health probes and the disposable PostgreSQL cycle remain pending a Hermes rerun; this is not a P1 contract-gate pass.

### P2 — Pure domain + DB invariants

**선행:** independently accepted P1 contract gate (충족). **실행 상태:** P2.1–P2.8은 독립 Hermes QA와 final Claude source-diff `PASS` (BLOCKER 0, MAJOR 0, MINOR 1) 후 source-complete·accepted다. 별도 명시적 사용자 승인으로 P2는 committed, fresh-main clean integration 되었고 source commit `996056b`와 first integration-documentation commit `58e963c`가 `origin/main`에 delivered 됐다. `58e963c`는 verified first-push/integration-evidence commit 및 durable ancestor이고, 이 post-push docs reconciliation은 later descendant이며 Git history가 live tip의 정본이다. 이후 별도 승인된 P3도 source-complete·accepted 상태에 도달했으나 Git integration은 아직 수행하지 않았다.
**목표:** UI/OCR 전에 정본 모델과 fail-closed 규칙을 증명한다.

|Task|의존|구현/테스트|
|---|---|---|
|P2.1 Decimal/단위 값객체|P1|float 거부, dimension, conversion/rounding version; `unit/test_decimal_boundary.py`, `test_units.py`|
|P2.2 Master/spec scope|P2.1|nullable supplier/model scope, DRAFT/ACTIVE/version/effective range; `test_spec_selection.py`|
|P2.3 LOT/입고 관계|P1|`material_lots`, `inbound_receipts`, `receipt_lot_allocations`; versioned identity policy/key, provisional/conflict/merge, 동시 생성, 동일 LOT 재입고·분할 입고 계약 테스트|
|P2.4 문서/section/link|P2.3|immutable checksum, section↔allocation M:N, canonical dedupe|
|P2.5 결과/샘플/mapping|P2.1~4|supplier/internal 분리, sample XOR FK, alias/manual confirmed|
|P2.6 판정 엔진|P2.1/2/5|mapping→parse/type→unit→sample→supplier/HYC/internal decision→source→missing→overall의 순수 평가와 canonical snapshot|
|P2.7 상태 머신|P2.3~6|document/case transition table, role/guard/reason, 엔진 3상태와 workflow 5상태 분리|
|P2.8 승인/감사/멱등|P2.6/7|expected version, request hash, approval/snapshot/audit/outbox atomicity, correction revision|

**DB 비가역성 방어**

- app role은 finalized/snapshot/audit에 UPDATE/DELETE 권한 없음
- 핵심 finalized mutation trigger 거부
- active spec range overlap은 scope key+GIST exclusion 또는 동등 DB-safe constraint
- `material_lots(supplier_id, material_id, identity_policy_version, identity_key)` UNIQUE; concurrent create는 unique conflict/upsert로 기존 canonical id 반환
- 필수 identity component 누락은 `PROVISIONAL/CONFLICT_REVIEW`; 자동 merge·최종 판정 연결 금지. merge는 row/advisory lock, expected version, 이중 권한, `merged_into_id`, append-only audit
- sample source `CHECK(num_nonnulls(internal_result_id,supplier_result_id)=1)`
- operator별 필수 컬럼 CHECK
- approval 없는 final decision 저장 거부
- 모든 업무 row에 `version`; `If-Match` 불일치는 409

**게이트:** migration upgrade→downgrade→upgrade, domain infra import 0, property/boundary/state/constraint integration tests 통과.

**수용된 follow-up N-M3:** 현재 스키마에서는 광범위한 직접 `inspection_cases` INSERT/UPDATE와 네 개 append-only evidence 테이블 INSERT 권한을 모두 가진 app-role DB-direct writer가 unfinalized case를 바로 `LEAD_REVIEW`로 생성한 뒤 완전하고 유효한 근거를 넣어 확정할 수 있어 중간 상태 이력을 우회할 수 있다. N1 판정 무결성, 근거 필수성, 확정 후 불변성은 유지된다. 이 defense-in-depth gap은 fixed가 아니며 production DB-role 활성화 전에 P3 correction-revision flow와 함께 재검토한다.

### P3 — 첫 작동 수직 Slice

**선행:** accepted P2 (충족). **현재 gate:** P3 구현은 별도 명시적으로 승인됐고 final independent backend/UI/API review와 Hermes controller QA를 통과해 source complete·accepted다. 문서 작성 시점에는 아직 uncommitted/unintegrated/unpushed exact candidate이며 Git integration 대기 상태다.
**범위:** 염화칼슘 비드 1개 품목/기준/실제 허가 fixture. 모델은 일반화하되 다른 문서 유형 UI는 만들지 않는다.

1. 검사자가 수동 입고, 정본 LOT, 입고 배분을 등록한다.
2. 문서를 격리 저장하면서 SHA-256을 계산한다. 동일 hash이면 새 canonical 원본 대신 기존 문서 링크 선택지를 준다.
3. `FixtureExtractionProvider`가 schema-valid 후보, confidence, page/bbox를 반환한다. 상태는 항상 `REVIEW_REQUIRED`에서 시작한다.
4. 검토 화면에서 원문/OCR/수기/최종값과 사유를 함께 확정한다. 저신뢰·필수 누락·논리 모순은 숨길 수 없다.
5. document section↔receipt allocation 후보를 검사자가 확정한다.
6. inspection 생성 시 우선순위로 spec을 선택하고 `spec_version_id`와 규격 값 Snapshot을 고정한다.
7. Decimal 엔진이 supplier 규격 재계산, HYC 참고 판정, internal 판정, effective candidate를 각각 출력한다.
8. 자체검사 필요 항목 미완이면 `ON_HOLD/INTERNAL_TEST_PENDING`; 서버가 제출/승인을 차단한다.
9. 자체 결과 입력 후 재평가, 검사자 제출, 팀장 반려/승인을 수행한다. 검사자와 ADMIN의 승인 시도는 403이다.
10. 승인 transaction에서 재평가+approval+decision snapshot+audit+outbox를 원자 저장한다.
11. 승인 후 direct PATCH/DB app-role mutation은 거부된다. 정정은 새 revision, 재검사는 새 inspection round다.
12. LOT 검색에서 분할 입고, 원본, section, 결과, 기준 버전, 승인, 감사 연결을 조회한다.

**대표 Create tests**

- `backend/tests/integration/api/test_vertical_slice.py`
- `backend/tests/integration/api/test_document_dedup.py`
- `backend/tests/integration/api/test_internal_substitute_hold.py`
- `backend/tests/integration/api/test_approval_atomicity.py`
- `backend/tests/integration/api/test_split_lot_trace.py`
- `frontend/tests/e2e/inspection-happy-path.spec.ts`
- `frontend/tests/e2e/inspection-hold.spec.ts`
- `frontend/tests/e2e/rbac-approval.spec.ts`

**게이트:** 외부 OCR/NAS/Drive가 모두 꺼져도 Slice가 완주하고 AT-002/003/005~010/013의 핵심 계약이 통과해야 P4로 간다.

**2026-08-01 completion-remediation builder evidence (historical ordering superseded):** synthetic calcium-chloride-bead fixture만 사용했다. extraction-run/document→allocation exact lineage가 검사/idempotency effect의 commit 전에 강제되고 실패 시 예약을 포함한 transaction 전체가 rollback된다. 이후 final idempotency race remediation에서 missing-row contention을 실제로 노출하려고 검사 생성의 idempotency reservation을 lineage row lock보다 앞에 두었지만, mismatch는 여전히 committed inspection/idempotency/audit/outbox/snapshot residue 0을 유지한다. unfinalized internal-results 재PUT exact replace/update와 finalized evidence immutability 증빙은 그대로 유효하다.

**2026-08-01 second-remediation builder evidence:** Claude final security review의 B-1/M-1 동일 원인을 닫아 CONFIRMED run의 재확정·재바인딩·field rewrite를 409로 거부하고, document section당 CONFIRMED allocation을 partial unique index로 하나만 허용했다. M-2는 internal-results PUT을 omitted-row 삭제와 empty clear를 포함하는 collection replace로 고정했고, N-3 GET은 non-persisting evaluation을 사용하며, N-4 trap은 자신이 생성한 exact `mktemp` storage tree만 재귀적으로 제거하고 부재를 assert한다. 최종 gate는 backend 346/23 deselected, P2 PostgreSQL 10, P3 PostgreSQL 13, Playwright 3/3을 포함해 모두 통과했다. N-1 validation ordering, N-2 fixture GET seed, N-5 fixture-session eviction은 fixture-only 후속으로 공개하고 남겨두었다. 이는 uncommitted builder evidence이며 Hermes acceptance/integration/push/deploy/release 판정이 아니다.

**2026-08-01 last-blocker remediation builder evidence:** 독립 QA가 기존 N-7 test의 pre-inserted section 때문에 genuine lazy-section first-confirm race가 빠졌음을 재현했다. 교체 regression은 section 0건에서 두 `document_sections` INSERT를 barrier로 동기화하고 5회 parameterize해 매번 200 1건, stable 409 1건, 500 0건, authoritative section/link 각 1건, loser run/field/audit 전체 rollback과 inspection/LOT lineage/idempotency 추가 residue 0을 증명한다. `confirm_review`는 flush/commit을 포괄해 먼저 rollback하고 section/link의 exact constraint 3개만 409로 mapping하며 unrelated integrity error는 re-raise한다. 최종 gate는 backend 346/29 deselected, P2 PostgreSQL 10, P3 PostgreSQL 19, targeted race 15/15, frontend 32, migration 4, full Playwright 3/3을 포함해 통과했다. 기존 authoritative UI/N-6 evidence와 fixture-only N-1/N-2/N-5 상태는 유지된다. 이는 uncommitted builder evidence일 뿐 Hermes acceptance/integration/push/deploy/release 판정이 아니다.

**2026-08-01 final idempotency/upload remediation builder evidence (historical checkpoint):** intake, inspection 생성, approval/finalization의 no-row first reservation을 실제 PostgreSQL `idempotency_keys` INSERT barrier로 동기화했다. `reserve_idempotency`는 nested transaction/savepoint에서 insert하고 `uq_idempotency_principal_scope_key`만 판별한다. loser transaction은 savepoint rollback 뒤 committed competitor hash를 읽어 same payload를 409 pending, different payload를 409 conflict로 반환하며 unrelated constraint는 generic 500으로 재상승하고 business/idempotency residue를 남기지 않는다. 같은 payload는 family별 5회 반복해 intake 201+409, inspection 201+409, approval 200+409를 보장하고, sequential winning-payload replay는 bytes까지 동일하다. Upload stream은 typed empty/over-limit exceptions를 각각 normal 422/413 envelope로 변환하며 exact temp file과 새로 만든 empty storage root를 제거한다. 당시 gate는 backend 346/50 deselected, P2 PostgreSQL 10, P3 PostgreSQL 40, focused 22, frontend 32, migration 4, Playwright 3/3, contract drift/scans/frozen P2 hashes/diff/cleanup을 포함해 green이었다. 당시 pending이던 Hermes gate는 아래 final source-acceptance evidence로 superseded되며 N-1/N-2/N-5는 fixture-only follow-up으로 유지된다.

**2026-08-01 final DB serialization/immutability and source-acceptance evidence:** 모든 supplier/internal/sample evidence I/U/D는 deterministic old/new parent-case lock 뒤 terminality를 검사해 approval과 직렬화한다. Extraction run/field/section/link I/U/D/reparent도 deterministic old/new authoritative-run lock 뒤 `CONFIRMED` 불변성을 검사하며, legitimate first confirm과 failed-confirm rollback을 유지하고 direct app-role cross-LOT rebind를 거부한다. Final independent backend review는 P3 PostgreSQL 67, mutation-first reverse-order probe 6 cycles, terminal-first focused 27, P2 regression 10, substantive gates backend 346/77 deselected·mypy 39·frontend 32·migration 4를 통과해 blocker/major/medium 0이었다. Final independent UI/API review는 real Playwright 3/3, 별도 live-stack desktop 및 375×812 smoke, intake 201+409·inspection 201+409·approval 200+409, byte-identical replay, invalid upload 422/413 residue 0, P3 API 67, repository fingerprint unchanged, cleanup 0/0/0/0으로 `PASS`였다. Hermes controller도 `make bootstrap && make check`, P2 PostgreSQL 10, P3 PostgreSQL 67, real Playwright 3, `test_db_serialization.py` 27 tests × 3 fresh cycles = 81을 독립 재검증했다. Docker HYC containers/networks/volumes는 0/0/0이고 user-owned n8n만 running 상태로 untouched였다. Historical blocker/major는 모두 fixed다.

**Exact-candidate freeze/Git boundary:** base HEAD는 `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf`다. Pre-doc-final freeze는 changed/untracked 50 files, source hash `51f3bbb1d23970484813e893e51fd781f89fb781d02fac2db5cb475b00cac7f2`였고, 이 문서 변경 이후 hash라고 주장하지 않는다. P3는 source accepted이며 exact-candidate commit과 fresh-main fast-forward integration 준비가 됐지만 문서 작성 시점에는 uncommitted/unintegrated/unpushed다. N-1/N-2/N-5와 P2 N-M3는 accepted non-production debt이고 P4/P5는 unstarted다.

### P4 — OCR Golden/Provider benchmark

**선행:** P3 + 품질팀이 승인한 대표 문서 코퍼스/비식별 정책.  
**목표:** Provider를 고르기 전에 채점기와 Human Review 안전망을 만든다.

1. source hash, page/DPI/rotation, header/row/sample raw+normalized expected, page/bbox polygon, low-confidence reason, 허용 normalization을 golden schema로 정의한다.
2. text-layer 탐지 → render → rotate/deskew/contrast → table detect → OCR → parser → schema/logic validation을 단계별 artifact로 기록한다.
3. 두 샘플 PDF와 추가 승인 코퍼스에 동일 runner를 적용한다.
4. exact/normalized match, row recall/precision, numeric/unit/LOT/missing detection, latency/cost/correction time을 분리한다.
5. Provider/prompt/parser/schema version을 기록하고 CI는 `FixtureExtractionProvider`만 사용한다.
6. 외부 전송은 AP-02를 통과한 Provider에만 opt-in한다.

**엣지 fixture:** 소수점, %, O/0, I/l, ±, μ/㎜, 병합셀, 다중 LOT, 도장 겹침, 회전/저해상도, 암호화/손상 PDF, 필수 행 누락, 가변 샘플.

**게이트:** AT-001/004 golden과 KPI 산식이 재현 가능하고 품질팀이 benchmark 표본 대표성을 승인해야 실제 Provider를 고른다. 목표 미달은 자동 확정 확대가 아니라 검토 큐 확대/수동 fallback으로 처리한다.

### P5 — Core MVP 완성

**선행:** P3 필수, OCR 의존 기능은 P4.  
**병렬 lane:** 기준 import, UI/보고서, OCR adapter, NCR을 계약 이후 분리한다.

- 38-sheet 기준 importer: dry-run report → DRAFT only → 관리자 검토/활성화; raw spec/source coordinate/hash 보존
- Local Auth/RBAC, 서비스 계정, 로그인 제한/세션 만료
- package 가변 샘플/정성 결과, alias conflict/unmapped hold
- 반환/재제출, 재검사 회차, 부적합/처리방안/특채/증빙/완료일
- Raw 호환 시트 + `Measurements_Long` + `Documents` + optional `Audit`
- 승인 Snapshot 기반 통합/LOT/공급사 통계 보고서
- 마스터/별칭 import dry-run, feature flag 중앙 관리
- ADMIN/INSPECTOR/LEAD/VIEWER별 API/E2E

**게이트:** AT-001~013 전체와 DoD 기능 항목이 추적표에서 green, 보고서가 mutable live row가 아닌 승인 Snapshot을 읽음.

### P6 — 수집/운영/Pilot

**선행:** P5.  
**목표:** 장애·복구·보안까지 포함해 파일럿 판단 자료를 만든다.

- NAS watcher: size/mtime 안정화, temp/lock 제외, 처리 완료 정책
- Drive cursor polling: quota/backoff, checksum/idempotency, Mirror health
- retry/circuit breaker/DLQ/replay 권한과 운영 대시보드
- 구조화 로그/correlation, metrics/traces, OCR 장애와 API readiness 분리
- malware/MIME/size/page/decompression limits, signed view URL, download audit
- DB+file backup encryption, disposable restore rehearsal, row/hash manifest 검증
- 품질팀 UAT: 유형/공급사/난이도별 정확도·수정시간·hold 원인
- RPO/RTO/보존/운영 책임/production cutover 별도 승인

**게이트:** worker 강제 종료/재처리에도 중복 승인·보고서가 없고 restore rehearsal 성공, 감사 누락 0, 원본/기준 연결 검증 완료.

## 7. 정본 데이터 모델과 불변식

### 7.1 LOT

- `material_lots`: 정본 LOT. 파일럿 identity는 `(supplier_id, material_id, normalized_supplier_lot_no)`이며 `identity_policy_version`과 canonical `identity_key`를 저장한다.
- 원문 LOT는 `supplier_lot_no_raw`로 불변 보존한다. 기본 normalization은 Unicode NFKC+양끝 공백 제거뿐이며 case/내부 구분자는 바꾸지 않는다.
- 생산일·입고일·수량·모델은 기본 key가 아니라 매칭/충돌 증거다. 공급사의 LOT 번호 재사용 근거가 있으면 AP-03에서 versioned policy component로 추가하고 기존 key를 조용히 재계산하지 않는다.
- 필수 component가 없으면 `PROVISIONAL/CONFLICT_REVIEW`; 자동 merge·최종 판정 연결을 금지한다.
- `inbound_receipts`: 입고 이벤트.
- `receipt_lot_allocations`: receipt↔material_lot M:N, 수량/단위/수기값/확정값/확정자.
- `document_sections` ↔ `receipt_lot_allocations`: M:N `document_lot_links`.
- `inspection_cases.receipt_lot_allocation_id`: 한 입고 배분의 검사 건.
- 추적/집계는 `material_lot_id`로 분할 입고를 합친다.
- promotion/merge는 QUALITY Lead+master-data ADMIN 분리 권한, expected version, lock, 사유, link 이관 transaction, `merged_into_id`, append-only audit를 요구한다.

필수 계약 테스트는 1문서-2LOT, 2문서-1LOT, 동일 정본 LOT의 다중 입고, 동시 동일 LOT 생성, provisional conflict/promotion, 감사 가능한 merge, 잘못된 공급사/품목 LOT 충돌이다.

### 7.2 Spec scope

`spec_profiles(material_id NOT NULL, supplier_id NULL, model_id NULL, version, effective_range, status)`로 공통/공급사/모델 범위를 직접 표현한다. `supplier_material_models`는 별칭·parser profile·자체검사 필요 여부 연결에 사용한다. 선택 우선순위와 활성기간 중복 금지는 application lock과 DB constraint로 함께 보장한다.

### 7.3 결과와 정책

- supplier declared decision, supplier-spec recalculated decision, HYC reference decision, internal decision, effective candidate를 별도 컬럼/DTO로 유지한다.
- `source_policy`가 명시되면 그것이 우선한다. 기본은 `BOTH_INTERNAL_PRIORITY`; `BOTH_ALL_MUST_PASS`는 자체 결과만으로 통과시키지 않는다.
- `sample_policy`, `missing_policy`, `unit_formula_version`, `rounding_mode`, `precision`은 spec version에 속한다.
- 불명/custom rule에 `eval`을 사용하지 않는다. allowlisted DSL이 준비되지 않으면 `MANUAL/ON_HOLD`다.

### 7.4 판정과 workflow 분리

`evaluate(spec_snapshot, supplier_results, internal_results, policy_version) -> DecisionCandidate`

순서는 `mapping/confirmation → parse/type → unit dimension/conversion → sample aggregation → supplier/HYC/internal item decision → source policy → missing policy → overall`이다. 전체 후보 우선순위는 `ON_HOLD → REJECTED → ACCEPTED` 조건으로 명시한다. `RETEST/SPECIAL_ACCEPTED`는 역할·사유·승인 guard가 있는 상태 전이다.

### 7.5 승인 Snapshot

Snapshot에는 다음 값을 복사한다.

- source document/section hashes와 final reviewed values
- spec profile/version와 실제 operator/threshold/unit/policy 값
- supplier/internal/effective result와 sample values
- conversion/formula/parser/engine/policy versions
- item별 근거/warning/missing/hold reason
- overall candidate/final workflow decision
- submitter/approver/time/reason/correlation

Canonical JSON serialization과 Snapshot hash로 재현성을 보장한다.

### 7.6 API Idempotency 정본

공통 `idempotency_records`는 principal/scope/key, canonical request hash, state(`PENDING/COMPLETED/FAILED_RETRYABLE`), status/body/resource, lease, created/completed/expires를 저장한다. 동일 key+hash는 최초 응답을 재현하고, 동일 key+다른 hash는 `409 IDEMPOTENCY_KEY_REUSED`다. PENDING worker/API crash recovery도 테스트한다.

|API|Request hash 범위|동일 요청 재시도|보존/Planned test|
|---|---|---|---|
|`POST /documents/upload`|streaming file SHA-256 + canonical metadata|기존 canonical document/job 응답, 새 원본/작업 0|업무 보존기간 이상; `backend/tests/integration/api/test_upload_idempotency.py`|
|`POST /inspection-cases/{id}/approve`|case id + expected version + action + canonical reason/comment|기존 approval/snapshot 응답, approval/audit 1건|approval/audit와 동일 기간, 임의 만료 금지; `test_approval_idempotency.py`|
|`POST /reports/*`|report kind + approved snapshot ids + canonical filters + template version|기존 report job/resource, worker 중복 0|resource 보존기간 이상; `test_report_idempotency.py`|

문서 checksum dedupe는 Idempotency-Key와 독립적으로 항상 적용한다. 상세 계약의 정본은 `docs/TRACEABILITY_MATRIX.md` §4다.

## 8. 한국어 UX와 동시편집

- 작업 큐: 목록 → 입고/LOT → 문서 검토 → 매칭 → 자체검사 → 제출 → 팀장 검토 → LOT 추적.
- 공급사와 HYC 패널은 색상뿐 아니라 제목·접두어·아이콘으로 구분한다.
- PDF.js page coordinate와 bounding box overlay는 unit test를 둔다.
- 숫자는 browser에서도 string 상태로 보관해 float 오염 없이 decimal string으로 전송한다.
- autosave는 DRAFT only, debounce+expected version. 409이면 overwrite하지 않고 비교/새로고침을 안내한다.
- 키보드 이동, 명시적 focus, 색상 외 상태 텍스트, 한국어/영문/±/%/μ/㎜ UTF-8, 1440px 기준과 좁은 화면 Tab을 검증한다.
- 승인/특채/문서 재연결/정정은 사유·confirmation·expected version이 필수다.

## 9. AT-001~013 및 DoD 추적

|AT|Phase|대표 Create 테스트|검증|
|---|---:|---|---|
|AT-001 COA 파싱|P4/P5|`backend/tests/golden/test_calcium_chloride_coa.py`|행/LOT/spec/result/bbox, 도장 저신뢰, 손글씨 참고|
|AT-002 규격 분리|P2/P3|`backend/tests/unit/judgment/test_supplier_vs_hyc_spec.py`|supplier/HYC 컬럼·판정 독립|
|AT-003 누락 대체|P2/P3|`backend/tests/integration/api/test_internal_substitute_hold.py`|자체 미완 hold, 승인 차단|
|AT-004 가변 샘플|P4/P5|`backend/tests/golden/test_domestic_8p_samples.py`|5개/3개 값·원문·순서 무손실|
|AT-005 교차검증|P3|`frontend/tests/e2e/cross-validation.spec.ts`|원문/OCR/수기/final/사유|
|AT-006 단위 변환|P2|`backend/tests/unit/judgment/test_unit_conversion.py`|dimension, 공식 버전, Decimal, 반올림 전 값|
|AT-007 자체 결과 우선|P2/P3|`backend/tests/unit/judgment/test_source_policy.py`|internal effective, supplier 보존|
|AT-008 중복 문서|P3|`backend/tests/integration/api/{test_document_dedup.py,test_upload_idempotency.py}`|canonical 원본 1개, 업무 link 재사용, 동일 key/hash 응답 재현·다른 hash 409|
|AT-009 기준 버전|P2/P3|`backend/tests/integration/db/test_spec_snapshot_immutability.py`|v2 활성 후 과거 v1 결과 불변|
|AT-010 승인|P3|`backend/tests/integration/api/{test_approval_atomicity.py,test_approval_idempotency.py}`|재평가/snapshot/approval/audit 원자성·재시도 중복 0|
|AT-011 부적합|P5|`frontend/tests/e2e/nonconformance.spec.ts`|처리/승인/목표일/증빙/재검사|
|AT-012 Raw Data|P5|`backend/tests/integration/{reports/test_raw_excel_lossless.py,api/test_report_idempotency.py}`|호환+Long, 가변 sample 무손실, 동일 report job 재현|
|AT-013 LOT 조회|P3/P5|`backend/tests/integration/api/{test_split_lot_trace.py,test_production_lot_link_seam.py}`|분할 입고/문서/검사/NCR 전체 연결 + feature OFF 상태의 production link 저장·조회·보고서 seam; ERP 자동 연계는 비범위|

### DoD gate

- Migration/seed 재실행: P1/P2/P5 replay tests
- 38 템플릿/119 항목 Draft import: P0A 관찰, 승인 후 P0B 재검증, P5 승인 import
- 입고/LOT·교차검증·문서 M:N: P2/P3
- PDF 두 유형·Human Review: P4/P5
- HYC 판정·자체검사·가변 샘플: P2~P5
- 검사자→팀장, 5개 workflow 결과, 수정 차단, 감사: P2/P3/P5
- Raw/통합/LOT/통계 4종: P5 Snapshot report tests
- Unit/Integration/Contract/E2E/Golden/OpenAPI: P1부터 누적
- 설치/운영/백업/복구/관리자/품질팀 가이드: P6
- code secret 0: 전 Phase CI

## 10. 목표 검증 명령

아직 프로젝트 코드가 없으므로 아래 명령은 구현 후 목표이며 현재 성공했다고 주장하지 않는다.

```bash
# bootstrap
uv python pin 3.12
uv sync --project backend --all-groups
pnpm --dir frontend install --frozen-lockfile
docker compose up -d postgres redis

# backend
uv run --project backend ruff check backend
uv run --project backend mypy backend/src
uv run --project backend lint-imports
uv run --project backend pytest backend/tests/unit -q
uv run --project backend pytest backend/tests/integration -q
uv run --project backend pytest backend/tests/contract backend/tests/golden -q

# disposable migration replay
uv run --project backend alembic -c backend/alembic.ini upgrade head
uv run --project backend alembic -c backend/alembic.ini downgrade base
uv run --project backend alembic -c backend/alembic.ini upgrade head

# frontend / E2E
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test --run
pnpm --dir frontend build
pnpm --dir frontend exec playwright test

# full / security / restore
./scripts/check.sh
./scripts/secret-scan.sh
./scripts/backup.sh --target /tmp/hyc-backup-test
./scripts/restore-verify.sh /tmp/hyc-backup-test
git diff --check
```

CI/golden에서는 실제 OCR 외부 호출을 금지한다. 기대 결과는 exit 0, migration replay 후 동등 schema, 승인/hold/dedupe/split-lot E2E 통과, restore row/hash manifest 일치다. 테스트 개수·성능·OCR 정확도는 실제 실행 전 기재하지 않는다.

## 11. 보안·관측성·복구·롤백

### 보안

- quarantine → MIME magic/extension/size/page/encryption/corruption/decompression/malware 검사 → immutable 승격
- path sanitization, 파일 실행 금지, signed URL 단기 만료, download audit
- Argon2id, 세션 만료/실패 제한, 역할/permission 최소 권한
- ADMIN과 LEAD 분리, 비상 permission은 사유/감사/만료 필수
- 외부 AI 전송 기본 OFF, training/retention/region 검토
- secret은 환경변수/Secret Store, 로그·오류·fixture에 금지

### 관측성

- correlation/causation/idempotency ID를 HTTP→Outbox→worker→Provider에 전파
- document state count/age, queue/DLQ, provider latency/cost/error, low-confidence/correction time, dedupe, match ambiguity, approval dwell, replication/backup failure metrics
- 구조화 log에 원문·전체 OCR raw·secret을 넣지 않음
- OCR/Storage 장애를 API 전체 readiness와 분리하고 수동 경로를 유지

### 백업/복구/롤백

- DB와 파일 hash manifest를 함께 백업하고 암호화/접근권한 기록
- disposable environment restore rehearsal을 생산 gate로 사용
- destructive migration은 add → backfill → dual-read/write 검증 → switch → 후속 제거
- 기능은 feature flag로 비활성 가능하되 데이터 불변성 guard는 비활성할 수 없음
- 승인 Snapshot은 rollback 시에도 보존하며 corrective forward migration을 우선

## 12. MVP 비범위와 후속 seam

**비범위:** ERP/MES/WMS 실시간 연계, AQL 자동 계산, 검사장비 연동, 손글씨 핵심 필드 자동 확정, 자동 메시지/메일, 완제품·출하 LOT 자동 연결, CAPA 전체, 공급사 포털, 공인전자서명, AI 최종 판정, Kubernetes/마이크로서비스.

**Seam:** `ErpPort`, BOM/production links, `AuthPort` SSO, Storage/Extraction/Report Adapter, outbox domain events. Future field/table을 만들더라도 MVP UI/API와 worker는 feature flag OFF에서 호출하지 않는다.

## 13. 실행 오케스트레이션 — 승인 후

1. Hermes가 AP-0와 추적표를 유지하고 독립 QA를 담당한다.
2. Orca 관리 worktree에서 Codex CLI가 기본 구현자다. main/shared CWD는 건드리지 않는다.
3. Claude Code Opus 5는 DB 불변식·보안·고위험 review 또는 막힌 분석에 읽기 전용 specialist로 사용한다.
4. 한 worktree에 여러 mutating agent를 두지 않는다.
5. 구현 agent는 add/commit/push/merge/deploy 권한이 없다. 검증 evidence를 Hermes가 재실행한다.
6. 각 Phase는 tests-first → 최소 구현 → diff review → 실제 명령 → 문서/traceability/Kanban 동기화 순서다.
7. P3 수직 Slice 검증 전 P4/P5의 넓은 UI·Provider 구현을 시작하지 않는다.
8. Phase 완료는 사용자 승인과 분리한다. 특히 실데이터 import, 외부 OCR, production deployment는 별도 승인이다.

## 14. 최종 승인 체크리스트

- [x] AP-01 배포/데이터 위치 승인
- [x] AP-02 외부 OCR 기본 OFF 및 향후 검토 절차 승인
- [x] AP-03 canonical LOT+allocation 모델 승인
- [x] AP-04 Local Auth/RBAC/ADMIN 비승인권 승인
- [x] AP-05 실제 PDF/XLSX Git 커밋 금지·마스킹 fixture 정책 승인
- [x] P0A/P0B/P1 구현 착수 승인(기존 권한)
- [x] P0A/P0B complete·accepted 및 P1 진행 권한 확인
- [x] P2는 P1 contract gate 후 진행 권한 확인
- [x] P2 source gate: independent Hermes QA + final Claude `PASS` 후 complete·accepted
- [x] P2 source commit `996056b`의 fresh-main clean integration branch fast-forward 통합 및 fresh QA
- [x] P3 isolated-worktree 구현 권한 확인
- [x] P3 completion-remediation builder gate: cross-allocation lineage, repeated internal-result PUT, finalized-evidence I/U/D; local/contract/frontend, disposable PostgreSQL P2/P3 distinct-app-role controls, 3-scenario Compose E2E, diff/cleanup 검증
- [x] P3 second-remediation builder gate: confirmed-run terminality/single allocation, internal-results collection replace/clear, mutation-free GET, exact temp-tree cleanup; N-1/N-2/N-5 fixture-only residual disclosure
- [x] P3 final-polish builder gate: authoritative visible/live server status, concurrent unique-index loser stable 409/full rollback, structured replace/clear audit metadata, LEAD_REVIEW evidence-change eligibility rollback, desktop/375×812 UI regression
- [x] P3 last-blocker builder gate: true empty-section first-confirm race repeated 5× per run, exact section/link uniqueness allowlist mapping after rollback, full loser/no-residue assertions, dead rolled-back conflict assignment removed
- [x] P3 final idempotency/upload builder gate: intake/inspection/approval no-row first-reservation savepoint races, same/different payload 409 contracts, byte-stable replay, typed empty 422/over-limit 413 with exact residue cleanup
- [x] P3 final DB serialization/immutability builder gate: deterministic old/new parent locks for every evidence and extraction-lineage I/U/D/reparent operation; repeated approval/confirmation races, confirmed direct app-role mutation/cross-LOT rebind denial, pending→confirmed preservation, failed-confirm rollback, migration runtime-object roundtrip
- [x] P3 independent backend/UI/API review and Hermes controller QA source gate
- [ ] P3 exact-candidate commit and fresh-main fast-forward integration gate

**현재 상태 (2026-08-01 P3 final source acceptance):** `P0A_P0B_P1_P2_P3_SOURCE_COMPLETE_ACCEPTED_P3_GIT_INTEGRATION_PENDING`. P2는 complete/accepted/committed/fresh-main integrated/원격 delivered 상태를 유지한다. P3는 모든 historical blocker/major가 fixed되고 independent backend/UI/API review와 Hermes controller QA를 통과했다. Final counts는 backend 346/77 PostgreSQL deselected, mypy 39, frontend 32, migration 4, P2 PostgreSQL 10, P3 PostgreSQL 67, real Playwright 3/3, focused serialization 27×3=81이다. Alembic head는 `20260801_0004`이고 frozen P2 migrations는 byte-identical이다. N-1/N-2/N-5와 N-M3는 accepted non-production debt다. P3는 source accepted이나 문서 작성 시점 uncommitted/unintegrated/unpushed이며, separately authorized exact-candidate commit과 fresh-main fast-forward integration만 다음 안전 단계다. P4/P5는 unstarted다. 실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP, 비일회성/production DB, production DB-role activation, public exposure, deployment/release는 여전히 미승인이다.
