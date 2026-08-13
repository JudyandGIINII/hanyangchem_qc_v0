# 한양화학 v0 인계 문서 — 1차 개발 MVP 종료

## 2026-08-13 1차 MVP 종료 및 재개 조건 (현행 인계 문서)

이 섹션이 현재 인계 상태의 정본이다. 아래 P5 이하 섹션은 각 증분의 역사적 증거로 계속 유효하며 이 섹션이 그것을 무효화하지 않는다.

### 1. 결론

**1차 개발 MVP를 종료한다.** 엔지니어링으로 더 진행할 수 있는 항목이 남지 않았다. 남은 전 항목은 **승인 또는 실물 부재**로 막혀 있으며 코드 부채가 아니다.

**추가 개발은 두 가지가 확보된 뒤에 재개한다.**

1. **시험 샘플(COA 등) 확보** — OCR 품질 기준선 측정과 P4-B 대표 코퍼스에 필요하다
2. **NAS / Google Drive 접속 확인** — 수집 seam에 실제 어댑터를 붙이는 데 필요하다

두 조건이 갖춰지기 전에는 아래 §6의 금지가 그대로 유지된다.

### 2. 이번 MVP 증분 범위

`59ad9c9`(P6 승인·계획) 이후 `ff98896`까지 **9개 커밋, 87개 파일, +9816/−58**. 전부 `origin/main`에 non-force fast-forward로 전달됐고 병합 커밋이나 rebase는 없다.

|증분|내용|
|---|---|
|P6-1|보고서 공통 틀(Job·산출물 불변성) + 통합 검사보고서|
|P6-2|Raw Data 엑셀 · 월별/공급사 통계 · 통계 화면|
|P6-3|부적합 후속조치 append-only 이력|
|P6-4|NAS/Drive 수집 seam|
|P6-5|마스터 Import (미리보기→적용→되돌리기)|
|P6-6|OCR 운영 모니터링|
|P6-7|백업/복구와 복원 리허설|
|P7|추적성 seam (BOM · 생산 LOT · 영향 범위)|

### 3. 최종 검증 상태

최종 트리(`ff98896`) 기준.

|게이트|결과|
|---|---|
|`make check`|**exit 0** (Ruff, strict mypy **104 files/0 errors**, backend **779 passed/191 deselected**, frontend Vitest **78/11 files** + Next production build, migration contract 4, secret·sensitive scans, Compose)|
|`make p2-postgres-check`|**27**|
|`make p3-postgres-check`|**147**|
|`make p6-report-check`|**41**|
|`make p3-e2e` (Playwright)|**3/3**|
|`make p6-backup-restore-verify`|매니페스트 diff 통과|
|`make p4-golden-check` / `p4-preflight-check`|**199 / 97 — 불변**|
|HYC Docker 잔여|**0/0/0** (사용자 소유 n8n만 running, untouched)|

P4 수치가 전 증분에서 한 번도 변하지 않은 것이 P4 경계를 침범하지 않았다는 증거다.

### 4. 설계상 확정되어 되돌리면 안 되는 결정

- **보고서 바이트 재현성.** openpyxl이 xlsx zip 멤버마다 현재 시각을 박으므로 아카이브를 고정 타임스탬프로 재작성한다. 같은 검사가 초마다 다른 파일이 되면 "그때 받은 그 파일"을 증명할 수 없다
- **보고서 출처 이원화.** 판정값은 `decision_snapshots`에서만 읽고 명칭·COA 메타·부적합·첨부는 조회 시점 값을 쓰되 각 시트 1행에 출처를 렌더한다. 스냅샷 스키마는 확장하지 않는다 — `APPROVAL_SNAPSHOT_REQUIRED_KEYS` 변경은 기존 `content_hash` 계약을 깨고, **부적합은 승인 이후 발생하는 사후 사건**이라 승인 스냅샷에 얼리는 것이 모델링상 틀리다
- **승인된 부적합은 불변.** 그래서 후속조치 완료는 NCR 행 수정이 아니라 append-only 이력에 기록한다. 행 수정으로 구현하면 런타임에 `P0001`을 맞는다
- **통계 모집단.** `decision_snapshots` 행이 있는 승인 완료 건만, `CANCELLED` 제외. 월 경계는 Asia/Seoul
- **통계 기간은 SQL로 밀어 넣는다.** 기간 없이 전체 이력을 적재하면 검사가 쌓일수록 제곱으로 느려진다(실제로 P3 게이트가 32초 → 600초 초과로 악화된 적 있음)
- **화면과 엑셀은 단일 집계 엔진을 공유한다.** 두 곳에서 따로 집계하면 품질팀 앞에서 숫자가 갈라진다
- **Import는 미리보기 없이 적용할 수 없다.** 거부 행이 하나라도 있으면 전량 미적용
- **추적성 순회는 순환에서 종료한다.** 실제 BOM은 입력 오류로 순환이 생기고, 고객 이슈 대응 중 무한 루프에 빠지는 영향 분석은 제한된 결과보다 나쁘다
- **seam은 플래그 off일 때 부수효과가 0이다.** 수집·추적성 모두 off에서 테이블을 읽지도 않는다

### 5. 값을 만들지 않고 부재를 명시한 항목

근거 없는 숫자를 만드는 것보다 못 잰다고 말하는 편이 낫다는 원칙을 적용한 지점이다.

|항목|처리|사유|
|---|---|---|
|OCR 품질 KPI 임계값|`kpi_thresholds: null` + 사유 문구|PRD §3.3이 초기 운영 데이터로 기준선 측정을 요구. COA 샘플 없음|
|OCR 운영 지표 무관측|`0%`가 아니라 `관측 없음`|"검토 안 됨"과 "추출이 없음"은 다른 주장|
|PRD §12.5 테스트 데이터 제외|미구현 + 쿼리 헬퍼에 갭 주석|스키마에 테스트 레코드 식별 표시가 없어 제외 불가|
|부적합 severity·목표일 산정|미구현|QUALITY 정책|
|Import UPDATE 되돌리기|생성분만 되돌리고 한계 명시|이전 값을 기록하지 않으므로 추측 복원은 더 나쁨|

### 6. 재개 전까지 계속 금지

