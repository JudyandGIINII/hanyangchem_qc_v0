# 한양화학 수입검사 디지털화 및 LOT 추적 시스템 — Claude Code Opus 5 독립 구현 계획

> **Provenance:** Claude Code CLI를 `--model opus --effort medium --permission-mode plan --tools Read`로 읽기 전용 호출했다. CLI JSON 증빙의 canonical model은 `claude-opus-5`이다. Claude는 `Prd.md`만 읽었으며 Hermes 독립 계획은 입력·열람하지 않았다.

---

# 한양화학 수입검사 디지털화 시스템 — 독립 구현 계획 (v0)

## Context

현 저장소에는 소스가 없고 Git main은 첫 커밋 전이다. 확보된 실물은 PRD(`Prd.md`), 기준 Excel(PRD 기준 38 템플릿 / 119 검사항목 행), 헤더만 있는 Raw Data Excel, 이미지 기반 샘플 PDF 2건이다. 즉 **판정 규칙의 원천(기준 Excel)은 있으나, OCR 성능을 좌우할 실문서 코퍼스와 이관용 실데이터는 없다.** 따라서 계획의 축은 "OCR을 먼저 잘 만든다"가 아니라 **정본 DB·상태머신·결정론적 판정 엔진을 먼저 세우고, OCR은 후보 생성기로 뒤에 붙인다**이다. PRD §27-28, §17.1, §19.1과 같은 방향이다.

---

## 1. 핵심 위험 · PRD 내부 모순 · 구현 전 결정

### 1.1 핵심 위험

| # | 위험 | 영향 | 완화 |
|---|---|---|---|
| R1 | OCR 후보가 사실상 최종값으로 굳어짐(검토 피로 → 무조건 채택) | 오판정, PRD §0-3 위반 | 판정 엔진 입력에서 `mapping_status != MANUAL_CONFIRMED` / `review_status != CONFIRMED` 필드를 **구조적으로 배제**. 채택 시 `final_source`+사유 필수 |
| R2 | LOT-입고 cardinality 미확정 상태의 1:1 하드코딩 | 후속 재설계 | 문서↔LOT은 Join Table만, 코드에 단건 가정 금지. 계약 테스트로 M:N 강제 |
| R3 | 기준 개정 후 과거 건 판정이 바뀜 | 품질 기록 신뢰 붕괴 | `spec_version_id` 고정 + **규격 값 자체를 판정 snapshot에 복사**(FK만으로는 부족) |
| R4 | 승인 완료 데이터의 사후 수정 | 감사 부적합 | 앱 가드 + DB 트리거 이중화, 정정은 `revision_of` 신규 행 |
| R5 | 부동소수점 사용 | 경계값 오판정(0.15 상한 등) | 전 구간 `Decimal`, DB `NUMERIC`, JSON은 문자열 직렬화 |
| R6 | OCR Provider 장애가 업무 전체를 막음 | 가용성(§19.3) | 수동 입고/자체검사 경로는 OCR 의존성 0. 워커가 죽어도 수직 슬라이스 완주 |
| R7 | 외부 LLM 전송에 대한 사내 정책 미확정 | 컴플라이언스 | Provider별 `allow_external`/보존 설정, 기본 **비활성**. 로컬 Provider 어댑터 자리 확보 |
| R8 | 38개 seed의 규격 문자열이 자유 텍스트(`91.80 ± 0.50`, `2 - 5mm`, `98*68mm`, `65μ*280mm*1,000M`) | 판정 불가/오해석 | seed는 **DRAFT + `raw_spec_text` 보존**, 구조화는 승인 시점 1회(§27-31). 파싱 실패는 `VISUAL_MANUAL`/`MANUAL`로 안전 낙하 |
| R9 | 실 Raw Data 행이 없어 출력 호환성 검증 불가 | AT-012 리스크 | 헤더 기반 계약 테스트 + 자체 fixture 라운드트립, 실데이터 확보 시 재검증 |

### 1.2 PRD 내부 모순 / 모호

