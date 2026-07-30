# 요구사항 추적 매트릭스 — 한양화학 수입검사 디지털화 및 LOT 추적

**상태:** P0A/P0B complete and accepted; P1 authorized and ready (not started); P2 authorized after the P1 contract gate (not started)
**정본:** `Prd.md`  
**계획:** `docs/plans/2026-07-30-integrated-implementation-plan.md`  
**규칙:** 아래 경로는 모두 구현 시 `Create` 대상이다. `Planned`는 통과를 의미하지 않는다. 각 행은 해당 Phase의 테스트가 실제 exit 0이고 Hermes 독립 QA가 증빙을 확인해야 `Verified`로 바뀐다.

## 소유자

- **DOMAIN:** 순수 판정·정책·상태 도메인
- **DATA:** PostgreSQL/Alembic/repository/invariant
- **API:** FastAPI application/RBAC/idempotency/OpenAPI
- **WORKER:** ingestion/OCR/parser/report/outbox
- **WEB:** Next.js UI/접근성/E2E
- **OPS:** 보안/관측/백업/복구/배포
- **QUALITY:** 품질팀 정책·golden/UAT 승인
- **HERMES-QA:** 독립 검증·gate 판정

## P0B delivery trace

|P0B task|Delivered candidate|Verification / ADR binding|Current gate|
|---|---|---|---|
|P0B.1|`backend/scripts/import_spec_workbook.py`|`backend/tests/integration/importers/test_spec_workbook_dry_run.py`: synthetic-only dry run; bounded all-member CRC/decompression reads; canonical OPC Content-Type resolution and media-type-driven XML parsing; exact workbook/worksheet/shared-strings/`.rels` types; complete ASCII RFC 3986 Relationship-Type and conservative canonical OPC member/Override/Target lexical validation (including safe in-root `..` only), attribute-free `Relationships` roots, unique IDs while same-target distinct typed relationships remain permitted; all fail closed|accepted|
|P0B.2|`fixtures/spec-import/qm301-7-expected.json`|Typed approved baseline binds 38 templates / 119 item rows to the approved source SHA-256; deterministic ordered `QUALITY_REVIEW_REQUIRED` digest/count discrepancy evidence, no auto-correction/apply|accepted|
|P0B.3|`fixtures/manifests/source-documents.yaml`|Metadata-only manifest with P0A evidence/digest/alias provenance; `.gitignore` recursively excludes sensitive document basenames; importer tests generate temporary synthetic workbooks only|accepted|
|P0B.4|`docs/adr/0001-deployment-and-data-boundary.md` through `docs/adr/0004-local-auth-rbac-and-real-source-prohibition.md`|Read-only, external-OCR-off, LOT/allocation, and source-prohibition decisions remain binding|accepted|

P0B final independent review: `APPROVE` after 67 in-memory probes (HIGH 0, MEDIUM 0). The accepted LOW note—generic scheme-specific URI semantics—remains defense-in-depth because the relationship roles consumed by the importer use exact allowlists. Controller evidence records `127 passed`; the approved real QM301 dry-run returned 38 templates/119 rows with discrepancy 0, DB write/apply 0, unchanged source hash/size/mtime, and tracked sensitive documents 0.

## 1. 기능 요구사항 전수 추적