실데이터 apply/import, 외부 OCR/AI/**NAS/Drive/ERP 실제 호출**, 실 PDF/XLSX 커밋(AP-05), 보존기간·만료·삭제 규칙(RET-001/AP-08), OCR KPI 임계값, 비일회성·production migration, production DB-role activation, release·production readiness 선언.

이 인계 문서 자체는 어떤 승인 권한도 부여하지 않는다.

### 7. 재개 시 착수 지점

**시험 샘플이 확보되면**

1. `docs/approvals/P4B_QUALITY_CORPUS_DECISION_PACKET.md`를 완성하고 QUALITY 승인자를 지정한다
2. human-label과 독립 검토 증거를 확보한다(현재 후보 4건 / 적격 0건)
3. 기준선을 측정한 뒤에만 OCR KPI 임계값을 설정한다. `hyc_api/reports/ocr_operations.py`가 임계값 상수 도입 시 실패하는 구조적 가드를 갖고 있으므로 그 가드도 함께 갱신해야 한다
4. P5 잔여 5행(FR-SPEC-003/007, FR-MAP-003, FR-OCR-001, FR-INT-003)의 판정·샘플 정책을 확정한다

**NAS / Google Drive 접속이 확인되면**

1. `backend/src/hyc_ingest/ports.py`의 `SourceAdapter`를 구현하는 실 어댑터를 추가한다. `LocalDirectorySourceAdapter`가 참조 구현이다
2. 접속 정보를 설정으로 주입하고 수집 플래그를 켠다. 파이프라인·안정화·중복차단은 이미 있다
3. AP-06(mirror)과 AP-01 경계를 재확인한다

**둘 다 무관하게 가능한 것**

- REP-001 산출물을 품질팀에 보여주고 `QUALITY sample approval`을 받는다. 열 구조 호환성은 이미 확보돼 있다
- 매트릭스 인용 경로 전수 검증(§8 참조)

### 8. 인계받는 사람이 알아야 할 함정

이번 작업에서 **실제로 발생한** 것만 적는다.

- **매트릭스가 존재하지 않는 테스트를 인용한 사례가 3건 있었다** — P5의 `test_internal_results_api.py`, FR-MST-006의 `test_erp_bom_seam.py`, REP-003의 `test_production_lot_link_seam.py`. 세 건 모두 "구현 완료"로 기록돼 있었다. **매트릭스의 근거 경로는 실재를 확인하기 전까지 신뢰하지 말 것.** 남은 행의 전수 검증은 아직 하지 않았다
- **단위 테스트에 `pytest.mark.postgres`를 붙이면 어디에서도 실행되지 않는다.** `make check`는 `-m "not postgres"`로 제외하고, postgres 게이트는 `integration/`만 대상으로 한다. 이 실수가 4번 발생했다. `backend/tests/unit/`의 fixture는 DSN이 없으면 sqlite로 폴백하므로 마커가 불필요하다
- **워커 CLI가 존재하지 않는 산출물을 구체적 수치와 함께 완료 보고한 사례가 2건 있었다.** 전사는 응답의 증거일 뿐 산출물이 아니다. 파일 존재와 게이트 수치 증가로 직접 확인할 것
- **`make p3-e2e`는 `COMPOSE_BAKE=false`로 더 이상 통과하지 않는다.** 저장소 경로의 비ASCII 문자가 buildx 세션 키를 깨므로 **`COMPOSE_BAKE=0 DOCKER_BUILDKIT=0`**이 필요하다
- **`contracts/openapi.json` 재생성 시 `frontend/src/lib/api/generated.ts`도 함께 재생성**해야 `make contracts-check`가 통과한다
- **`check_migrations.py`는 head 리비전·예상 테이블 집합·트리거 목록을 고정**한다. 신규 마이그레이션은 셋 다 갱신해야 한다
- **`hyc_domain`은 인프라 import가 금지**다. xlsx 파서를 거기 두려다 `test_domain_has_no_infrastructure_imports`에 걸린 적이 있다
- **`StrictNumeric` 컬럼 집합이 계약으로 고정**돼 있어 신규 Decimal 컬럼은 명시 등재해야 한다
- **여러 에이전트가 한 worktree를 공유하면 위험하다.** 이 저장소에서 실제로 두 차례 `git checkout`으로 승인된 작업이 파괴됐다. 파일을 겹치지 않게 나누고 브리프에서 Git 상태 변경을 금지할 것
- **`make p4-local-ocr-preflight`는 모델 아티팩트 부재로 `LOCAL_OCR_MODEL_MISSING` fail closed가 정상**이다. 실행에는 `make local-ocr-bootstrap`이 필요하다

### 9. 공개 데모 경계

`https://hanyangchemqc.vercel.app` (최종 `dpl_AMAChWZGvEW8qpoEQFzJzZEaVYxf`)는 **frontend-only 합성 경계**다. `NEXT_PUBLIC_HYC_PUBLIC_DEMO=1`로 빌드되며 backend·DB·worker·OCR·모델·원본 문서는 사내망 전용이다.

Root Directory와 Framework Preset은 대시보드 상태라 커밋 파일로 고정할 수 없다. **잘못 설정되면 localhost-fetch 모드로 되돌아갈 수 있으므로**, 향후 배포는 라이브 HTML에서 `합성 로컬 상태` 존재와 `검사 생성 전`·`SESSION_READY`·`127.0.0.1`·`P3 API 실행 제어` 부재를 매번 확인할 것.

---

## 2026-08-10 P5 종료 및 P6 handoff (이전 증분, 역사적 증거)

이 섹션이 현재 인계 상태의 정본이다. 아래 P4 이하 섹션은 해당 증분의 역사적 증거로 계속 유효하며 이 섹션이 그것을 무효화하지 않는다.

### 1. P5 결론

**P5 Core MVP는 완료되지 않았다.** 매트릭스 기준 21개 `P5` 태그 행 중 12행이 구현됐고, 남은 5행은 전부 QUALITY/AP-02 승인 대기다. 남은 항목은 코드 부채가 아니라 **사람의 품질 판단이 필요한 승인 게이트**이며, 엔지니어링만으로는 더 진행할 수 없다.

전달 커밋은 `ad5b4a1`, `88c89e0`, `f54688f`, `bdd5c98`, `251d417`, `9a1d5fb`이며 전부 `origin/main`에 non-force fast-forward로 전달됐다. 범위 분류는 [`plans/2026-08-10-p5-core-mvp-scope-plan.md`](plans/2026-08-10-p5-core-mvp-scope-plan.md), NCR 스키마 설계는 [`plans/2026-08-10-p5-ncr-module-schema-design.md`](plans/2026-08-10-p5-ncr-module-schema-design.md)에 있다.

### 2. 구현 완료 (12행)

|FR|내용|근거|
|---|---|---|
|FR-MST-001/002/003|품목·공급업체·모델 마스터|P2 테이블 위에 `routes/masters.py` API 추가. 신규 테이블·마이그레이션 없음|
|FR-MST-004|품목-공급사-모델 매핑|`spec_profiles`의 optional scope를 `test_supplier_material_model_scope.py`로 고정|
|FR-MST-005|nullable 코드/후속 업데이트|다중 NULL 허용, 중복 non-null insert/update 거부를 3개 엔티티 파라미터화 회귀로 고정|
|FR-SPEC-002|Draft/Active 기준 버전·적용일|`routes/specs.py`의 activate/retire 전이. profile당 ACTIVE 1건을 행 잠금 + 경쟁 행 `FOR UPDATE`로 동시성 하에서 보장|
|FR-NCR-001|처리방안|`nonconformance_dispositions`. PRD 명시 6종 seed, DELETE 거부 트리거로 과거 기록 보존|
|FR-NCR-002|부적합 기록/승인/기한/증빙|`nonconformances` + 승인/첨부 테이블, API, UI. APPROVED 불변성 트리거|
|FR-NCR-004|모듈 Feature Flag|5개 모듈 플래그. 32개 조합 전수 회귀로 불변식 비활성 불가를 증명|
|FR-MAP-001|표준 항목 별칭|scope + priority. 전역 승격 컬럼을 의도적으로 만들지 않음|
|FR-APR-003|반려/사유/재제출|append-only 이력 테이블. `reason TEXT NOT NULL`로 필수 사유를 DB가 강제|
|FR-INT-006|사진/시험기록 증빙|`documents` 재사용 링크 테이블로 저장 계층 충족|

FR-NCR-003 재검사 연결은 P2/P3의 `inspection_cases` lineage로 이미 충족되어 신규 작업이 없었다.

### 3. 미완료 (5행) — 전부 승인 게이트

|FR|내용|대기 중인 승인|
|---|---|---|
|FR-SPEC-003|표준 검사항목|QUALITY review|
|FR-SPEC-007|샘플 계산/판정 정책|항목 정책 QUALITY 승인|
|FR-MAP-003|학습형 별칭 운영|QUALITY approval|
|FR-OCR-001|정확도 우선 파이프라인|AP-02 + QUALITY benchmark. P4-B/P4-C에 연쇄 종속|
|FR-INT-003|가변 샘플|FR-SPEC-007과 동일 게이트|

이 다섯은 **판정 임계값과 샘플링 규칙**을 확정해야 진행 가능하다. 실제 입고 검사 합부 판정에 쓰이는 값이므로 구현자가 임의로 만들면 안 되며, 그래서 의도적으로 비워 두었다. `SamplePolicy`는 이미 6종 StrEnum으로 존재하므로 **메커니즘은 있고 품목별 정책 배정만 없다**.

### 4. 승인 현황 — 착수조차 안 된 상태

|항목|상태|
|---|---|
|AP-01 ~ AP-05|승인 완료. 단 AP-02는 "절차" 승인이며 특정 Provider 승인이 아니다|
|P4-B QUALITY 코퍼스 패킷|`PENDING / NOT APPROVED`, PENDING 필드 **49개**, `Named QUALITY approver` 미지정|
|P4-C Provider AP-02 패킷|`PENDING / NOT APPROVED`, PENDING 필드 **60개**, 승인자 미지정|
|로컬 코퍼스|후보 문서 4건 / **적격 0건** (human-label 증거와 독립 검토 증거 부재)|

병목은 승인 절차가 막힌 것이 아니라 **승인에 올릴 재료가 없는 것**이다. 순서는 QUALITY 승인자 지정 → 코퍼스 확보와 human-label → 항목별 판정·샘플 정책 확정이다.

### 5. P6 착수 가능 여부

P6는 KANBAN의 "수집/운영/Pilot"이며 PRD `Phase 2: Operations`에 해당한다. 항목별로 성격이 다르므로 그대로 착수하면 안 된다.

|P6 항목|상태|근거|
|---|---|---|
|Feature Flag|**이미 완료**|FR-NCR-004로 5개 모듈 플래그와 불변식 보호가 구현됨. 재작업 불필요|
|부적합 후속조치|**착수 가능**|NCR 스키마·API·UI가 이미 있어 그 위에 확장하면 된다. 새 승인 불필요|
|Raw Data / 통합 보고서 / 통계|**착수 가능**|기존 합성 데이터 위에서 구현 가능. 새 승인 불필요|
|OCR 운영 모니터링|**부분 착수 가능**|로컬 OCR 파이프라인과 preflight가 이미 있어 관측·지표 수집은 가능하다. 단 KPI 임계값 판정은 FR-OCR-005 KPI가 미승인이므로 임계값을 만들지 말 것|
|마스터 Import|**금지**|실데이터 apply/import는 계속 미승인. AP-05의 실 PDF/XLSX 정책도 유효|
|NAS / Google Drive 자동 수집|**금지**|외부 NAS/Drive/ERP 호출은 계속 미승인. 별도 승인 없이는 착수 불가|

**P5 미완료 5행이 P6 착수를 막지는 않는다.** 다만 FR-OCR-001이 미승인이므로 OCR 품질 KPI를 P6에서 확정된 것처럼 다루면 안 된다.

### 6. P6가 반드시 보존해야 할 불변식

- OCR/추출 결과는 후보일 뿐이며 사람 확인 전 확정 금지. 누락·미매핑·저신뢰·internal incomplete는 fail closed
- 별칭은 후보 추천 전용이며 매칭을 자동 확정하지 않는다. 전역 승격은 FR-MAP-003 승인 전까지 금지이며 스키마에 그 여지를 만들지 말 것
- 승인 권한은 LEAD이며 ADMIN은 비승인권(AP-04). NCR 승인도 DB CHECK와 API 403 이중으로 강제됨
- finalized evidence와 APPROVED 부적합은 DB에서 불변. disposition 마스터는 DELETE 불가이며 비활성화만 가능
- 모듈 feature flag로 위 불변식을 끌 수 없다. 플래그는 `module_exposure.py`의 노출 계층에 격리되어 있고 32개 조합 회귀가 이를 지킨다
- 공개 Vercel 데모는 frontend-only 합성 경계이며 backend/DB/worker/OCR/모델/원본 문서는 사내망 전용이다

### 7. P6 착수 전 알아야 할 환경·운영 사실

- `make p3-e2e`는 이 체크아웃 경로에 비ASCII 문자가 있어 Docker bake가 실패한다. **2026-08-12 확인: `COMPOSE_BAKE=false`는 더 이상 듣지 않는다.** 실패 메시지 `x-docker-expose-session-sharedkey contains value with non-printable ASCII characters`는 buildx가 경로에서 세션 키를 만들면서 발생하므로 BuildKit 자체를 꺼야 한다. **`COMPOSE_BAKE=0 DOCKER_BUILDKIT=0 make p3-e2e`로 실행하면 통과한다**(이 조합으로 Playwright 3/3 확인). 환경 제약이며 코드 결함이 아니다
- `make p4-local-ocr-preflight`는 모델 아티팩트가 부트스트랩되지 않아 `LOCAL_OCR_MODEL_MISSING`으로 **정상적으로 fail closed** 된다. 실제 실행에는 `make local-ocr-bootstrap`이 필요하며 이는 모델 아카이브를 내려받는다
- `contracts/openapi.json`을 재생성하면 `frontend/src/lib/api/generated.ts`도 함께 재생성해야 `make contracts-check`가 통과한다
- `scripts/scan_secrets.py`의 `APPROVED_FIXTURES`에 등재된 파일을 수정하면 SHA-256 다이제스트를 갱신해야 한다. 갱신 없이 커밋하면 `make check`가 깨진다
- 이 저장소는 도메인 불변식을 마이그레이션 23곳에서 `RAISE EXCEPTION`으로 강제하며 PostgreSQL이 여기에 SQLSTATE `P0001`을 부여한다. 광범위한 `DBAPIError`를 통째로 409로 매핑하면 연결 끊김·타임아웃 같은 인프라 장애가 업무 충돌로 위장되어 무의미한 재시도를 유발하고 장애를 은폐한다. `routes/nonconformances.py`의 `_is_domain_invariant_violation` 헬퍼를 재사용해 `P0001`만 409로 좁힐 것
- 여러 에이전트 CLI가 하나의 worktree를 공유하면 위험하다. 이 저장소에서 실제로 두 차례 `git checkout`/`restore`로 승인된 작업이 파괴됐다. 워커별 worktree를 분리하거나 브리프에서 Git 상태 변경을 금지할 것

### 8. 계속 금지

실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP 호출, production/비일회성 migration, production DB-role activation, release·production readiness 선언. 이 인계 문서 자체는 어떤 승인 권한도 부여하지 않는다.

### 9. 최종 검증 상태

최종 트리(`9a1d5fb`) 기준 `make check` exit 0 (Ruff, strict mypy 77 files/0 errors, backend `705 passed, 160 deselected`, frontend Vitest `61 passed`/8 files 및 Next production build, migration contract 4, scans, Compose), `make p2-postgres-check` 18, `make p3-postgres-check` 125, `make p4-golden-check` 199, `make p4-preflight-check` 97, Docker 잔여 0/0/0. Playwright E2E는 이번 P5 증분에서 재실행하지 않았다.

---

# P4 local-only OCR accepted delivery handoff (이전 증분, 역사적 증거)

## 2026-08-03 active handoff

- The authorized local-only low-quality PDF OCR engineering lane is complete, independently accepted, committed, fresh-`origin/main` fast-forward integrated, and delivered. Source/integration baseline is `91fd4a8229b12d2b229f2ef9abb9dceef93591b5` (`feat: add local-only low-quality PDF OCR`). Pre-closure main baseline `96413d20230b62033ecb754a12e5a1a621a7b95c` is its later descendant; the commit containing this documentation closure will be newer, and Git history is authoritative for its exact SHA/remote-tip state.
- All OCR output is a candidate with `review_required=true`; missing/low-confidence/conflicting/table-layout results fail closed. Runtime network, credentials, endpoints, model auto-download, external Provider fallback, and automatic final decisions are prohibited.
- Final post-remediation generated-synthetic PaddleOCR smoke passed with output digest `581ed7dad0973c3a999ce6e1b48bc9368452e5f6f9aab3fdc3e8c1fbe72437c1`, aggregate digest `6545119c4a18c2e788024521a3e77fbdd38b4fc902a01900063d79327b1c6a9c`, field/physical-line header/numeric/public-provider review exposure `1.0000/1.0000/1.0000`, and initialization/prediction network attempts `0/0`.
- Final independent Claude review returned `ACCEPT_WITH_MINOR` at BLOCKER/MAJOR/MINOR/NOTE `0/0/4/8`. It confirmed B1/M1-M9 and MA-1 closed. The four bounded minors remain: broad/over-inclusive native table detection; native low-confidence evaluator wiring exercised only through a fake backend because production native lines are confidence 1.00; no expensive smoke rerun inside the independent review after final native remediation, although the later Hermes final-source run produced the digests above; and duplicate native word extraction per native page.
- Final-tree evidence: backend `641 passed, 92 deselected`, strict mypy 67, frontend Vitest 32/build, P4 golden 198, P4 preflight 97, local preflight focused/runtime 43 plus real engine initialization, migration 4, contracts, scans, and Compose passed. Final `make check` exited 0 after documentation sync.
- Readiness failure caching is fail-closed and restart-required. Ordinary CI deliberately does not require model binaries; exact local runtime/model validation remains a separate mandatory `make p4-local-ocr-preflight` gate.
- Active local-only P4 engineering is complete. If representative real-corpus validation is desired, the next boundary is P4-B QUALITY corpus approval and missing human-label/independent-review evidence; this is a validation gate, not code debt. Otherwise the work may hand off to the next separately approved phase. P4-C external Provider work is deferred/not required for local-only scope; no account or approval request is active.
- Public synthetic-demo remediation `96413d2…` preserves local API behavior when `NEXT_PUBLIC_HYC_PUBLIC_DEMO` is absent and blocks backend calls/server persistence when it is exactly `1`. Its independent review was `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 6): a static approval assertion is vacuous; no runtime fetch-spy/effect coverage exists; source-slicing tests are formatting-brittle; public status copy can remain server-oriented; no committed `vercel.json`/`.vercelignore` pins the flag or Root Directory; and root `.env.example` does not feed the Compose web image build. These residuals are not fixed. Controller frontend verification was 36 passed plus build. Verified 2026-08-03 KST production evidence is Vercel `hanyangchem_qc` deployment `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y`, `READY` at `https://hanyangchem-739r15g9t-judy-ng-ii-nii-s-projects.vercel.app` with alias `https://hanyangchemqc.vercel.app` and `sourceCommit=cf6d6327172fb09da0fe0e3b12159f6596553c41`. Next.js 15.5.22 completed compile/lint/type validity, five static routes and `/api/health` in 57s; root HTTP 200 and health `{"status":"ready"}` passed. Alias browser QA found the public boundary/title, no `Failed to fetch`, no localhost resources, alias-only resources, zero console messages/errors, and only local synthetic approval on team-lead interaction. Production/Preview flags are saved. This proves only that exact synthetic frontend boundary; backend, DB, worker, OCR, models, and original documents remain local/intranet-only. Future missing/incorrect flag/configuration can still fall back to localhost-fetch mode and must repeat deployment-API/browser verification. The later documentation commit is docs-only with `frontend/` unchanged from `cf6d632…`, so no rebuild is required solely for unchanged frontend bytes; Git history is authoritative for its tip. The reviewer ran Vitest 36, `tsc`, and `eslint`, not a build or Playwright.
- The complete design, evidence, limitations, setup distinction, and prohibitions are in [`research/2026-08-03-local-only-low-quality-pdf-ocr.md`](research/2026-08-03-local-only-low-quality-pdf-ocr.md).

## 2026-08-09 previously undocumented delivered commits

The three commits below are already on `origin/main` but were absent from this handoff and from `KANBAN.md`. They are recorded here as delivered history; no new approval is claimed.

- `faee4d9` (`feat: add human-reviewed local OCR dashboard flow`), 31 files, +4107/−221. It adds `backend/src/hyc_api/document_locks.py` (`DigestOwnershipGuard`: 256 in-process lock stripes plus a PostgreSQL session-level advisory lock on a dedicated checked-out connection, keyed only on a `[0-9a-f]{64}` SHA-256 digest so ownership does not depend on mutable storage paths), the `POST/GET/PUT /api/v1/documents/{document_id}/extractions[/{run_id}]` surface, and `frontend/src/lib/inspection/ocr-review.ts`. Human review stays mandatory: every field requires a reason and a final string, and `local-paddleocr` runs additionally require an explicit `MAP`/`UNMAPPED` disposition where `UNMAPPED` forbids a target field key. Test files added include `test_local_ocr_dashboard_api.py`, `test_local_ocr_dashboard.py`, `test_document_stable_guard.py`, `test_document_locks.py`, and `ocr-review.test.ts`.
- `1a25665` and `42c6123` change only `.github/workflows/ci.yml`: `uv sync … --extra local-ocr` and `fonts-noto-cjk`. Verified in this increment: `backend/tests/local_ocr/test_runtime_components.py` (marker `local_ocr_runtime`) constructs only `RecordingOcrEngine` and never `PaddleOcrEngine`, so CI still requires no model binaries and makes no network call. The line 10 statement above therefore remains true; CI runs `pytest -q -m "not postgres"`, which does not deselect `local_ocr_runtime`.

## 2026-08-09/10 residual-minor follow-up increment (committed, not integrated)

This increment closes disclosed minors only. It is committed on the candidate branch `JudyandGIINII/p4-residual-minors-20260810` as a source commit plus this documentation commit; it is **not fast-forward integrated into `main` and not pushed to `origin/main`**. Git history is authoritative for the exact SHAs and for the remote tip, which remained `42c6123306a9ac9af9ada829481a4a900c69f0e6` at capture time. It grants no P4-B/P4-C, corpus, deployment, or production approval, and it did not deploy, run any Vercel CLI command, contact any external service, download models, build any image, or use any real PDF/XLS/XLSX.

- Local-only OCR minors, in `backend/src/hyc_local_ocr/pdf_backend.py`. **Closed:** duplicate native word extraction — `page.get_text("words", sort=True)` is now called once per page and shared by `_native_lines` and `_native_table_suspected`. **Closed:** over-inclusive native table detection — row cells are now derived by collapsing words separated by less than a 12.0pt `_MIN_COLUMN_GUTTER_POINTS` gutter, so ordinary single-spaced aligned prose no longer counts each word as a column. `test_native_table_signal_requires_wide_cell_gutters` pins both directions and asserts the prose fixture really does contain three-word rows (max gap < 8.0pt) so it cannot pass vacuously, while the wide-gutter table fixture (min gap ≥ 12.0pt) still returns `True`. **Substantiated, not newly covered:** the native low-confidence evaluator path — `test_real_native_backend_has_no_low_confidence_signal_for_the_evaluator` records that the real native backend always yields `Decimal("1.00")` and never emits `LOW_CONFIDENCE`, which is why a fake backend remains the only way to exercise that wiring. **Unchanged:** the independent-review-time smoke non-rerun is a process note, not code.
- Public synthetic-demo minors, all six now addressed. **Closed:** the vacuous static approval assertion and the absent runtime coverage — `frontend/tests/public-demo.test.tsx` now runs under `// @vitest-environment happy-dom` and mounts the component, asserting zero `fetch` calls across bootstrap, stage navigation, `LEAD`/`ADMIN` role switching, and the synthetic approval action when `publicDemo=true`. Its `publicDemo=false` control asserts `fetch` *is* called against `/api/v1/local-auth/sessions` on bootstrap and on role switch, which is what makes the zero-fetch assertion meaningful rather than a silent no-mount. Element lookups are guarded by `expect(...).not.toBeNull()` so a missing selector fails instead of skipping; the synthetic-approval click remains conditionally guarded and is the one step that could still skip silently. **Closed:** the formatting-brittle source-slicing assertions were replaced by those behavioral assertions. **Closed:** public status copy — `workflowStatus` previously rendered the server-oriented `검사 생성 전 · …` in public demo because `inspection` is always null there; it now renders `합성 로컬 상태 · …` when `publicDemo` is true, with the local-API branch and its raw `inspection.status` suffix unchanged. The regression is folded into the existing render tests rather than added as a separate case: public markup must contain `합성 로컬 상태` and must not contain `검사 생성 전`, `SESSION_READY`, or the raw `DRAFT`/`LEAD_REVIEW`/`READY_FOR_REVIEW`/`ACCEPTED`/`REJECTED` enum names, while the local-API test asserts `검사 생성 전` and `SESSION_READY` are still present, so the pair proves a real difference rather than passing vacuously. **Closed:** `.env.example` now reaches the Compose web image — `compose.yaml`'s `web.build` passes `NEXT_PUBLIC_HYC_PUBLIC_DEMO: ${NEXT_PUBLIC_HYC_PUBLIC_DEMO:-0}` as a build arg and `frontend/Dockerfile` declares `ARG NEXT_PUBLIC_HYC_PUBLIC_DEMO=0` plus a matching `ENV` after `COPY frontend ./` and before `RUN pnpm build`, which is required because Next.js inlines `NEXT_PUBLIC_*` at build time. The default is deliberately `0`: Compose is the local intranet stack that must keep talking to the real backend, so only an explicit operator override selects demo mode. `backend/tests/contract/test_public_demo_build_contract.py` pins the wiring, the `0` default, and the `ARG`/`ENV`-before-build ordering. **Partially closed:** committed `vercel.json` and `frontend/vercel.json` pin `NEXT_PUBLIC_HYC_PUBLIC_DEMO=1` at build time and committed `.vercelignore`/`frontend/.vercelignore` exclude `backend/`, `docs/`, `docker/`, `compose.yaml`, `scripts/`, `Makefile`, `*.pdf`, `*.xlsx`, `*.xls`, and `.local-ocr-models/`; Root Directory and Framework Preset remain dashboard-only settings that `vercel.json` cannot express, so they are documented in [`VERCEL_PUBLIC_DEMO.md`](VERCEL_PUBLIC_DEMO.md) instead. Both a root and a `frontend/` copy of each file are committed because which one applies depends on the dashboard Root Directory.
- Note the two opposite, intentional defaults: Compose defaults to `0` (local stack keeps its backend) and Vercel pins `1` (any public build is a disconnected demo). Together they make the previously warned localhost-fetch fallback harder to reach, but they do not eliminate it, because Root Directory and Framework Preset are still dashboard state.
- Increment verification, re-run by the controller on the final working tree rather than quoted from a worker: backend `pytest -q -m "not postgres"` **688 passed, 125 deselected**, Ruff clean, strict mypy **53 source files, 0 errors**, frontend Vitest **43 passed across 5 files**, frontend lint/typecheck/production build pass, `pnpm install --frozen-lockfile` passes, `docker compose config --quiet` passes, and the secret and sensitive-document scans pass. Full `make check`, the PostgreSQL suites, Playwright, and the local OCR preflight were **not** run for this increment, and no container image was built. Those remaining gates, a fresh `origin/main` fast-forward check, and delivery are the next controller steps and are not claimed here.
- The delivered `96413d2…` review record above is retained verbatim as historical evidence. Its `ACCEPT_WITH_MINOR` BLOCKER 0 / MAJOR 0 / MINOR 6 verdict, its capture-time deployment/browser proof, and its warning that a missing or incorrect flag can still fall back to localhost-fetch mode all remain valid; this increment closes the code-level residuals but does not re-verify that deployment.

## 2026-08-10 delivery and public demo redeployment

- Delivered. The candidate was fast-forwarded onto fresh `origin/main` baseline `42c6123306a9ac9af9ada829481a4a900c69f0e6` with no merge commit or rebase and pushed non-force as `42c6123..f9a6995`, then `f9a6995..290e7b5`. At capture time local `main`, `origin/main`, and `git ls-remote origin refs/heads/main` all equaled `290e7b580f6fe1ebb9c0840bf472c9f56622f32b`, and the baseline is an ancestor of `origin/main`.
- Full gate run on the delivered tree: `make check` exit 0 (Ruff, strict mypy 68 source files, backend 671 passed/142 deselected, frontend Vitest 43/5 files plus production build, migration contract 4, secret and sensitive-document scans, `docker compose config`); `make p2-postgres-check` 10; `make p3-postgres-check` 115; `make p3-e2e` Playwright **3/3**; `make p4-golden-check` 199; `make p4-preflight-check` 97. Disposable Docker containers/networks/volumes ended at 0/0/0.
- `make p3-e2e` first failed with a Docker bake error (`x-docker-expose-session-sharedkey contains value with non-printable ASCII characters`) because the repository path contains non-ASCII characters. It is an environment limitation, not a code defect, and passes with `COMPOSE_BAKE=false`. Use `COMPOSE_BAKE=false make p3-e2e` on this checkout.
- `make p4-local-ocr-preflight` correctly **fails closed** with `{"error_code": "LOCAL_OCR_MODEL_MISSING", "status": "BLOCKED"}` because no local model artifacts are bootstrapped here. This is the documented gate behavior, not a regression; running it for real requires `make local-ocr-bootstrap`, which downloads model archives and was deliberately not performed.
- Public synthetic demo redeployed to production at explicit user request. Deployment `dpl_ER31Q8WjXup6Khuewsj5AmJ7hacr`, target production, `READY`, at `https://hanyangchem-7xca4t6bx-judy-ng-ii-nii-s-projects.vercel.app`; alias `https://hanyangchemqc.vercel.app` now resolves to it, superseding `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y` and the later `dpl_BbT5ADzDifuLv1KpLniU5ULrfkaW`. It was CLI-deployed from inside `frontend/` on a clean working tree at `290e7b5`, so only `frontend/` was uploaded and `frontend/vercel.json` and `frontend/.vercelignore` are the copies that took effect.
- Live boundary evidence: root HTTP 200 and `/api/health` `{"status":"ready"}`. The served HTML contains `합성 로컬 상태`, `공개 합성 데모`, `서버 연결 없음`, and `공개 합성 데모 경계`, and contains zero occurrences of `검사 생성 전`, `실제 서버 상태`, `SESSION_READY`, `P3 API 실행 제어`, `127.0.0.1`, or a `localhost` port. Because `합성 로컬 상태` renders only when `publicDemo` is true, its presence is direct end-to-end proof that the committed `vercel.json` build-flag pin took effect and that the status-copy fix shipped. A real browser session recorded **zero non-static network requests** (7 static) — no API or backend call of any kind — and one console error, a `favicon.ico` 404 that is pre-existing and unrelated: no favicon or `public/` directory has ever existed in Git history. The earlier record's raw-deployment-URL comparison is not meaningful because unaliased deployment URLs return 302 deployment protection on every path.
- This proves only that synthetic frontend boundary at that exact deployment. Backend, DB, worker, OCR, models, and original documents remain local/intranet-only. Root Directory and Framework Preset are still dashboard state that no committed file can pin, so a future misconfiguration can still fall back to localhost-fetch mode and must be re-verified the same way.

The historical accepted/delivered P4-A and preflight record below remains authoritative for those increments. This local-only delivery does not grant P4-B/P4-C, representative-corpus quality, external Provider, deployment, or production approval.

## 현재 handoff

- Authoritative P4 plan and acceptance record: [`plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md`](plans/2026-08-02-p4-ocr-golden-provider-benchmark-kickoff.md).
- P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442` remains accepted, fresh-main fast-forward integrated, and delivered to `origin/main`.
- P4-A Offline/Synthetic is complete, independently accepted, committed, fresh-main fast-forward integrated, and delivered to `origin/main` at source/integration baseline `aeedceb2c3b7008439a9c72e3984be77f6135e51` (`feat: complete P4-A offline synthetic evaluator`). That commit is a direct descendant of `2d5c02dbc612f9b612f27a36263b95e842c24e75`.
- Final controller QA passed. The fresh independent read-only review of the final 25-path candidate returned `ACCEPT_WITH_MINOR` (BLOCKER 0, MAJOR 0, MINOR 3); it recomputed unchanged before/after-review digests for the 16-path source-only set (`0d5c259f59293f35e4cf6b83ffff13820c3c07194f5db48e54d8c8b1d09db632`) and 25-path full candidate (`ba938518beca8f3718abdf4eb44430e26b3a775aea8f8b33dc5dc01937218f23`). The latter is capture-time accepted-candidate evidence, not the digest of the commit containing this nine-file closure.
- A fresh Orca integration worktree was created from fetched `origin/main` at baseline `2d5c02d…`. `git merge --ff-only aeedceb…` succeeded without a merge commit or rebase; non-force `git push origin HEAD:main` succeeded. At capture time integration HEAD, `origin/main`, and `git ls-remote origin refs/heads/main` all equaled `aeedceb…`; baseline/source ancestry and clean implementation/integration worktrees were verified.
- The commit containing this nine-file documentation closure is a newer descendant of `aeedceb…`; Git history is authoritative for its exact SHA and remote-tip status. `aeedceb…` remains the P4-A source/integration baseline, not the continuing tip.
- Post-integration documentation commits `1d98e4cf17b37e0ea95eadcbe69418778d1a614f` and `afe58a0fe556e8ae94b11926dd572ef9b2e60ee5` are historical ancestors after `aeedceb…`.
- The pre-P4-B four-path maintenance increment was independently accepted with final `VERDICT: ACCEPT` (blocker 0, major 0, minor 0). Its exact review-freeze digest remained `7ed91a678ba1dd72c30f7e9b58d5e5066fdcf41f8cde2b9da8239447345a85ce` before and after review.
- Maintenance source/delivery commit `cad1ab48b7ab1923638fe8600f23ef640efdab73` (`fix: stabilize P4-A geometry validation`) is the direct child of `afe58a0…`. A fresh `origin/main` fast-forward and non-force delivery succeeded. At capture time local integration HEAD, `origin/main`, and `git ls-remote` main all equaled `cad1ab4…`; ancestry and clean integration status passed. Git history is authoritative for the exact SHA and remote-tip state of any later documentation-only descendant.
- The maintenance closes the former schema Decimal-context and dead internal polygon-counter notes. Polygon validation arithmetic is pinned to precision 28 / `ROUND_HALF_EVEN`; public `missing_polygon_count` and `invalid_polygon_count` remain Literal-zero compatible. Strict required geometry and fail-closed invalid-geometry behavior remain unchanged.
- Fail-closed P4 preflight source/delivery commit `fce19681f75cac8f95bb6cde95ad50351cf9e309` (`feat: add fail-closed P4 preflight contracts`) directly descends from fresh `origin/main` baseline `4866f7a992cd8e40dc95b43b1b2adaa13d989752`. Independent Agy/Gemini reviews returned `ACCEPT` with blocker/major/minor 0/0/0. Final evidence was preflight 97 passed, golden 192, Ruff, strict mypy 52/0, backend 607 passed/77 deselected, frontend Vitest 32/build, migration contract 4, scans, and Compose.
- Fresh `origin/main` ff-only integration and non-force push of `fce19681…` succeeded. At capture time integration HEAD, `origin/main`, and remote main were equal to `fce19681…`. This is accepted/delivered offline/local preflight contract evidence only; it is not P4-B/P4-C/full-P4 completion.
- The [P4-C public-source due-diligence note](research/2026-08-02-p4c-ocr-provider-due-diligence.md) recommends Azure AI Document Intelligence `prebuilt-layout` / REST `2024-11-30` / Korea Central as the first research candidate only. It is `NOT SELECTED / NOT APPROVED`; no account, endpoint, credential, Provider call, legal approval, or AP-02 approval exists in this record.
- Private local inventory is aggregate-only: 4 candidate documents and 0 eligible because neither human-label evidence nor independent-review evidence is present. The set is non-representative and is not a QUALITY corpus.
- No real representative corpus, external Provider/OCR/AI, credential, network call, real PDF/XLS/XLSX, deployment, migration, DB/API/frontend/service change, or production activation was used.

## Lane decisions

|Lane|Status|What the next session may do|
|---|---|---|
|P4-A — Offline/Synthetic foundation|`COMPLETE_ACCEPTED_DELIVERED_TO_ORIGIN_MAIN`|Preserve original source/integration baseline `aeedceb…`, maintenance delivery `cad1ab4…`, and their capture-time evidence; do not expand the synthetic-only scope.|
|P4 local-only OCR|`COMPLETE_ACCEPTED_COMMITTED_FRESH_MAIN_FF_INTEGRATED_DELIVERED_TO_ORIGIN_MAIN`|Preserve source/integration baseline `91fd4a8…`, final review `ACCEPT_WITH_MINOR` 0/0/4 with 8 notes, final controller evidence, and the local-only boundary.|
|P4-B — Approved corpus benchmark|`BLOCKED_QUALITY_CORPUS_APPROVAL` / future validation gate|If representative real-corpus validation is desired, complete the [`P4-B QUALITY packet`](approvals/P4B_QUALITY_CORPUS_DECISION_PACKET.md) and supply human-label plus independent-review evidence before any run. This is not unfinished code debt.|
|P4-C — External Provider benchmark/selection|`BLOCKED_AP02_PROVIDER_OPT_IN` / deferred, not required for local-only scope|Only if a future external Provider is separately requested, complete a [`P4-C Provider-specific AP-02 packet`](approvals/P4C_PROVIDER_AP02_DECISION_PACKET.md) before any call. No account request is active.|

P4-B approval does not unlock P4-C, and P4-C approval does not establish corpus representativeness. CI remains fixture-provider-only, network-free, and credential-free. Missing KPI expands Human Review/manual fallback and never permits auto-finalization.

The delivered preflight/local OCR contracts do not change these lane decisions. P4-B remains blocked because aggregate local inventory is 4 candidate documents and 0 eligible, and the research-only Azure candidate does not satisfy any formal field in the P4-C decision packet.

## P4-A final maintenance evidence

- Strict/versioned golden, fixture, stage, candidate, report, and benchmark-output schemas with canonical JSON and Decimal/SHA-256 dataset→stage→candidate→report→output binding, exact cardinality, and order.
- Deterministic eight-stage runner with fail-closed upstream propagation, compatible stage/error states, independent stored candidate payloads, canonical warning/error ordering, rejection of every non-empty observed-warning subset when extraction is non-successful, and no warnings on failed/skipped stages.
- Nontrivial report evidence: exact fields 35/44, one page mismatch, one non-unit IoU, plus duplicate, unmapped, unapproved-normalization, value-mismatch, concave, self-intersecting, degenerate, and malformed fail-closed paths.
- Executable disjoint 20-edge matrix with exact reason binding across `CANDIDATE_ONLY`, `REVIEW_REQUIRED`, `MANUAL_FALLBACK`, and `STABLE_FAILURE`; no invented IoU threshold.
- Maintenance controller selector passed 9. `make p4-golden-check`: 192 passed. Backend gates passed Ruff, strict mypy 49 files/0 errors, pytest 510 passed/77 deselected, and compileall. Full `make check` exited 0, including frontend Vitest 32 and Next production build, migration contract 4, scans, and Compose.
- `make p4-benchmark-fixture` was repeated twice and retained the accepted output `354d7c10d7c6380c855876ef72d11148523ea12f1b346b8c5f3552ec416bfd23`, report `7b0601d2f57547db32a1c9897efa30211a14fd9ff645b2a9a4fcabf57da28933`, and fixture `05f777392052c3b29be32abe1d7852312baff966fd5ac1fdc88cc6479ae918d0` digests.
- Controller probes rejected truncated, swapped, foreign, and digest-tampered benchmark outputs; ambient precisions 12/28/50 and `ROUND_UP`, `ROUND_DOWN`, `ROUND_CEILING`, `ROUND_FLOOR`, and `ROUND_HALF_EVEN` produced identical canonical output/report bytes and digests; all 20 dispositions were bound.
- Final regression evidence also includes P2 PostgreSQL 10 and P3 PostgreSQL 67; disposable Docker containers/networks/volumes ended at 0/0/0. P3 browser E2E was not run because P4-A changes no runtime/API/UI/workflow path.
- Independent review history: the original 25-path acceptance returned `ACCEPT_WITH_MINOR` (0/0/3). The later exact four-path maintenance candidate closed the two remaining source-quality notes and returned final `VERDICT: ACCEPT` (0/0/0) with its freeze digest unchanged before/after. The original verdict and notes remain historical evidence, not live open findings.

## Safe next action

1. Preserve `91fd4a8…` as the local-only OCR source/integration baseline, `96413d2…` as its pre-closure descendant, and obtain the closure/live tip from Git history.
2. If real-corpus validation is desired, obtain P4-B QUALITY approval plus human-label and independent-review evidence before reading/running the corpus; otherwise hand off to the next separately approved phase.
3. Keep P4-C deferred. Do not request an account/credential or invoke an external Provider unless provider-specific P4-C approval is separately requested and completed.
4. The verified production artifact is `dpl_2AJpKy3L7ZLiBgEx3LRqXnxDBb7Y` at the recorded alias. For any future public synthetic deployment, preserve the frontend-only invariant; because a missing/incorrect flag can return localhost-fetch mode, verify that deployment's browser network plus live identity/behavior from deployment API.

This P4 section supersedes only section 7, “안전한 다음 단계”, in the historical P3 handoff below. All P3 scope, evidence, counts, accepted debt, delivery proof, and prohibitions remain truthful historical evidence.

# P3 delivery handoff and post-push closure (historical)

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

Historical P3 checkpoint에서는 P4/P5가 unstarted였다. 이 과거 문구는 현재 P4-A remediation 상태를 설명하는 문서 상단을 override하지 않으며, P3 source acceptance나 Git integration만으로 pilot/production 단계를 자동 시작하지 않는다는 경계는 계속 유효하다.

## 8. 금지 작업

- 이 handoff 자체를 commit/push/merge/deploy 권한으로 해석하지 않는다.
- main/shared CWD mutation, reset/restore/stash/rebase 또는 무단 Git 작업을 하지 않는다.
- 실 PDF/XLS/XLSX를 커밋·업로드·미러링·외부 전송하지 않는다.
- 실데이터 apply/import, 외부 OCR/AI/NAS/Drive/ERP 호출을 하지 않는다.
- production/non-disposable migration 또는 production DB-role activation을 하지 않는다.
- public service exposure, deployment, release, production-ready 선언을 하지 않는다.
- n8n을 중지·재시작·삭제·설정 변경하지 않는다.