| 코드 | 내용 | 판단 |
|---|---|---|
| C1 | §14.2 `spec_profiles.supplier_material_model_id`(단일 FK) vs FR-SPEC-001의 "supplier/model NULL = 공통 허용" | **모순.** SMM은 supplier NOT NULL이라 공통 프로파일 표현 불가 → `spec_profiles`가 `material_id NOT NULL`, `supplier_id NULL`, `model_id NULL`을 직접 보유. SMM은 파서 프로파일·별칭·자체검사 필요 여부 용도로 분리 |
| C2 | "자체 결과 우선"(§8, FR-JDG-003) vs `BOTH_ALL_MUST_PASS`(FR-SPEC-005) | **충돌.** `source_policy` 명시 시 명시 정책 우선, 미지정 기본은 `BOTH_INTERNAL_PRIORITY`. `BOTH_ALL_MUST_PASS`는 자체 우선 규칙 비적용(문서화) |
| C3 | FR-JDG-004가 `RETEST`/`SPECIAL_ACCEPTED`를 엔진 출력에 포함 | **역할 혼선.** 재검사·특채는 사람 액션 → **엔진 출력은 `ACCEPTED`/`REJECTED`/`ON_HOLD` 3종**, 나머지는 상태머신 전이로만 도달 |
| C4 | §8-20과 FR-JDG-004의 우선순위 서술 중복·순서 불명확 | 고정: `ON_HOLD`(필수 누락/미매핑/자체검사 미완/미확인 저신뢰) → `REJECTED`(최종 유효 항목 1개 이상 FAIL) → `ACCEPTED` |
| C5 | `sample_measurements`의 "internal_result_id 또는 supplier_result_id" | nullable 2 FK + `CHECK (num_nonnulls(a,b)=1)` |
| C6 | `inspection_round`(재검사)와 `revision_of`(정정본) 의미 중복 | 독립 2축으로 분리 |
| C7 | §4.1은 첨가제 포함, §5.3은 첨가제 템플릿 미확인 | seed 0건으로 진행, 분류 enum·등록 경로만 확보 |
| C8 | AQL이 화면·기준서엔 있으나 계산은 MVP 제외 | 문자열 보존 필드만, 계산 코드 금지 |
| C9 | 문서 상태 `MATCHED` vs 검사 상태 `MATCH_REVIEW` 중복 | 문서=파이프라인, 검사=업무 진행. 링크 이벤트로 동기화하되 상호 파생 금지 |
| C10 | §8 항목 번호가 9~23으로 어긋나고 중간에 13부터 재시작(§0, §9 헤딩 번호도 동일 현상) | 문서 편집 오류로 판단, 내용 해석엔 영향 없음. 인용은 조항 번호가 아닌 문구 기준으로 |
| C11 | KPI 95%/98%가 개발 게이트인지 파일럿 목표인지 | 파일럿 인수 목표. **Stage 2 벤치마크에서만** 사용, Stage 1 통과 조건 아님 |

### 1.3 구현 전 결정

**A. 즉시 결정 (착수 전 확정)**
1. 스택: FastAPI + PostgreSQL + Alembic + Celery/Redis + Next.js(TS) + Pytest/Playwright (§17.1 채택).
2. 판정 엔진은 **순수 함수 패키지**, DB/HTTP/OCR 의존 0.
3. 수치 전부 `Decimal` / DB `NUMERIC` / API는 문자열.
4. 시간은 DB UTC(`timestamptz`), 표시 Asia/Seoul, 도메인 경계에 `ClockPort`.
5. 식별자는 예측 불가 UUID(v7 권장), 표시 번호(`inbound_no`, `ncr_no`)는 별도 시퀀스.
6. Soft Delete, 감사로그 append-only.
7. C1·C2·C3·C4·C5·C6 해소안 확정.
8. 승인 완료 불변성 이중화(앱 가드 + DB 트리거).

**B. 설정으로 격리 (상수 금지, §27-47)**
신뢰도 임계값(필드 유형별), 파일 안정화 대기시간, 업로드 크기 상한, 보존기간, Primary/Mirror 저장소, Provider·프롬프트/스키마 버전, 외부 전송 허용 여부, 필수 입력 필드 목록, 기본 누락 정책(기본 `HOLD`), 기본 샘플 정책(기본 `MANUAL`), 입고일 허용 오차, 편차 경고 임계, Feature Flag(BOM/NCR 세부/자동수집/통계).

**C. 파일럿 이후 확정**
OCR Provider 최종 선정과 KPI 기준선, 항목별 샘플 정책, 단위 목록·반올림 모드, 통합보고서 최종 디자인, RPO/RTO, ERP 연계 방식, BOM 구조, 실 Raw Data 이관 규칙.

---

## 2. 권장 아키텍처

### 2.1 구조 (모듈러 모놀리스 + 워커)

```
[Next.js Web]──HTTP──▶[FastAPI API]──▶[PostgreSQL]
                          │  │
                          │  └──▶[Outbox 테이블]──▶[Relay]──▶[Redis/Celery]
                          │                                      │
                          ├──▶ StoragePort ──▶ NAS / GDrive      ├─▶ Ingestion Worker
                          ├──▶ JudgmentEngine (순수, 인프로세스)  ├─▶ OCR Worker ──▶ OcrPort ──▶ Provider
                          └──▶ ERPPort (Future, no-op)           └─▶ Report Worker
```

레이어(단방향): `domain`(엔티티·값객체·상태머신·판정, 외부 의존 0) ← `application`(UseCase·UnitOfWork·Port) ← `adapters`(inbound: FastAPI / outbound: SQLAlchemy·storage·ocr·drive) ← `infrastructure`(DI·설정·마이그레이션·워커 부팅).

### 2.2 Port / Adapter