|Requirement|요약|Phase|Owner|대표 Planned 검증|승인/Gate|
|---|---|---:|---|---|---|
|FR-MST-001|품목 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_material_master.py`; `frontend/tests/e2e/master-data.spec.ts`|AP-04, P5|
|FR-MST-002|공급업체 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_supplier_master.py`|AP-04, P5|
|FR-MST-003|모델 마스터|P2/P5|DATA/API/WEB|`backend/tests/integration/api/test_model_master.py`|P5|
|FR-MST-004|품목-공급사-모델 매핑|P2/P5|DATA/API|`backend/tests/integration/db/test_supplier_material_model_scope.py`|P2|
|FR-MST-005|nullable 코드/후속 업데이트|P2/P5|DATA/API|`backend/tests/integration/db/test_nullable_code_uniqueness.py`; import dry-run|P5|
|FR-MST-006|BOM 확장 준비|P2|DATA/API|`backend/tests/contract/test_erp_bom_seam.py`(feature OFF)|AP-08; 자동연계 비범위|
|FR-SPEC-001|공통/공급사/모델 기준 프로파일|P2|DOMAIN/DATA|`backend/tests/unit/specifications/test_spec_selection.py`; overlap DB test|AP-03, P2|
|FR-SPEC-002|Draft/Active 기준 버전·적용일|P2/P5|DOMAIN/DATA/API|`backend/tests/integration/db/test_spec_version_lifecycle.py`|P2/P5|
|FR-SPEC-003|표준 검사항목|P2/P5|DATA/API/QUALITY|seed replay + `test_standard_test_items.py`|QUALITY review|
|FR-SPEC-004|규격 operator/정성/사용자 정의|P2|DOMAIN/DATA|`backend/tests/unit/specifications/test_spec_expression.py`; operator CHECK|P2; custom은 MANUAL|
|FR-SPEC-005|결과 출처 정책|P2|DOMAIN|`backend/tests/unit/judgment/test_source_policy.py`|P2|
|FR-SPEC-006|COA 누락 정책|P2/P3|DOMAIN/API|`backend/tests/unit/judgment/test_missing_policy.py`; hold integration|P3|
|FR-SPEC-007|샘플 계산/판정 정책|P2/P5|DOMAIN/QUALITY|`backend/tests/unit/judgment/test_sample_policy.py`|항목 정책 QUALITY 승인|
|FR-INB-001|입고 생성·필드|P2/P3|DATA/API/WEB|`backend/tests/integration/api/test_inbound_receipt.py`; vertical slice|P3|
|FR-INB-002|임시저장·OCR/수기 교차검증|P3|API/WEB|`frontend/tests/e2e/cross-validation.spec.ts`|P3|
|FR-INB-003|LOT 관계 유연성|P2/P3|DOMAIN/DATA/API|`backend/tests/integration/db/test_material_lot_identity.py`; `test_split_lot_trace.py`|AP-03, P2|
|FR-DOC-001|NAS/Drive/수동 수집|P3/P6|WORKER/API|manual upload P3; source adapter contract P6|AP-01/02/06|
|FR-DOC-002|파일 안정화|P6|WORKER|`backend/tests/integration/workers/test_stabilizing_watcher.py`|P6|
|FR-DOC-003|원본 hash/불변/metadata|P2/P3|DATA/API/OPS|`backend/tests/integration/api/test_document_immutability.py`|AP-05, P3|
|FR-DOC-004|SHA-256 중복 탐지/재사용|P3|API/DATA|`backend/tests/integration/api/test_document_dedup.py`|P3|
|FR-DOC-005|Storage Adapter/Primary/Mirror|P1/P6|WORKER/OPS|storage contract + mirror failure test|AP-06, P6|
|FR-OCR-001|정확도 우선 파이프라인|P4/P5|WORKER/QUALITY|`backend/tests/golden/test_pipeline_regression.py`|AP-02, QUALITY benchmark|
|FR-OCR-002|Provider 추상화|P1/P4|WORKER|`backend/tests/contract/test_extraction_port.py`|P4|
|FR-OCR-003|구조화 출력 schema/원문 위치|P1/P4|WORKER/API|JSON Schema/Pydantic contract + golden bbox|P1/P4|
|FR-OCR-004|손글씨는 참고 메모|P4|WORKER/QUALITY|`test_handwriting_never_business_field.py`|P4|
|FR-OCR-005|confidence/Human Review|P3/P4|API/WEB/QUALITY|low-confidence hold + review E2E|P3/P4|
|FR-OCR-006|합계/범위/날짜/누락 논리 검증|P2/P4|DOMAIN/WORKER|`backend/tests/unit/judgment/test_logical_validation.py`; golden|P4|
|FR-MAP-001|표준 항목 별칭|P2/P5|DATA/API|`backend/tests/integration/api/test_alias_mapping.py`|P5|
|FR-MAP-002|mapping 상태|P2/P3|DOMAIN/API|unmapped excluded/hold tests|P3|
|FR-MAP-003|학습형 운영(승인 전 전역 금지)|P5|API/QUALITY|`test_alias_approval_scope.py`|QUALITY approval|
|FR-UNIT-001|단위 마스터/차원/공식 버전|P2|DOMAIN/DATA|`backend/tests/unit/judgment/test_unit_registry.py`|P2|
|FR-UNIT-002|자동 환산/차원 일치|P2/P3|DOMAIN|`backend/tests/unit/judgment/test_unit_conversion.py`|P2|
|FR-UNIT-003|원값/환산값/공식/반올림 기록|P2|DOMAIN/DATA|snapshot serialization test|P2|
|FR-JDG-001|판정 단계와 hold 우선순위|P2|DOMAIN|`backend/tests/unit/judgment/test_engine_pipeline.py`|P2|
|FR-JDG-002|공급사/HYC 기준 분리|P2/P3|DOMAIN/API/WEB|`test_supplier_vs_hyc_spec.py`; panel E2E|P3|
|FR-JDG-003|자체 검사 우선|P2/P3|DOMAIN|`backend/tests/unit/judgment/test_source_policy.py`|P2|
|FR-JDG-004|전체 후보/업무 최종상태|P2/P3/P5|DOMAIN/API|engine 3-state + workflow 5-state transition tests|P3/P5|
|FR-JDG-005|기준·근거 Snapshot 재현성|P2/P3|DOMAIN/DATA/API|`test_spec_snapshot_immutability.py`; canonical hash|P3|
|FR-INT-001|자체검사 대상 표시|P3/P5|DOMAIN/WEB|hold integration + panel E2E|P3|
|FR-INT-002|자체검사 입력 필드|P3/P5|API/WEB|`test_internal_results_api.py`|P3/P5|
|FR-INT-003|가변 샘플|P2/P4/P5|DOMAIN/DATA/WEB|sample property + package golden + E2E|P5|
|FR-INT-004|임시저장|P3|API/WEB|versioned autosave/conflict E2E|P3|
|FR-INT-005|계산값|P2/P3|DOMAIN|sample aggregate tests|P2|
|FR-INT-006|사진/시험기록 증빙|P5|API/WEB/OPS|attachment validation/audit E2E|P5|
|FR-APR-001|검사자 제출 검증|P2/P3|DOMAIN/API|`test_submit_guards.py`|P3|
|FR-APR-002|팀장 검토/승인·역할분리|P2/P3|API/WEB|`test_rbac_approval.py`; E2E|AP-04, P3|
|FR-APR-003|반려/사유/재제출|P2/P5|DOMAIN/API/WEB|transition + return/resubmit E2E|P5|
|FR-APR-004|확정 불변/Snapshot/정정 revision|P2/P3|DATA/API|`test_approval_atomicity.py`; DB mutation denial|P3|
|FR-NCR-001|처리방안|P5|DOMAIN/API/WEB|`test_nonconformance_disposition.py`|P5|
|FR-NCR-002|부적합 기록/승인/기한/증빙|P5|DATA/API/WEB|`frontend/tests/e2e/nonconformance.spec.ts`|P5|
|FR-NCR-003|재검사 연결|P2/P5|DOMAIN/DATA/API|`test_retest_vs_revision.py`|P5|
|FR-NCR-004|모듈 Feature Flag|P1/P5|API/WEB|`test_feature_flags.py`|P5; invariant guard는 비활성 불가|

