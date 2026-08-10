# P5 NCR 모듈 스키마 설계 (승인됨, 구현 대기)

작성 2026-08-10. 대상: FR-NCR-001 처리방안, FR-NCR-002 부적합 기록. FR-INT-006 사진/시험기록 증빙도 첨부 링크로 함께 충족한다.

## 1. 사전 조사로 정정된 사실

FR-NCR-003 재검사 연결은 **신규 테이블이 필요하지 않다**. `inspection_cases`가 이미 `retest_of_case_id`, `correction_of_case_id`, `lineage_root_id`, `round_no`, `revision_no`, `lineage_reason`을 갖고 있고, `ck_inspection_correction_revision` CHECK와 `uq_inspection_lineage_round_revision` UNIQUE로 회차/개정 일관성이 강제된다. 이번 증분은 그 lineage를 FK로 참조만 한다.

## 2. 재사용 판단

|기존 자산|재사용|근거|
|---|---|---|
|`inspection_cases` lineage|재사용|재검사 연결이 이미 완비되어 있다|
|`documents`|재사용|SHA-256 중복 제거, `ck_documents_always_immutable`, `uq_documents_storage_key`를 이미 갖춘 검증된 불변 저장소다|
|`approvals`|재사용 불가|`ck_approval_actor_role_lead`와 `ck_approval_action`이 `LEAD`/`APPROVE`로 고정되어 있고 `inspection_case_id`가 NOT NULL이다|

## 3. 신규 테이블

### 3.1 `nonconformance_dispositions` (FR-NCR-001)

`code` UNIQUE, `name`, `active`, `sort_order`, `Versioned` 믹스인.

마이그레이션에서 PRD 명시 6종을 seed한다: 반품, 재작업, 용도변경, 폐기, 선별작업, 특채. 이 값들은 PRD에 열거된 것이므로 발명이 아니다.

"관리자가 값을 추가/비활성화할 수 있으나 과거 기록은 유지한다"는 요구를 두 가지로 보장한다. 첫째 비활성화는 `active=false`로만 가능하고 DB 레벨에서 DELETE를 거부한다. 둘째 아래의 스냅샷 컬럼을 둔다.

### 3.2 `nonconformances` (FR-NCR-002)

|컬럼|비고|
|---|---|
|`ncr_number`|UNIQUE, 부적합 번호|
|`inspection_case_id`|FK → `inspection_cases`, NOT NULL|
|`spec_item_id`|FK → `spec_items`, 부적합 항목|
|`severity`|`'MAJOR'`/`'MINOR'`/NULL. PRD가 optional로 명시|
|`quantity`|`StrictNumeric`, `CHECK quantity > 0`|
|`description`, `cause`|Text|
|`disposition_id`|FK → `nonconformance_dispositions`|
|`disposition_snapshot`|JSON. 기록 시점의 code/name 고정|
|`target_completion_date`, `completion_date`|Date|
|`status`|`DRAFT`/`SUBMITTED`/`APPROVED`/`REJECTED`/`CLOSED` CHECK|
|`retest_case_id`|FK → `inspection_cases`, nullable. 기존 lineage 재사용|
|`Versioned`|lock_version 낙관적 잠금 포함|

`disposition_snapshot`이 필요한 이유는 FK만으로는 마스터가 나중에 비활성화되거나 이름이 바뀔 때 과거 기록의 의미가 흔들리기 때문이다. P3의 `spec_snapshot` 패턴과 동일한 접근이다.

### 3.3 `nonconformance_approvals`

`nonconformance_id` FK, `actor_id`, `actor_role`, `action`, `created_at`. 승인 권한은 **LEAD로 한정**하며 기존 `approvals`와 동일하게 `CHECK actor_role = 'LEAD'`, `CHECK action IN ('APPROVE','REJECT')`로 DB에서 강제한다. AP-04의 ADMIN 비승인권 원칙과 일관된다.

### 3.4 `nonconformance_attachments`

`nonconformance_id` FK, `document_id` FK → `documents`, `UNIQUE(nonconformance_id, document_id)`. 새 파일 저장소를 만들지 않고 `documents`의 체크섬 중복 제거와 불변성을 그대로 물려받는다. 이 링크로 FR-INT-006도 충족된다.

## 4. 정책을 만들지 않는 지점

`severity`의 Major/Minor 판정 기준, `target_completion_date` 산정 규칙, 부적합 유형별 처리방안 선택 규칙은 **일절 만들지 않는다**. 전부 입력값으로만 저장한다. 판정·샘플 정책은 FR-SPEC-007의 QUALITY 게이트 소관이며 이번 증분과 무관하다.

## 5. 이번 증분에서 제외

FR-MAP-001 표준 항목 별칭은 제외한다. 마이그레이션 1회당 관심사 1개를 유지해 롤백 범위를 좁힌다. 별칭을 나중에 추가할 때는 scope 한정 컬럼만 두고 전역 승격 컬럼을 스키마에 만들지 않는다. FR-MAP-003 학습형 전역 운영이 QUALITY 승인 게이트이므로 스키마에 그 여지를 남기지 않는 편이 안전하다.

## 6. 마이그레이션 제약

리비전은 `20260801_0004`를 부모로 하는 `20260810_0005`다. `backend/tests/contract/test_migrations.py::test_historical_migrations_are_metadata_independent`가 마이그레이션의 모델 import와 metadata 호출을 금지하므로 **순수 DDL**로 작성하고, 기존 파일의 `_versioned()` 헬퍼 관례를 따른다. upgrade와 downgrade 왕복 및 autogenerate 무drift가 `make p2-postgres-check`/`p3-postgres-check`에서 통과해야 한다.

## 7. 검증

`make check`, `make p2-postgres-check`, `make p3-postgres-check`, `make p4-golden-check`, `make p4-preflight-check` 전부 통과하고 Docker 잔여가 0/0/0이어야 한다. 승인 후 불변성은 기존 finalized evidence 패턴을 따라 DB에서 거부하는 회귀로 고정한다.