| Port | 메서드 | MVP 구현 | 대체 |
|---|---|---|---|
| `StoragePort` | `put/get/exists/checksum/copy/signed_view_url/health_check` | `LocalFsStorage`, `SmbNasStorage` | `GoogleDriveStorage`, 향후 S3 |
| `DocumentSourcePort` | `list_new/fetch/mark_processed` | `ManualUploadSource` | `NasWatcherSource`, `GoogleDriveSource` |
| `OcrPort` | `extract(document_ref, schema_version) -> RawExtraction` | `FixtureOcrProvider`(golden 재생) | Provider N종 |
| `ParserPort` | `parse(raw, profile) -> ExtractionCandidate` | 규칙 기반 | LLM 구조화 |
| `EventPublisherPort` | `publish(event)` | Outbox 기록 | 향후 알림 |
| `ClockPort` / `IdPort` | 결정론적 테스트 | 실제 구현 | 고정 시계 |
| `ReportRendererPort` | `render(kind, snapshot) -> bytes` | openpyxl | 템플릿 교체 |
| `ERPPort` | 부록 D contract | no-op stub | 후속 |

어댑터는 도메인 타입만 주고받고, Provider 원문은 `raw_output_ref`로 저장소에 두고 DB엔 참조만 둔다.

### 2.3 동기 / 비동기 경계

- **동기:** 입고/LOT 등록·확정, 매칭 확정, 자체검사 입력, **판정 실행**, 제출/반려/승인, LOT 조회. 판정은 순수·저비용이며 "승인 직전 최신 판정 보장"이 더 중요하므로 큐에 넣지 않는다.
- **비동기(Job ID):** 문서 수집·해시·전처리·OCR·파싱, 대용량 보고서, 마스터/기준 Import(Dry-run·적용), 미러 복제.
- 업로드는 저장+해시까지 동기(접수 응답 3초 목표), 이후는 Outbox 이벤트.

### 2.4 트랜잭션 / Outbox

- UseCase 1개 = 트랜잭션 1개. 그 안에서 **업무 변경 + `audit_logs` + `outbox_events`를 함께 커밋**. 외부 호출은 트랜잭션 밖.
- Relay가 `outbox_events`를 폴링해 발행(at-least-once), 컨슈머는 `event_id` 기반 멱등.
- 재시도 초과분은 DLQ 테이블 + 대시보드 노출(§19.3).

### 2.5 RBAC · 감사 · 불변성

- 역할 `INSPECTOR / LEAD / ADMIN / VIEWER / SERVICE`, `(role, permission)` 매핑 + 라우터 데코레이터. **ADMIN은 승인 권한 없음**(권한 분리). 비상 권한은 별도 permission + 사유 필수 + 감사 강제.
- 감사: `audit_logs(entity_type, entity_id, action, actor_id/service_id, before_json, after_json, reason, correlation_id, created_at)`. 앱 기록이 정본, 핵심 테이블엔 누락 방지 트리거를 보조로.
- 불변성: `documents` 경로·해시 UPDATE 금지 / `spec_versions` ACTIVE 후 변경 금지·사용 중 삭제 금지(FK RESTRICT + 트리거) / `inspection_cases` 최종 상태 후 업무 필드 UPDATE 금지 / `inspection_report_snapshots` append-only / `audit_logs` UPDATE·DELETE 금지.

---

## 3. 신규 디렉터리 · 파일 구조 (전부 `Create:`)

> 아래는 모두 **아직 존재하지 않는 신규 생성 대상**이다.