## 2. 화면·매칭·데이터·API·보고서 정책 추적

|Policy ID|PRD 범위|Phase|Owner|대표 Planned 검증|Gate|
|---|---|---:|---|---|---|
|UI-001|§12.1 목록 컬럼·필터·통합검색|P5|API/WEB|`frontend/tests/e2e/inspection-list-filter.spec.ts`; API query tests|NFR-PERF|
|UI-002|§12.2 좌우 상세·원문/bbox·자체검사·경고|P3/P5|WEB/API|vertical slice + `inspection-detail.spec.ts`|P3/P5|
|UI-003|§12.3 OCR 검토 단축키/저신뢰/체크리스트|P3/P5|WEB|`ocr-review-accessibility.spec.ts`|P5|
|UI-004|§12.4 기준 비교/편집/Draft→활성/Import|P5|WEB/API/QUALITY|`spec-version-management.spec.ts`|QUALITY 승인|
|UI-005|§12.5 승인건 통계·테스트/취소 제외|P5|API/WEB|`test_quality_stats_snapshot_only.py`|P5|
|MATCH-001|§13.1 우선순위|P2/P3|DOMAIN|`backend/tests/unit/documents/test_match_ranking.py`|AP-03|
|MATCH-002|§13.2 후보도 잠정, 핵심 충돌 자동금지, section 분리|P3/P4|DOMAIN/API/WEB|ambiguous/no-match/manual confirmation tests|P3/P4|
|MATCH-003|§13.3 상태·재연결 감사|P2/P3|DATA/API|`test_document_relink_audit.py`|P3|
|DATA-001|§14.1/14.2 관계·테이블|P2|DATA|migration schema snapshot/constraints|AP-03|
|DATA-002|§14.3 승인/기준/checksum/Decimal/FK/soft-delete/UTC|P2|DATA/DOMAIN|DB invariant suite|P2|
|DATA-003|canonical LOT 보정|P2|DATA/DOMAIN|identity conflict/merge/concurrency/re-entry tests|AP-03|
|API-001|§15.1 endpoint surface/OpenAPI|P1~P5|API|`backend/tests/contract/test_openapi_contract.py`|P5|
|API-002|§15.2 upload/approve/report Idempotency-Key|P2/P3/P5|API/DATA|endpoint별 same-key same-hash replay + key/hash conflict tests|P3/P5|
|API-003|§15.2 RBAC/correlation/error/page/filter/sort/version/reason/size/Job ID|P1~P5|API|common middleware/contract/integration suite|P5|
|REP-001|§16.1 Raw 호환+Long+Documents+optional Audit, 무절단|P5|WORKER/QUALITY|`test_raw_excel_lossless.py`|QUALITY sample approval|
|REP-002|§16.2 승인 Snapshot 통합보고서·정정 버전|P5|WORKER/DATA|`test_integrated_report_from_snapshot.py`|P5|
|REP-003|§16.3 LOT trace·분할 입고·production link seam|P3/P5|API/WORKER|`test_split_lot_trace.py`; `test_production_lot_link_seam.py`|AP-08; 자동 ERP 비범위|
|REP-004|§16.4 월별/공급사 품질 통계|P5|API/WORKER|`test_supplier_quality_report.py`|P5|
|ARCH-001|§17.1 stack와 OCR/판정 분리|P1/P2|HERMES-QA|import-linter, process/component smoke|P2|
|ARCH-002|§17.2 API/DB/storage/queue/worker/ERP adapter|P1~P6|API/WORKER/OPS|contract/smoke/feature-off tests|P6|
|ARCH-003|§17.3 metadata vs immutable source/derived artifacts/mirror|P2/P6|DATA/WORKER/OPS|storage/mirror/lineage tests|AP-06, P6|

