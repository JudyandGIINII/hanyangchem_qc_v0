# P6 Operations 범위·설계 계획

**작성일:** 2026-08-11
**선행 문서:** [`HANDOFF.md`](../HANDOFF.md) 2026-08-10 P5 종료 섹션, [`KANBAN.md`](../KANBAN.md), [`TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md), `Prd.md` Phase 2
**기준 커밋:** `b49f62a` (`docs: close P5 and hand off to P6`)
**Alembic head:** `20260810_0007_inspection_return_reasons`

---

## 0. 한 문단 요약

P6는 PRD `Phase 2: Operations`다. P1~P5가 "검사 한 건을 넣고 판정하고 승인하는 것"을 만들었다면, P6는 **쌓인 데이터를 실제 업무에서 꺼내 쓰는 단계**다. 이번 P6는 7개 조각으로 나눈다. 앞 3조각(보고서·통계·부적합 후속조치)은 지금 바로 값어치가 나오는 완성품이고, 뒤 4조각(수집·Import·모니터링·백업)은 실물 연결만 남긴 상태로 미리 깔아두는 것이다.

---

## 1. 승인 상태

### 1.1 이번 문서가 기록하는 승인

2026-08-11 사용자 결정으로 **P6 전체가 승인됐다.** 승인 시 사용자가 함께 지시한 조건이 있다.

> "OCR 운영 모니터링을 할 COA 샘플이 없다. 이건 나중에 확보하면 수행할 수 있게 준비만 해. NAS, 구글 드라이브 자동 수집도 당장 접속이 안되니까 준비만 해. master import는 import 테스트 할 엑셀은 없지만 이것도 나중에 필요한 기능이니까 준비해. 결과적으로 p6는 모두 승인이다."

즉 승인의 성격은 **"만들어라"**이지 **"없는 실물을 만들어내라"**가 아니다. 세 항목은 실물 부재가 원인이므로 실물이 붙는 자리를 정확히 비워둔 채 완성한다.

추가로 보존 정책/백업 두 P6 태그 행에 대해서는 **백업/복구만 포함하고 보존 정책은 제외**하기로 결정했다.

### 1.2 이 승인이 부여하지 않는 것

이 승인은 아래를 부여하지 않는다. 반드시 별도 승인이 필요하다.

- 실제 NAS/Google Drive/ERP **접속·자격증명·네트워크 호출**
- 실 PDF/XLS/XLSX의 **Git 커밋·업로드·외부 전송** (AP-05 계속 유효)
- 외부 OCR/AI Provider 호출 (AP-02 절차 승인은 Provider 승인이 아님)
- production/비일회성 migration, production DB-role activation
- release·production readiness 선언, 공개 서비스 노출
- **보존 기간·만료·삭제 규칙** (RET-001 / AP-08 계속 미승인)

### 1.3 사실상의 제약 — 승인으로 풀리지 않는 것

승인 여부와 무관하게 **데이터가 없어서 정할 수 없는 값**이 있다.

- **OCR 품질 KPI 임계값**: PRD §3.3이 "초기 운영 데이터를 확보한 후 기준선을 측정한다"고 명시한다. COA 샘플 없이 "정확도 95% 이상" 같은 합격선을 코드에 넣으면 근거 없는 숫자가 굳는다. **P6에서는 지표를 수집·표시만 하고 합격/불합격 판정선을 만들지 않는다.**
- **샘플링/판정 정책 (FR-SPEC-007, FR-INT-003)**: P5에서 QUALITY 게이트로 남은 항목이며 P6가 이를 해제하지 않는다.
- **부적합 severity 기준·목표 완료일 산정 규칙**: 품질 정책이다. P6-3은 기한을 **입력받아 관리**하되 **산정 공식을 만들지 않는다.**

---

## 2. P6 범위 확정

### 2.1 포함 (7조각)

|조각|PRD/매트릭스 근거|성격|
|---|---|---|
|P6-1 보고서 공통 틀 + 통합 검사보고서|REP-002, API-002(report Idempotency), API-003(Job ID), NFR-PERF(report async)|완성|
|P6-2 LOT 추적·통계·통계 화면·Raw Data 엑셀|REP-003, REP-004, UI-005, REP-001|완성|
|P6-3 부적합 후속조치|PRD Phase 2 "부적합 후속조치", P5 FR-NCR-002 위 확장|완성|
|P6-4 NAS/Drive 수집 준비|FR-DOC-001, FR-DOC-002, FR-DOC-005, ARCH-002, ARCH-003|준비(seam)|
|P6-5 마스터 Import 준비|PRD Phase 2 "마스터 Import", UI-004 Import|준비(seam)|
|P6-6 OCR 운영 모니터링|PRD Phase 2 "OCR 운영 모니터링", NFR-AVAIL status|준비(임계값 제외)|
|P6-7 백업/복구|BACKUP-001|완성|

### 2.2 제외

|항목|사유|
|---|---|
|보존 정책 (RET-001)|보관 기간은 경영·품질 판단이며 AP-08 미승인. 숫자 없이 만들면 헛돈다|
|Feature Flag|P5 FR-NCR-004로 **이미 완료**. 5개 모듈 플래그와 32조합 전수 회귀가 존재하므로 재작업 없음|
|FR-SPEC-003 / FR-SPEC-007 / FR-MAP-003 / FR-OCR-001 / FR-INT-003|P5 잔여 5행. 전부 QUALITY/AP-02 승인 대기이며 P6가 해제하지 않는다|

### 2.3 "준비(seam)"의 정확한 의미

모호해지지 않도록 4개 조건으로 못 박는다. 네 조건을 다 만족해야 "준비 완료"다.

1. **연결 규격이 코드로 확정된다** — 포트(Protocol)와 데이터 계약이 존재하고 contract 테스트로 고정된다
2. **합성 구현체로 전 흐름이 게이트를 통과한다** — 실물 없이 end-to-end가 실제로 돌아가고 CI에서 초록이다
3. **실물이 붙는 지점이 어댑터 1개로 국소화된다** — 나중에 하는 일이 "새 개발"이 아니라 "어댑터 구현 + 설정"이다
4. **기능 플래그로 꺼진 채 들어간다** — 켜지 않으면 어떤 부수효과도 없고, off 상태가 테스트로 고정된다(ARCH-002 feature-off 계약)

이는 이 저장소가 이미 쓰는 패턴이다. `LocalOcrExtractionProvider`가 extraction 포트 뒤에 있고, `module_exposure.py`가 노출 플래그를 격리하는 방식과 동일하다.

---

## 3. 확정된 설계 결정

|#|결정|대안|채택 사유|
|---|---|---|---|
|D1|첫 조각은 **보고서·통계 라인**|부적합 후속조치 / 운영 관측|품질팀이 매일 쓰는 산출물이고, 이미 불변으로 확정된 승인 스냅샷 위에서 **읽기 전용**으로 구현되어 새 승인이 필요 없다|
|D2|**Job 리소스 + in-process 실행기**|동기 생성 / Redis 큐+워커|PRD가 `report async`(NFR-PERF)와 `Job ID`(API-003)를 명시하므로 동기 생성은 나중에 API 표면을 깨는 재작업을 부른다. Redis 큐는 retry/DLQ(NFR-AVAIL)까지 끌고 들어와 첫 조각 범위를 넘는다. 실행기를 `ReportRunner` 포트로 분리해 나중에 워커로 옮겨도 API가 안 깨지게 한다|
|D3|산출물은 **별도 `report_artifacts` 테이블 + 기존 StoragePort 재사용**|매번 재생성 / `documents`에 통합|ARCH-003이 "원본 불변 소스 vs 파생 산출물" 구분을 명시적으로 요구한다. `documents`에 섞으면 원본 COA와 시스템 생성물이 같은 집합이 되어 감사·추적 의미가 흐려진다. 삭제 경로를 만들지 않아 미승인 보존 정책 공백을 침범하지 않는다|
|D4|보고서 출처를 **스냅샷 / 조회시점으로 이원화하고 문서에 명시 렌더**|스냅샷 스키마 확장|아래 §4 참조|

---

## 4. 핵심 설계 발견 — 스냅샷 정본성의 한계

### 4.1 현황

`decision_snapshots`는 inspection_case당 **unique 1건**, canonical JSON + SHA-256 `content_hash`, `APPROVAL_SNAPSHOT_REQUIRED_KEYS` 20개 키를 `DecisionSnapshot.freeze_for_approval`이 강제한다(`hyc_domain/snapshots.py`, 구성 지점은 `hyc_data/repositories.py:690-747`). REP-002가 요구하는 "승인 시점 Snapshot 기준 생성"의 토대로 적합하다.

### 4.2 갭

PRD §16.2 요구 항목 중 **5개가 스냅샷에 없다.**

|§16.2 요구|스냅샷 상태|
|---|---|
|적용 기준 버전 / 공급사 항목·규격·결과 / 자체검사 / 최종 유효값·판정 근거 / 누락 항목 처리 / 원본 문서 해시|있음 (`spec_version`, `spec_items`, `supplier_results`, `internal_results`, `item_decisions`, `missing_policy`, `overall_decision`, `decision_reasons`, `document_hashes`)|
|품목/공급업체/모델 **명칭**|**없음** — `profile_id`/`model_id`/`lot_id` 등 UUID만|
|원본 COA **정보**(파일명·업로드일)|**없음** — `document_hashes` 해시 목록만|
|**부적합/특채**|**없음** — NCR은 P5에서 신설|
|**첨부파일 목록**|**없음**|
|**검사자**(제출자)|**없음** — `approver`(LEAD)만|

### 4.3 결정 (D4)

**스냅샷 스키마를 확장하지 않는다.** 대신 보고서에서 출처를 이원화하고 그 사실을 문서에 렌더한다.

- **판정에 관한 모든 값은 오직 스냅샷에서만 읽는다.** DB 현재 상태로 판정값을 덮어쓰는 코드 경로를 만들지 않는다.
- 명칭·COA 메타·부적합·첨부는 현재 DB에서 조회하되, 보고서 각 섹션 헤더에 `승인 시점 고정` 또는 `조회 시점: <UTC ISO8601>`을 **셀로 출력**한다.

**사유 두 가지.**

1. `APPROVAL_SNAPSHOT_REQUIRED_KEYS`를 바꾸면 기존 `content_hash` 계약이 깨지고 `snapshot.verify()`가 과거 행에서 실패한다. 이미 승인된 건은 소급 불가하다.
2. 결정적 사유: **부적합은 승인 이후에 발생하는 사후 사건이다.** 승인 시점에 존재하지 않던 NCR을 승인 스냅샷에 얼리는 것은 모델링상 틀렸다.

**대가:** "보고서는 전부 불변 스냅샷"이라는 단순한 서술을 포기한다. 이는 문서화된 의도적 트레이드오프이며, 출처 명시 렌더가 그 대가를 사용자에게 보이게 만드는 장치다.

**테스트로 고정할 것:** 판정 관련 셀은 DB를 변경해도 값이 바뀌지 않고, 참조 정보 셀은 바뀌며, 두 섹션의 출처 라벨이 실제로 렌더된다는 양방향 회귀.

---

## 5. 조각별 계획

각 조각은 독립 롤백 가능해야 한다. 마이그레이션은 조각당 단일 리비전, 순수 DDL을 유지한다(마이그레이션 metadata 독립성 계약).

**리비전 번호는 실제 전달 순서에 따라 구현 시점에 부여한다.** 아래 표기(`20260811_0008` 등)는 조각별 스키마 소요를 보이기 위한 것이며 조각 순서가 바뀌면 번호도 바뀐다. 현재 head는 `20260810_0007`이다.

|조각|신규 테이블|
|---|---|
|P6-1|`report_jobs`, `report_artifacts`|
|P6-2|**없음** — job kind만 확장, 통계는 기존 행에서 집계|
|P6-3|후속조치 이력 1개|
|P6-4|수집 커서/이력 1개 (어디까지 훑었는지, 안정화 대기 중인 항목). 중복 차단은 기존 `documents` 재사용|
|P6-5|import 배치 이력 + 행 단위 결과|
|P6-6|**없음** — 기존 extraction/document 행에서 집계. 별도 지표 테이블을 만들지 않는다|
|P6-7|**없음** — 스크립트만|

### P6-1 — 보고서 공통 틀 + 통합 검사보고서

**목표:** REP-002. 이후 모든 보고서가 재사용할 실행 프레임을 하나의 산출물로 검증한다.

**만드는 것**

- 마이그레이션 `20260811_0008`: `report_jobs`, `report_artifacts`
  - `report_jobs`: kind, 파라미터(canonical JSON), state(`QUEUED`/`RUNNING`/`SUCCEEDED`/`FAILED`), 실패 사유 코드, 요청자, 타임스탬프
  - `report_artifacts`: job FK, SHA-256 digest, byte size, media type, storage key. **쓰인 뒤 불변**, DELETE 거부 트리거
- `hyc_api/routes/reports.py`
  - `POST /api/v1/reports` → `202 Accepted` + Job ID. `Idempotency-Key` 필수(API-002). 기존 `IdempotencyKey` 테이블·savepoint 패턴 재사용
  - `GET /api/v1/reports/{job_id}` → 상태 폴링
  - `GET /api/v1/reports/{job_id}/download` → 산출물 스트리밍. **다운로드 전건 감사 기록**(SEC-001)
- `hyc_api/services/reports.py`: `ReportRunner` 포트 + in-process 구현체. 워커 이관 시 이 포트만 갈아끼운다
- `hyc_worker`가 아니라 API 프로세스에서 실행하되, 실행 함수는 순수하게 `(snapshot, lookups) -> bytes`
- 통합 검사보고서 생성기: PRD §16.2 13개 항목 전부. 출처 이원화 라벨 포함
- 정정 버전: PRD §16.2 "원본 데이터 정정 시 새 버전" — 같은 case에 대한 재생성은 **덮어쓰지 않고 새 job/artifact**를 만든다
- 프론트: 보고서 생성 버튼 → 진행 표시 → 완료 시 다운로드. `canUseBackend` 가드로 publicDemo=true에서 fetch 0회 회귀(publicDemo=false 양성 대조군 포함)

**신규 의존성:** `openpyxl`. `pyproject.toml` 본 dependencies에 추가(로컬 OCR처럼 optional이 아님 — 보고서는 기본 기능)

**안 만드는 것**

- 산출물 삭제/만료 경로 (보존 정책 미승인)
- Redis 큐, DLQ, 재시도 정책 (P6-6에서 다룸)
- Raw Data 호환 시트 (P6-2)

**검증**

- `make check` exit 0
- 신규: `make p6-report-check` — 결정론적 바이트 재현성(같은 스냅샷 → 같은 SHA-256), 출처 이원화 양방향 회귀, Idempotency 동시성(승자 201/패자 409/재생 byte-identical), 다운로드 감사 기록, 미승인 case 생성 거부
- P2/P3 PostgreSQL 회귀 유지

**위험**

- `openpyxl`은 기본적으로 생성 시각을 파일 메타에 넣어 바이트가 매번 달라진다. **워크북 메타의 created/modified를 고정**해야 재현성 계약이 성립한다. 이걸 놓치면 digest 테스트가 flaky해진다
- Job 상태 전이 경쟁: 동일 job을 두 요청이 동시에 실행하지 않도록 행 잠금 필요. 기존 `with_for_update()` 패턴 재사용

---

### P6-2 — LOT 추적 · 월별/공급사 통계 · 통계 화면 · Raw Data 엑셀

**목표:** REP-001, REP-003, REP-004, UI-005.

**만드는 것**

- P6-1의 `ReportRunner` 위에 생성기 3종 추가. 신규 테이블 없음(job kind만 확장)
- **REP-003 LOT 추적 보고서**: PRD §16.3 MVP 항목. 분할 입고 포함. 생산 LOT/ERP 연계 컬럼은 **seam만 두고 비움**(FR-REP-003 "자동 ERP 비범위")
- **REP-004 월별·공급사별 품질 통계**: PRD §16.4 11개 지표. 부적합률, 평균 처리기간, COA 누락률, OCR 검토 필요율, 자체검사 완료율 등
- **UI-005 통계 화면**: 승인 완료 건만 집계. **테스트/취소 건 제외**를 쿼리 수준에서 강제하고 회귀로 고정
- **REP-001 Raw Data 엑셀**: `Raw_Data`(기존 호환) / `Measurements_Long` / `Documents` / `Audit`(선택) 4시트. **기존 템플릿 열 수를 초과해도 잘라내지 않음**을 회귀로 고정

**Raw Data 열 구조 확보 절차 (AP-05 준수)**

저장소 폴더에 실제 양식 `수입검사성적서_Raw_Data.xlsx`가 존재한다. P0A/P0B에서 승인받아 쓴 절차와 동일하게 처리한다.

1. 실제 파일에서 **열 구조(헤더 이름·순서·개수)만** 읽는다
2. 값은 읽지 않고, 마스킹된 합성 fixture를 생성한다
3. **실 파일은 커밋하지 않는다.** `scripts/check_sensitive_documents.py`가 계속 이를 강제한다
4. 생성한 fixture는 `scripts/scan_secrets.py`의 `APPROVED_FIXTURES`에 SHA-256과 함께 등재한다
5. 열 구조 추출 결과는 `docs/evidence/`에 집계 형태로 기록한다

**주의:** 이 절차는 열 구조 호환성만 확보한다. **샘플 데이터의 대표성이나 QUALITY 승인을 뜻하지 않는다.**

**검증**

- `make p6-report-check` 확장: 3개 생성기 각각의 재현성, 통계 기간 경계(월 시작/끝, UTC vs KST), 테스트/취소 제외 양방향 회귀, 열 무절단 회귀
- 통계 쿼리는 NFR-PERF 대상이므로 데이터셋 프로파일과 측정 환경을 함께 기록

**위험**

- 통계 기간 경계와 타임존이 가장 흔한 오류 지점이다. DB는 UTC로 저장하고 사용자는 KST로 본다. **월 경계를 어느 타임존으로 자를지 명시적으로 결정하고 테스트로 고정**한다
- 제외 규칙("테스트/취소 건")의 정의가 코드 여러 곳에 흩어지면 통계와 화면이 어긋난다. 단일 쿼리 헬퍼로 국소화한다

---

### P6-3 — 부적합 후속조치

**목표:** PRD Phase 2 "부적합 후속조치". P5의 `nonconformances` 위에 확장한다.

**만드는 것**

- 마이그레이션 `20260811_0009`: 후속조치 실행 이력 테이블(append-only)
  - 어떤 조치를, 누가, 언제, 어떤 결과로 수행했는지
  - 완료 처리와 그 근거 문서 링크(기존 `documents` 재사용, P5 첨부 패턴 승계)
  - APPROVED NCR 불변성 트리거와 정합하게: 후속조치 이력은 NCR 본문을 변경하지 않는다
- API: 후속조치 등록/조회/완료. LEAD 권한 강제는 `require_role` + DB CHECK 이중(AP-04)
- 기한 관리: **입력받은 목표 완료일**을 저장하고 경과 여부를 표시한다
- UI: NCR 상세에 후속조치 타임라인

**안 만드는 것**

- **severity 기준, 목표 완료일 산정 공식, 처리방안 자동 선택 규칙.** 전부 QUALITY 정책이다. P5 NCR 스키마 설계에서 동일한 판단을 이미 내렸고 이를 승계한다
- 알림/에스컬레이션 (PRD Phase 4)

**검증**

- 신규 db/api 테스트. APPROVED NCR에 후속조치를 추가해도 NCR 본문이 불변임을 회귀로 고정
- `_is_domain_invariant_violation` 헬퍼 재사용으로 `P0001`만 409 매핑

---

### P6-4 — NAS/Google Drive 수집 준비

**목표:** FR-DOC-001, FR-DOC-002, FR-DOC-005. §2.3의 4조건을 만족하는 seam.

**만드는 것**

- 마이그레이션: 수집 커서/이력 테이블 1개. 어디까지 훑었는지와 안정화 대기 중인 항목을 담는다. **중복 차단은 신규 테이블 없이 기존 `documents`의 SHA-256 경로를 재사용한다**
- `SourceAdapter` 포트: 목록 조회, 열기, 메타(크기·수정시각). NAS와 Drive가 같은 포트를 구현할 수 있는 모양
- `LocalDirectorySourceAdapter`: 합성 구현체. 로컬 임시 디렉터리를 소스로 쓴다
- **파일 안정화(FR-DOC-002)**: 복사 중인 파일을 받지 않는다. 크기·수정시각이 N초간 변하지 않아야 확정. 부분 파일·쓰기 중 파일·사라진 파일을 fail closed로 처리
- 수집 파이프라인: 발견 → 안정화 대기 → SHA-256 계산 → **기존 `documents` 중복 차단 재사용**(FR-DOC-004) → 등록
- **Storage mirror(FR-DOC-005)**: primary 성공 + mirror 실패 시 동작을 명시적으로 결정하고 테스트로 고정. AP-06 미승인이므로 **실제 미러 대상은 로컬 합성 경로만**
- Feature flag: 기본 **off**. off 상태에서 감시 스레드가 시작조차 되지 않음을 테스트로 고정

**안 만드는 것**

- 실제 NAS/Drive 클라이언트, 자격증명 설정, 네트워크 호출. **어댑터 인터페이스만 남긴다**
- 자동 재시도/DLQ (P6-6)

**검증**

- 신규 `make p6-ingest-check`: 안정화 대기(부분 파일 → 대기 → 완성 → 수집), 중복 차단, mirror 실패 처리, feature-off 무동작
- 네트워크 호출 0회를 테스트에서 단언

**위험**

- 파일 안정화는 타이밍 의존이라 flaky해지기 쉽다. **실제 sleep이 아니라 주입 가능한 clock**으로 구현해야 결정론적이다

---

### P6-5 — 마스터 Import 준비

**목표:** PRD Phase 2 "마스터 Import". 품목·공급사·모델 대량 등록.

**만드는 것**

- 마이그레이션 `20260811_0010`: import 배치 이력 + 행 단위 결과(append-only)
- 흐름: 엑셀 업로드 → **열 검증** → **미리보기(dry-run)** → 확인 → 적용 → **되돌리기**
  - 미리보기는 신규/변경/무시/오류를 행 단위로 보여준다
  - 적용은 단일 트랜잭션. 부분 적용을 남기지 않는다
  - 되돌리기는 배치 단위. 기존 soft delete/`lock_version` 낙관적 잠금과 정합
- 합성 견본 엑셀을 코드로 생성해 fixture로 사용
- Feature flag 기본 off

**안 만드는 것**

- **실 엑셀 파일 커밋** (AP-05)
- 자동 적용. **미리보기 확인 없는 적용 경로를 만들지 않는다** — P5 마스터 데이터의 `If-Match` 낙관적 잠금과 코드 중복 거부 불변식을 우회하지 않아야 한다

**검증**

- 신규 `make p6-import-check`: 열 누락/여분/순서 변경, 중복 코드, nullable 코드 의미(다중 NULL 허용/중복 non-null 거부) 유지, 부분 실패 시 전체 롤백, 되돌리기 후 원상복구

**위험**

- Import가 P5에서 DB로 강제한 마스터 불변식을 우회할 수 있다. **Import 경로도 동일한 서비스 계층을 지나가게** 하고, 우회 불가를 회귀로 고정한다

---

### P6-6 — OCR 운영 모니터링

**목표:** PRD Phase 2 "OCR 운영 모니터링", NFR-AVAIL status.

**만드는 것**

- 지표 수집: 처리 건수, 사람 검토 전환율, 실패 사유 코드별 집계, 처리 소요 시간 분포, 네이티브 텍스트 vs OCR 비율. **신규 지표 테이블을 만들지 않고 기존 extraction/document 행에서 집계한다** — 별도 저장은 원본과 어긋날 여지를 만들고, 지금은 그 비용을 치를 데이터 규모가 아니다
- 조회 API + 화면
- NFR-AVAIL 일부: 실패한 추출 작업의 **상태 노출과 수동 재시도**. 자동 재시도/DLQ는 큐 도입 시점으로 미룬다
- P6-4가 있으면 수집 파이프라인 지표도 같은 화면에 붙인다

**안 만드는 것**

- **KPI 임계값, 합격/불합격 판정, 알림.** §1.3 참조. 화면에 "목표: 95%" 같은 문구를 넣지 않는다
- 자동 재시도/DLQ

**검증**

- 지표 집계의 결정론성, 기간 경계, 임계값 식별자가 코드에 존재하지 않음을 구조적으로 단언(P5 feature flag 테스트가 쓴 방식)

---

### P6-7 — 백업/복구

**목표:** BACKUP-001. 이 조각만은 합성이 아니라 지금 그대로 진짜로 동작한다.

**만드는 것**

- `scripts/backup.sh`: DB 논리 백업 + 파일 저장소 백업
- `scripts/restore-verify.sh`: **일회성 disposable DB에 복원한 뒤 행 수와 해시 매니페스트를 원본과 자동 대조.** 복원이 실제로 되는지 증명하지 못하는 백업은 백업이 아니다
- 복구 절차 문서

**안 만드는 것**

- production DB 대상 실행, 스케줄러 등록, RPO/RTO 수치 확정(AP-08)

**검증**

- 신규 `make p6-backup-restore-verify`: disposable Compose에서 백업 → 복원 → 매니페스트 대조. Docker 잔여 0/0/0

---

## 6. 반드시 보존해야 할 불변식

P5 인계 문서 §6을 승계하며 P6에서 특히 위험한 지점을 덧붙인다.

- OCR/추출 결과는 후보이며 사람 확인 전 확정 금지. 누락·미매핑·저신뢰·internal incomplete는 fail closed
- 별칭은 후보 추천 전용. 전역 승격은 FR-MAP-003 승인 전까지 금지이며 스키마에 여지를 만들지 않는다
- 승인 권한은 LEAD, ADMIN은 비승인권(AP-04)
- finalized evidence와 APPROVED 부적합은 DB에서 불변. disposition 마스터는 DELETE 불가
- 모듈 feature flag로 위 불변식을 끌 수 없다
- 공개 Vercel 데모는 frontend-only 합성 경계
- **(P6 신규)** 보고서는 판정값을 **읽기만** 한다. 보고서 생성이 검사·판정·승인 상태를 변경하는 경로를 만들지 않는다
- **(P6 신규)** Import와 수집은 P2/P5가 DB로 강제한 마스터·문서 불변식을 **우회하지 않는다.** 동일 서비스 계층을 지난다
- **(P6 신규)** 수집·Import·모니터링 플래그가 off일 때 **부수효과 0**

---

## 7. 환경·운영 주의사항

P5 인계 문서 §7을 그대로 승계한다.

- `make p3-e2e`는 이 체크아웃 경로에 비ASCII 문자가 있어 Docker bake가 실패한다. `COMPOSE_BAKE=false make p3-e2e`로 실행
- `make p4-local-ocr-preflight`는 모델 아티팩트 부재로 `LOCAL_OCR_MODEL_MISSING` fail closed가 정상. 실행에는 `make local-ocr-bootstrap` 필요
- `contracts/openapi.json` 재생성 시 `frontend/src/lib/api/generated.ts`도 함께 재생성해야 `make contracts-check` 통과. **P6는 API를 크게 늘리므로 이 실수가 잦을 것이다**
- `scripts/scan_secrets.py`의 `APPROVED_FIXTURES` 파일 수정 시 SHA-256 갱신 필수
- 도메인 불변식은 마이그레이션 23곳에서 `RAISE EXCEPTION`(SQLSTATE `P0001`)으로 강제된다. 광범위한 `DBAPIError`를 409로 매핑하지 말 것. `routes/nonconformances.py`의 `_is_domain_invariant_violation` 재사용
- 여러 에이전트 CLI가 하나의 worktree를 공유하면 위험하다. 이 저장소에서 실제로 두 차례 승인된 작업이 파괴됐다

---

## 8. 계속 금지

실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP **실제 호출**, 실 PDF/XLSX 커밋, production/비일회성 migration, production DB-role activation, 보존 기간·삭제 규칙 생성, OCR KPI 임계값 생성, release·production readiness 선언.

이 계획 문서 자체는 commit/push/merge/deploy 권한을 부여하지 않는다.

---

## 9. 다음 단계

1. 이 문서를 사용자가 검토한다
2. 승인 후 `writing-plans`로 P6-1의 실행 계획(작업 단위·TDD 순서·검증 명령)을 작성한다
3. P6-1 구현 → 게이트 통과 → 독립 검토 → 전달
4. 조각마다 위를 반복한다. **조각 사이에 KANBAN/매트릭스/DEVLOG를 동기화한다**