```
Create: docker-compose.yml
Create: Makefile
Create: .env.example
Create: README.md
Create: backend/pyproject.toml
Create: backend/alembic.ini
Create: backend/src/hyc/__init__.py

# ── domain (순수)
Create: backend/src/hyc/domain/common/decimal_ops.py
Create: backend/src/hyc/domain/common/errors.py
Create: backend/src/hyc/domain/spec/spec_expression.py          # operator/데이터유형 값객체
Create: backend/src/hyc/domain/spec/spec_text_parser.py         # 기준 원문 → 구조화(승인 시 1회)
Create: backend/src/hyc/domain/units/unit_registry.py
Create: backend/src/hyc/domain/units/conversion.py
Create: backend/src/hyc/domain/judgment/item_evaluator.py
Create: backend/src/hyc/domain/judgment/sample_policy.py
Create: backend/src/hyc/domain/judgment/source_policy.py
Create: backend/src/hyc/domain/judgment/missing_policy.py
Create: backend/src/hyc/domain/judgment/overall_decision.py
Create: backend/src/hyc/domain/judgment/snapshot.py             # 판정 근거 JSON(부록 C)
Create: backend/src/hyc/domain/judgment/engine.py
Create: backend/src/hyc/domain/workflow/case_state_machine.py
Create: backend/src/hyc/domain/workflow/document_state_machine.py
Create: backend/src/hyc/domain/matching/match_rules.py

# ── application
Create: backend/src/hyc/application/ports/{storage.py,ocr.py,parser.py,document_source.py,events.py,clock.py,ids.py,report.py,erp.py}
Create: backend/src/hyc/application/uow.py
Create: backend/src/hyc/application/usecases/inbound/{create_receipt.py,add_lot.py,confirm_receipt.py}
Create: backend/src/hyc/application/usecases/documents/{upload_document.py,dedupe_document.py,confirm_extraction.py,match_section.py,unlink_section.py}
Create: backend/src/hyc/application/usecases/inspection/{create_case.py,put_supplier_results.py,put_internal_results.py,evaluate_case.py,submit_case.py,approve_case.py,return_case.py,retest.py,special_accept.py}
Create: backend/src/hyc/application/usecases/spec/{import_spec_excel.py,activate_spec_version.py,resolve_spec_version.py}
Create: backend/src/hyc/application/usecases/reports/{raw_data.py,integrated.py,lot_trace.py,supplier_quality.py}
Create: backend/src/hyc/application/usecases/masterdata/{import_codes.py,import_aliases.py}

# ── adapters
Create: backend/src/hyc/adapters/db/{base.py,session.py,models/*.py,repositories/*.py}
Create: backend/src/hyc/adapters/storage/{local_fs.py,nas_smb.py,google_drive.py}
Create: backend/src/hyc/adapters/ocr/{fixture_provider.py,provider_a.py,provider_b.py,registry.py}
Create: backend/src/hyc/adapters/parser/{rule_based.py,llm_structurer.py,schema.py}    # Pydantic 강제 검증
Create: backend/src/hyc/adapters/http/routers/{auth.py,inbound.py,documents.py,inspection.py,spec.py,masterdata.py,reports.py,admin.py,health.py}
Create: backend/src/hyc/adapters/http/{deps.py,rbac.py,errors.py,idempotency.py,pagination.py}
Create: backend/src/hyc/workers/{celery_app.py,outbox_relay.py,ingestion.py,ocr_pipeline.py,reports.py,mirror.py}
Create: backend/src/hyc/infrastructure/{settings.py,container.py,logging.py,metrics.py,feature_flags.py}
Create: backend/migrations/versions/            # Alembic revision 파일들
Create: backend/seeds/{spec_excel_import.py,standard_test_items.py,units.py,users_dev.py}

# ── tests
Create: backend/tests/unit/domain/{test_spec_expression.py,test_units.py,test_decimal_boundary.py,test_sample_policy.py,test_missing_policy.py,test_source_policy.py,test_overall_decision.py,test_case_state_machine.py}
Create: backend/tests/integration/{test_inbound_flow.py,test_document_dedupe.py,test_match_many_to_many.py,test_spec_version_freeze.py,test_approval_immutability.py,test_idempotency.py,test_rbac.py,test_outbox.py,test_ncr_flow.py,test_report_raw_data.py,test_lot_trace.py}
Create: backend/tests/contract/test_openapi_contract.py
Create: backend/tests/ocr_golden/{conftest.py,test_golden_regression.py,runner.py,metrics.py}
Create: backend/tests/fixtures/{documents/,golden/,expected_reports/}
Create: backend/tests/factories/*.py

# ── frontend
Create: frontend/package.json
Create: frontend/app/(dashboard)/inspections/page.tsx              # 메인 목록
Create: frontend/app/(dashboard)/inspections/[id]/page.tsx         # 좌우 2분할 상세
Create: frontend/app/(dashboard)/documents/review/[id]/page.tsx    # OCR 검토
Create: frontend/app/(dashboard)/specs/page.tsx
Create: frontend/app/(dashboard)/stats/page.tsx
Create: frontend/app/(dashboard)/lots/page.tsx
Create: frontend/components/{SupplierPanel.tsx,InternalPanel.tsx,PdfViewer.tsx,BoundingBoxOverlay.tsx,SampleGrid.tsx,DecisionBadge.tsx,CrossCheckField.tsx,WarningList.tsx}
Create: frontend/lib/{api.ts,decimal.ts,i18n.ko.ts,statusLabels.ts}
Create: frontend/e2e/{happy_path.spec.ts,rbac.spec.ts,report.spec.ts,lot_search.spec.ts}

# ── ops / docs
Create: ops/{backup.sh,restore.sh,rollback.md}
Create: docs/{install.md,operations.md,admin_guide.md,user_guide_ko.md,backup_restore.md,ocr_benchmark.md,decision_log.md}
```

---

## 4. 단계별 계획

### Stage 0 — Domain / DB Foundation
- **목표:** 정본 스키마·상태머신·순수 판정 엔진·단위/규격 값객체 확립. 화면 없음, 임시 데이터 없음(§27-28).
- **선행:** §1.3-A 결정 확정, compose로 Postgres 기동.
- **주요 파일:** `domain/**`, `adapters/db/models/**`, `migrations/versions/0001_init.py`, `seeds/{units,standard_test_items}.py`.
- **테스트:** 판정 단위 테스트 전량(경계값 포함), 상태머신 전이표 테스트, migration up/down, 불변성 트리거 테스트.
- **완료 게이트:** `upgrade head → downgrade base → 재실행` 무결. 판정 엔진의 인프라 import 0(import-linter 강제). 단위 테스트 전량 통과.
- **중단 신호:** 스키마가 1:1 가정을 요구 → C1/R2 즉시 재검토.

### Stage 1 — 얇은 수직 슬라이스
- **목표:** OCR 없이 **입고 → 검사 → 판정 → 제출 → 승인 → 불변 snapshot → LOT 조회**가 UI로 끝까지 동작(상세 §5).
- **선행:** Stage 0 게이트.
- **게이트:** `e2e/happy_path.spec.ts` 통과 + AT-005/007/009/010/013의 슬라이스 범위 통과 + 승인 후 수정 차단 실증.