## 3. 보안·감사·보존/NFR 전수 추적

|Policy ID|PRD 요구|Phase|Owner|대표 Planned 검증|Gate|
|---|---|---:|---|---|---|
|SEC-001|§18.1 TLS, 안전 hash, 최소권한, secret, MIME/scan, 실행금지, AI 정책, download audit, session 제한|P1/P5/P6|API/OPS/HERMES-QA|threat-model checklist, upload attack fixtures, RBAC, secret scan, TLS config inspection|AP-01/02/04, production|
|AUD-001|§18.2 11개 감사 이벤트 군 전부|P2/P3/P5|DATA/API/HERMES-QA|`backend/tests/integration/db/test_audit_event_matrix.py`가 요구 event matrix 순회|P5|
|RET-001|§18.3 설정형 보존, 승인>=원본, audit 삭제 제한|P2/P6|DATA/OPS|retention policy/permission/expiry dry-run tests|AP-08|
|BACKUP-001|§18.3 DB 일일 백업, 파일 백업/이중화, 복원 문서, RPO/RTO 승인|P6|OPS/HERMES-QA|`scripts/backup.sh` + disposable `restore-verify.sh` row/hash manifest|AP-08, production|
|NFR-ACC|§19.1 deterministic, no LLM final, bbox, raw/normalized/final, parse fail review|P2~P5|DOMAIN/WORKER/WEB|domain/golden/E2E fail-closed suites|P3/P5|
|NFR-PERF|§19.2 list/detail 2s, 100k search 3s, upload receipt 3s, report async|P5/P6|API/DATA/OPS|`backend/tests/performance/test_query_targets.py`; dataset/load profile and environment recorded|Pilot; 실제 규모 후 조정|
|NFR-AVAIL|§19.3 OCR 장애 시 수기 흐름, retry/manual, DLQ, status|P3/P6|API/WORKER/OPS|OCR-off vertical slice; worker kill/retry/DLQ/status tests|P3/P6|
|NFR-EXT|§19.4 no-code config, provider/ERP adapters, unlimited item/sample, site/warehouse IDs|P1/P2/P5|DOMAIN/API/WORKER|config-driven alias/schema tests, large variable-sample property tests, feature-off ERP contract|P5|
|NFR-UX|§19.5 한국어, 색+텍스트, 숫자 즉시 오류, 상태 구분, 유실 방지|P3/P5|WEB|Playwright accessibility/keyboard/autosave/conflict tests|P5|
|OCR-BENCH-001|§20.1 provider 고정 전 representative golden와 10개 지표|P4|WORKER/QUALITY|versioned runner/metrics report; 표본 대표성 QUALITY 승인|AP-02, P4|
|OCR-EDGE-001|§20.2 20개 edge case|P2~P5|DOMAIN/WORKER/API|`backend/tests/golden/test_required_edge_cases.py` + AT tests; 각 edge ID별 parameterized case|P5|