### Stage 2 — OCR Golden & Provider Benchmark
- **목표:** Provider를 고르기 전에 **채점기를 먼저 만든다**(§20).
- **선행:** Stage 1 통과, **실문서 코퍼스 확보**(현재 2건뿐 → 이것이 선행조건이자 최대 리스크).
- **주요 파일:** `tests/ocr_golden/**`, `adapters/ocr/{fixture_provider,registry}.py`, `adapters/parser/schema.py`, `docs/ocr_benchmark.md`.
- **테스트:** golden 회귀, Pydantic 스키마 위반 케이스, §20.2 엣지 20종 체크리스트.
- **승인 게이트:** 최소 2 Provider의 동일 데이터셋 비교표 + 외부 전송 정책 승인. KPI는 여기서만 판단하고, 미달 시 "자동확정 축소·검토 큐 확대"로 대응하며 파이프라인을 막지 않는다.
- **중단 신호:** 코퍼스 10건 미만 → 결론 유보하고 Stage 3의 OCR 비의존 항목만 진행.

### Stage 3 — 전체 MVP
- 문서 수집(NAS/Drive/업로드), 전처리·OCR·파싱·신뢰도·논리검증, 매칭 후보·교차검증, 별칭 매핑, 단위 환산, 자체검사 전 기능, NCR/재검사/특채, 4종 보고서, 통계, 마스터 Import, Feature Flag, RBAC 전량.
- **게이트:** AT-001~AT-013 전부 자동화 통과 + DoD 전항목 + OpenAPI 생성 + secret 스캔 clean.

### Stage 4 — 운영 / Pilot
- 백업·복원 리허설, 모니터링·상태 화면, DLQ 운영, 교육, UAT(오류를 문서유형·항목·Provider·원인·수정시간으로 기록), KPI 기준선 측정.
- **승인 게이트:** 복원 리허설 성공 + 파일럿 기간 감사로그 누락 0건 + 롤백 절차 실증.

---

## 5. 첫 수직 슬라이스 상세 (Stage 1)

시나리오: **염화칼슘_비드 1 LOT**을 수동으로 끝까지 통과.

1. **수동 입고/LOT 등록** — `POST /inbound-receipts` → `POST /{id}/lots`, 필수 필드는 설정 기반, 상태 `DRAFT`.
2. **hash 중복** — `POST /documents/upload`에서 SHA-256 계산, 동일 해시면 새 원본 레코드 생성 없이 `DUPLICATE` 표시 + 기존 문서 재사용 선택지 반환(AT-008).
3. **fixture 추출 후보** — 실 OCR 없이 `FixtureOcrProvider`가 golden JSON을 반환해 `document_extractions`/`extracted_fields` 생성, 상태 `REVIEW_REQUIRED`로 **후보임을 명시**.
4. **사람 확인** — OCR LOT No.와 수기 LOT No. 불일치를 원문 위치와 함께 비교. 최종값+사유 선택 전 확정 불가(AT-005), 확정 시 `MANUAL_CONFIRMED`/`final_source` 기록, 원 OCR값 보존.
5. **매칭 확정** — `document_lot_links` 생성. 후보 1건이어도 잠정 표시 후 검사자 확정.
6. **기준 고정** — 검사일 기준 유효 `spec_version`을 구체성 4단계 우선순위로 해석 → `spec_version_id` + **규격 값 snapshot** 고정(AT-009).
7. **Decimal 판정** — `POST /inspection-cases/{id}/evaluate`. `% 염화칼슘 최소 74%`(GTE), `밀도 0.95–1.0 g/ml`(BETWEEN), `Water Insoluble 최대 0.15%`(LTE). 공급사 판정과 HYC 판정을 **별도 컬럼**으로 산출(AT-002).
8. **자체검사 보류** — `성상`/`탁도` 같은 `[매 Lot]` 자체검사 항목 미입력이면 후보 `ON_HOLD` + 상태 `INTERNAL_TEST_PENDING`, 입력 후 재평가(AT-003, AT-007).
9. **제출/승인** — 제출 검증(필수값·미확인 저신뢰·경고 처리) → `LEAD_REVIEW` → 팀장 승인. 검사자 승인 시도는 403.
10. **immutable snapshot / audit** — 승인 트랜잭션에서 `inspection_report_snapshots` 생성(판정 근거 JSON + 문서 해시 + 기준 버전 + 승인자/일시), 이후 업무 필드 UPDATE 차단. 전 단계 `audit_logs` 적재.
11. **LOT 조회** — LOT No. 검색 → 입고 건들·문서·검사 결과·상태를 한 화면(AT-013 MVP 범위).

이 슬라이스는 **OCR Provider·NAS·Drive·Excel 보고서 없이** 완주 가능해야 하며, 그것이 R6에 대한 구조적 증거다.

---

## 6. 세부 규칙

### 6.1 DB 불변식
- `UNIQUE(documents.checksum_sha256)` + 인덱스. `UNIQUE(supplier_code) WHERE NOT NULL`(materials/models 동일).
- 동일 구체성 레벨 `spec_profiles`의 ACTIVE 유효기간 겹침 금지 → `EXCLUDE USING gist (profile_key WITH =, daterange(effective_from, effective_to) WITH &&) WHERE status='ACTIVE'`.
- `spec_items`: operator별 필수 컬럼 CHECK(`TARGET_PLUS_MINUS`→target/tolerance NOT NULL, `BETWEEN_*`→lower<upper).
- `sample_measurements` XOR FK CHECK(C5), `internal_results.spec_item_id NOT NULL`.
- 최종 판정이 있는 `inspection_cases`는 대응 `approvals` 필수(트리거).
- `document_lot_links`: `UNIQUE(document_section_id, receipt_lot_id) WHERE active`.
- Soft delete `deleted_at` + 부분 인덱스, `audit_logs`/snapshots 물리 삭제 금지.

### 6.2 LOT cardinality
- `inbound_receipts 1:N receipt_lots`, `document_sections M:N receipt_lots`(Join `document_lot_links`), `receipt_lots 1:N inspection_cases`(회차·정정본).
- 같은 `supplier_lot_no`가 여러 입고 건에 존재 가능 → LOT 조회는 `(supplier_id, material_id, supplier_lot_no)` 그룹 집계.
- 계약 테스트 필수 3케이스: 1문서-2LOT, 2문서-1LOT, 동일 LOT 분할 입고.

### 6.3 상태 머신
- 전이표를 `case_state_machine.py` 한 곳에 상수로 두고 **서버에서만 검증**, 위반은 `409`.
- 대표: `DRAFT→DOCUMENT_PENDING→MATCH_REVIEW→SUPPLIER_REVIEW→(INTERNAL_TEST_PENDING)→READY_FOR_REVIEW→LEAD_REVIEW→{ACCEPTED|REJECTED|ON_HOLD|RETEST|SPECIAL_ACCEPTED|RETURNED}`, `RETURNED→MATCH_REVIEW/SUPPLIER_REVIEW`, 최종→`CLOSED`, 오생성은 `CANCELLED`.
- 각 전이는 `(from, to, required_role, guard_fn, audit_reason_required)`로 선언 → 테스트가 표를 그대로 순회.

### 6.4 Idempotency / Optimistic locking
- `Idempotency-Key` → `idempotency_keys(key, endpoint, request_hash, response_json, status, created_at)`. 동일 key+hash면 저장 응답 반환, 다른 hash면 `409`. 대상: 업로드·제출·승인·보고서 생성·Import 적용.
- 문서 멱등성의 실질 키는 SHA-256(AT-008).
- 모든 업무 엔티티에 `version int`, 전이/PATCH는 `If-Match` 필요, 불일치 시 `409` + 한국어 안내("다른 사용자가 먼저 수정했습니다").
- 워커 컨슈머는 `event_id` 처리 기록으로 중복 실행 무해화.

### 6.5 OCR Golden 스키마

`tests/fixtures/golden/<doc_id>.json`:

```json
{
  "doc_id": "coa_cacl2_2025_04_23",
  "source_file": "documents/coa_cacl2.pdf",
  "document_type": "COA",
  "language": ["en"],
  "traits": ["image_scan", "stamp_overlap", "handwriting"],
  "header": { "supplier_name": {"value": "...", "page": 1, "bbox": [0,0,0,0], "required": true} },
  "results": [
    { "supplier_item_name": "CACL2", "supplier_spec_raw": "74.0% MIN",
      "supplier_result_raw": "75.56%", "numeric_value": "75.56", "source_unit": "%",
      "page": 1, "bbox": [0,0,0,0], "samples": [] }
  ],
  "expected_low_confidence": ["fe_percent"],
  "handwriting_notes": ["참고 메모로만 취급"]
}
```

- 채점기(`metrics.py`) 산출: 분류 정확도, 헤더 exact match, 수치 exact match, 단위 정확도, 표 행 recall/precision, LOT 정확도, 필수 항목 누락 탐지율, 처리시간, 문서당 비용, 사람 수정시간(수기 입력).
- 수치 비교는 정규화 후 **Decimal 동등성**(0.150 == 0.15 동등, `015`는 오답).
- Provider/prompt/schema 버전 변경 시 회귀 실행을 CI에서 강제.

### 6.6 결정론적 판정 엔진
- 개념 시그니처: `evaluate(spec_snapshot, supplier_results, internal_results, config) -> JudgmentResult`.
- 입력은 값객체, 출력은 항목별 결정 + 경고 + `candidate_overall_decision` + 근거 snapshot(부록 C 형태, 값은 문자열 Decimal).
- 순서: 기준 snapshot → 매핑 확인(미매핑 제외) → 타입 검증 → 단위 정규화(차원 불일치는 변환 금지·경고) → 공급사 규격 재계산 판정 → HYC 기준 대비 공급사 참고 판정 → 자체 결과 판정 → `source_policy` 적용해 최종 유효값 결정 → 누락 정책 → 전체 판정(C4 순서).
- 출력은 후보이며 `ACCEPTED/REJECTED/ON_HOLD` 3종(C3), 승인 시 최종으로 승격.
- 동일 입력 → 동일 출력(시계·랜덤·DB 접근 없음), `engine_version` 기록.
- 반올림은 항목 `precision`/`rounding_mode`로만 수행하고 반올림 전 값도 보존(FR-UNIT-003).