## 4. API Idempotency 계약 정본

|Endpoint family|Scope/Request hash|Same key + same hash|Same key + different hash|보존|Planned test|
|---|---|---|---|---|---|
|`POST /documents/upload`|`principal_id + route + key`; streaming file SHA-256 + canonical metadata|기존 canonical document/job의 최초 status/body를 반환; 새 원본/작업 없음|`409 IDEMPOTENCY_KEY_REUSED`|업로드 업무/보존 정책 이상; 만료 후에도 checksum dedupe는 독립 유지|`backend/tests/integration/api/test_upload_idempotency.py`|
|`POST /inspection-cases/{id}/approve`|actor+case+key; case id, expected version, action, canonical reason/comment|기존 approval/snapshot 응답 반환; audit/approval 1건|409; final-state guard도 거부|approval/audit와 동일 기간, 임의 만료 금지|`backend/tests/integration/api/test_approval_idempotency.py`|
|`POST /reports/*`|actor+route+key; report kind, approved snapshot IDs, canonical filters, template version|동일 report job/resource 반환; worker 중복 없음|409|job/resource 보존기간 이상|`backend/tests/integration/api/test_report_idempotency.py`|

공통 `idempotency_records`에는 key, principal/scope, request hash, state(`PENDING/COMPLETED/FAILED_RETRYABLE`), status/body/resource, created/completed/expires를 저장한다. PENDING lease 회수와 crash recovery를 테스트한다. Generic TTL은 설정형이지만 승인 key는 approval/audit 보존보다 짧아질 수 없다.

## 5. Canonical LOT identity 계약 정본

- Pilot 기본 identity policy: `(supplier_id, material_id, normalized_supplier_lot_no)`. 생산일·입고일·수량·모델은 일치/충돌 증거이지 기본 key가 아니다. 이는 동일 공급사 LOT의 분할 입고를 하나로 조회하는 AT-013에 맞춘다.
- 원문 `supplier_lot_no_raw`는 불변 보존한다. 기본 normalization은 Unicode NFKC와 양끝 공백 제거만 적용하며 case·내부 구분자는 자동 변경하지 않는다. 공급사별 추가 normalization은 versioned policy와 QUALITY 승인 후에만 허용한다.
- 공급사가 LOT 번호를 재사용해 생산일 등 추가 구분자가 필요하다는 현업 근거가 있으면 AP-03에서 `lot_identity_policy`의 components를 버전 지정한다. 기존 identity를 조용히 재계산하지 않는다.
- `material_lots(supplier_id, material_id, identity_policy_version, identity_key)`에 `UNIQUE`; concurrent create는 transaction + unique conflict/upsert로 기존 canonical id를 반환한다.
- 필수 component가 누락되면 `PROVISIONAL`; 자동 병합·최종 판정에 사용하지 않고 `CONFLICT_REVIEW`로 보낸다.
- promotion/merge는 QUALITY Lead와 master-data ADMIN의 분리된 권한, expected version, 사유, advisory/row lock, 링크 이관 transaction, `merged_into_id`, append-only audit로 수행한다. 원 canonical row는 삭제하지 않는다.

Planned tests:

- `backend/tests/integration/db/test_material_lot_identity.py`
- `backend/tests/integration/db/test_concurrent_lot_creation.py`
- `backend/tests/integration/api/test_same_lot_reentry.py`
- `backend/tests/integration/api/test_provisional_lot_conflict.py`
- `backend/tests/integration/api/test_lot_merge_audit.py`
- `backend/tests/integration/api/test_split_lot_trace.py`