### 6.7 한국어 UX
- 기본 한국어, 상태 문구는 §10 표 그대로. 색상 단독 사용 금지(색+텍스트+아이콘).
- **라벨 분리 강제**: "공급사 규격/공급사 결과" vs "한양화학 기준/한양화학 판정" — 동일 라벨 재사용 금지(§27-38).
- 좌우 50% 패널, 1440px 기준, 좁은 화면은 Tab 전환. 키보드 중심, 숫자 필드 단위 자동 표기, 미저장 변경 경고, 장시간 작업 자동 임시저장.
- 한국어 파일명·품명·화학식·특수기호(±, %, ㎜, μ)를 전 구간 UTF-8로 처리하고 Excel 출력에서도 검증.

---

## 7. AT-001~AT-013 매핑 및 DoD

| AT | 단계 | 대표 테스트 경로 | 검증 포인트 |
|---|---|---|---|
| AT-001 COA 파싱 | S2/S3 | `tests/ocr_golden/test_golden_regression.py::test_cacl2_coa` | 행 단위 생성, 도장 겹침 필드 저신뢰, 손글씨는 참고 메모 전용 |
| AT-002 규격 분리 | S1 | `unit/test_source_policy.py`, `integration/test_inbound_flow.py::test_supplier_vs_hyc_columns` | 공급사 0.5% / HYC 0.15% 별도 컬럼, 참고 판정은 HYC 기준 |
| AT-003 누락 대체 | S1 | `unit/test_missing_policy.py`, `integration/..::test_internal_substitute_blocks_accept` | `INTERNAL_SUBSTITUTE`→`INTERNAL_TEST_PENDING`, 적합 승인 차단 |
| AT-004 가변 샘플 | S2/S3 | `ocr_golden/..::test_package_report_samples`, `unit/test_sample_policy.py` | 5측정/3정성 원문 보존, 2열 절단 없음 |
| AT-005 교차검증 | S1 | `e2e/happy_path.spec.ts`, `integration/..::test_cross_check_required` | 두 값+원문 위치 비교, 사유 선택 전 확정 불가 |
| AT-006 단위 변환 | S1(엔진)/S3(UI) | `unit/test_units.py::test_ppm_to_percent` | 동일 차원만 변환, 공식 버전 기록, 반올림 전 값 보존 |
| AT-007 자체 우선 | S1 | `unit/test_source_policy.py::test_internal_priority` | 최종 유효값=자체, 공급사 값 보존·참고 표시 |
| AT-008 중복 문서 | S1 | `integration/test_document_dedupe.py` | 새 원본 레코드 미생성, 재사용 선택지 |
| AT-009 기준 고정 | S1 | `integration/test_spec_version_freeze.py` | v2 활성화 후에도 과거 건·보고서는 v1 snapshot |
| AT-010 승인 | S1 | `integration/test_approval_immutability.py`, `e2e/happy_path.spec.ts` | 최종 판정·승인자·일시·통합 snapshot, 검사자 수정 403 |
| AT-011 부적합 | S3 | `integration/test_ncr_flow.py` | 처리방안·승인자·목표일·증빙·재검사 연결 |
| AT-012 Raw Data 출력 | S3 | `integration/test_report_raw_data.py`(fixture 라운드트립) | 호환 시트 + `Measurements_Long`, 샘플 무손실, 열 절단 금지 |
| AT-013 LOT 조회 | S1(기본)/S3(보고서) | `e2e/lot_search.spec.ts`, `integration/test_lot_trace.py` | 분할 입고 다건·문서·결과·NCR·생산LOT 자리 |

**DoD 매핑(누락 없이):** 마이그레이션/Seed 재실행(S0) · 38 템플릿 Import 또는 동등 Seed(S3, `seeds/spec_excel_import.py` + 관리자 검토) · 입고/LOT 교차검증(S1) · 샘플 PDF 2유형 파싱(S2/S3) · 저신뢰 Human Review(S3) · 문서-LOT 다대다(S0 제약 + S1 링크) · 한양화학 기준 자동 판정(S1) · 자체검사 수기 입력·가변 샘플(S1/S3) · 검사자→팀장 승인(S1) · 적합/부적합/보류/재검사/특채(S3) · 원본 불변 + SHA-256(S1) · 감사로그(S0/S1) · Raw Data·통합·LOT·통계 출력(S3) · Unit/Integration/E2E 자동화(S1~S3) · OCR Golden 회귀(S2) · 설치/운영/백업/복구 문서(S4) · OpenAPI 문서(S3) · 관리자·품질팀 가이드(S4) · 코드 내 Secret 0(전 구간 CI) · 승인 데이터 직접 수정 차단(S0 트리거 + S1 검증).

---

## 8. 검증 · 운영 · 범위 · 병렬화

### 8.1 검증 명령

```bash
docker compose up -d db redis
make migrate                 # alembic upgrade head
make migrate-down-up         # downgrade base → upgrade head 재실행 무결성
make seed                    # units / standard_test_items / spec excel draft import
pytest backend/tests/unit -q
pytest backend/tests/integration -q
pytest backend/tests/contract -q
pytest backend/tests/ocr_golden -q         # fixture Provider, 외부 호출 없음
ruff check backend && mypy backend/src/hyc/domain
lint-imports                               # domain → 인프라 의존 0 강제
npm --prefix frontend run build && npm --prefix frontend run test
npx playwright test frontend/e2e
make openapi                               # OpenAPI 산출물 갱신·diff 확인
make secret-scan                           # 하드코딩 secret 0건
bash ops/backup.sh && bash ops/restore.sh --dry-run
```

테스트는 **실제 외부 OCR 호출 금지**(§27-34). CI는 `FixtureOcrProvider` 고정.

### 8.2 보안 / 관측성 / 백업·복구 / 롤백
- **보안:** TLS, 비밀번호 해시(argon2/bcrypt), 최소 권한 RBAC, secret은 환경변수/Secret Store, MIME 검증 + 악성파일 스캔 확장 지점, 업로드 파일 실행 차단, 중요 다운로드 감사, 세션 만료·로그인 실패 제한, 외부 AI 전송 기본 비활성 + Provider별 보존 정책.
- **관측성:** 구조화 JSON 로그 + `correlation_id` 전파(HTTP→Outbox→워커), 메트릭(문서 처리 지연, OCR 실패율, 검토 큐 길이, 판정 실행 수, DLQ 깊이, 미러 복제 실패), `/health`(DB/Redis/Storage/Provider)와 서비스 상태 화면.
- **백업·복구:** DB 일일 백업, 파일 저장소 미러 또는 백업, `ops/restore.sh` 기반 **복원 리허설을 Stage 4 게이트로 실증**. RPO/RTO는 IT 환경 확정 후 승인(수치 임의 확정 금지).
- **롤백:** 이미지 태그 롤백. 마이그레이션은 파괴적 변경 금지(add-only → backfill → 스위치 → 후속 릴리스에서 제거), 릴리스마다 `downgrade` 검증, 불가하면 `ops/rollback.md`에 데이터 보정 절차 명시. Feature Flag로 기능 단위 즉시 비활성.

### 8.3 MVP 비범위 (착수 금지)
ERP/MES/WMS 실시간 연동, AQL 자동 계산, 검사 장비 직접 연동, 손글씨의 업무 필드화, 자동 이메일/메신저 통보, 완제품·출하 LOT 자동 연결, CAPA 전체 프로세스, 공급사 포털, 공인전자서명. (Event 구조·Adapter 자리·Future 테이블만 준비)

### 8.4 의존성 · 병렬 lane

```
Stage 0 (도메인/DB) ──┬─▶ Stage 1 (수직 슬라이스) ──┬─▶ Stage 3 (전체 MVP) ─▶ Stage 4 (운영/Pilot)
                      │                              │
                      └─ Lane B: 기준 Excel Import ──┘
   Lane C: OCR Golden/Benchmark (Stage 2) ── 실문서 코퍼스 확보에 의존 ──┘
   Lane D: 프론트 디자인 시스템/한국어 라벨 ── Stage 0과 병렬
   Lane E: 인프라(compose, CI, secret scan, 백업 스크립트) ── 전 구간 병렬
```

- **직렬 필수:** Stage 0 → Stage 1(판정 엔진·상태머신 없이는 슬라이스가 의미 없음).
- **병렬 가능:** Lane B는 `spec_items` 스키마 고정 후 착수 가능. Lane C는 Stage 1과 독립이나 **문서 수집이 선행조건**이라 현재 최대 리스크. Lane D/E는 즉시 시작.
- **크리티컬 패스:** 실 COA/검사성적서 코퍼스 확보 → Stage 2 → Stage 3의 OCR 의존 기능.

---

## 모델/작업 증빙

- **인식한 모델명:** Claude Opus 5 (모델 ID `claude-opus-5`).
- **읽은 파일:** `/tmp/hanyang_v0/Prd.md` 단 하나. Read를 3회(1–2031, 2032–2831, 2831–3526줄) 호출해 전체를 읽었다.
- **읽지 않은 것:** `docs/plans/*` 등 다른 계획 문서를 일절 읽지 않았다. 바이너리 PDF 2건·XLSX 2건도 열지 않았고, 사전 제공된 검증 사실(38 템플릿/119 항목, Raw Data 헤더 전용, 이미지 기반 PDF)과 PRD 본문만 근거로 삼았다.
- **수정한 것:** 없음. 프로젝트 파일을 수정하지 않았고 구현·git·설치·외부 호출도 하지 않았다. 하네스 계획 파일 작성을 시도했으나 Write 도구가 이 컨텍스트에서 비활성이라 파일 생성도 발생하지 않았다. 이 호출에서 발생한 부수효과는 0이다.
- **미확정 처리:** PRD에 없는 수치·성능치·Provider명·기간은 만들어 넣지 않았고, 아직 존재하지 않는 파일은 전부 `Create:`로 표기했다.