## 6. AT-001~AT-013 추적

|AT|Phase|대표 Planned 검증|Gate/보정|
|---|---:|---|---|
|AT-001 COA 파싱|P4/P5|`backend/tests/golden/test_calcium_chloride_coa.py`|행/LOT/spec/result/bbox, 도장 저신뢰, 손글씨 참고|
|AT-002 공급사/HYC 규격 분리|P2/P3|`backend/tests/unit/judgment/test_supplier_vs_hyc_spec.py`|컬럼·판정 독립|
|AT-003 필수 누락 대체|P2/P3|`backend/tests/integration/api/test_internal_substitute_hold.py`|자체검사 전 hold/승인 차단|
|AT-004 가변 샘플|P4/P5|`backend/tests/golden/test_domestic_8p_samples.py`|5개/3개 값·원문·순서 무손실|
|AT-005 입고 교차검증|P3|`frontend/tests/e2e/cross-validation.spec.ts`|원문/OCR/수기/final/사유|
|AT-006 단위 자동 변환|P2|`backend/tests/unit/judgment/test_unit_conversion.py`|dimension/formula version/Decimal/pre-round|
|AT-007 자체 결과 우선|P2/P3|`backend/tests/unit/judgment/test_source_policy.py`|internal effective, supplier 보존|
|AT-008 중복 문서|P3|`backend/tests/integration/api/{test_document_dedup.py,test_upload_idempotency.py}`|checksum dedupe+Idempotency-Key|
|AT-009 기준 버전 고정|P2/P3|`backend/tests/integration/db/test_spec_snapshot_immutability.py`|v2 활성 뒤 과거 v1 불변|
|AT-010 승인|P3|`backend/tests/integration/api/{test_approval_atomicity.py,test_approval_idempotency.py}`|snapshot/approval/audit 원자성·중복 0|
|AT-011 부적합 처리|P5|`frontend/tests/e2e/nonconformance.spec.ts`|처리/승인/목표일/증빙/재검사|
|AT-012 Raw Data 출력|P5|`backend/tests/integration/{reports/test_raw_excel_lossless.py,api/test_report_idempotency.py}`|호환+Long·무손실·동일 job replay|
|AT-013 LOT 조회|P3/P5|`backend/tests/integration/api/{test_split_lot_trace.py,test_production_lot_link_seam.py}`|분할 입고/문서/검사/NCR + feature OFF production link 저장·조회·보고서 seam; ERP 자동 수집은 비범위|

## 7. Definition of Done 세부 추적

|DoD group|Phase|Verification owner/evidence|
|---|---:|---|
|Migration/Seed 재실행, 38 template Draft import|P1/P2/P5|DATA + HERMES-QA; disposable migration replay, importer dry-run/apply snapshot|
|입고/LOT·OCR/수기 교차검증·문서 M:N|P2/P3|API/WEB; vertical Slice + true LOT identity contracts|
|두 PDF 유형·저신뢰 Human Review·OCR golden|P4/P5|WORKER/QUALITY; approved corpus golden report|
|HYC 판정·자체검사·가변 sample|P2~P5|DOMAIN/API/WEB; property/integration/E2E|
|검사자→팀장·5 workflow 결과·NCR|P3/P5|API/WEB/QUALITY; role/state/NCR E2E|
|원본 불변/hash·감사·승인 직접수정 차단|P2/P3|DATA/API/HERMES-QA; app+DB denial tests|
|Raw/통합/LOT/통계 4종 출력|P5|WORKER/QUALITY; snapshot fixture, no-truncation, production-link seam|
|Unit/Integration/E2E/OpenAPI/Golden|P1부터 누적|HERMES-QA가 실제 명령과 exit code 재검증|
|설치/운영/백업/복구·관리자/품질팀 가이드|P6|OPS/QUALITY; clean install + restore rehearsal + tabletop|
|외부 Secret 0|모든 Phase|secret scan + config review|

## 8. 승인 상태

현재 매트릭스는 계획상 추적을 완결한 것이며 P0A/P0B는 complete·accepted다. P1은 authorized and ready지만 시작·완료되지 않았고, P2는 P1 contract gate 후에만 시작할 수 있으며 완료를 주장할 수 없다. 실데이터 apply·import, 외부 OCR·AI, 비일회성 migration, 배포와 서비스 공개는 계속 미승인이다.
