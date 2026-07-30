# KANBAN — 한양화학 v0

> 정본 실행 보드는 Hermes Kanban `hanyang-chemical-v0`이다. 이 문서는 프로젝트 내 사람이 읽을 수 있는 mirror다.

## 현재 작업

|Card|상태|내용|완료 조건|
|---|---|---|---|
|`t_7d493a1e`|Completed|PRD 기반 독립 계획 2개 비교·통합·문서화|Opus 5 증빙 확인, 비교표/통합 계획/전수 추적, Alfred R1 formal+substantive PASS, DEVLOG/링크 검증 완료|
|`t_715483aa`|Completed|P0B correction candidate final independent review/acceptance|P0A/P0B complete·accepted, final independent `APPROVE` 확인|

## 검증 결과

- Claude Code canonical model: `claude-opus-5`, `is_error=false`
- Alfred 1차 findings: HIGH 3건·MEDIUM 2건, 총 5건을 보정했고 R1에서 모두 `RESOLVED`
- Alfred R1: 신규 HIGH/MEDIUM blocker 0, `substantive_plan_assessment: PASS`
- P0B second remediation: independent re-review의 HIGH 1건·MEDIUM 3건(OOXML/OPC semantic validation, every-`.rels` validation, all-member CRC/decompression, source-digest provenance binding)을 synthetic regression coverage로 보정했으며 재검토/controller acceptance 대기
- P0B third focused remediation: MEDIUM Content-Type-driven OPC member validation 및 complete Relationship element semantics, LOW root-level relationship-source compatibility를 synthetic-only regression으로 보정했다. `pytest -q`는 2026-07-31에 `94 passed in 4.41s`; final QA/controller acceptance 대기 상태는 변함없다.
- P0B fourth focused remediation: MEDIUM full RFC 3986 Relationship-Type lexical validation 및 canonical OPC member/Override/relationship-Target lexical validation, LOW attribute-free `Relationships` root hardening을 synthetic-only regression으로 보정했다. 서로 다른 typed relationship ID의 동일 target은 OPC 호환성을 위해 허용하며 duplicate ID만 거부한다. `pytest -q`는 2026-07-31에 `127 passed in 5.90s`였다.
- P0B final independent review: 67 in-memory probes, HIGH 0, MEDIUM 0, `APPROVE`. generic scheme-specific URI semantics의 LOW lexical-contract note는 소비 relationship role이 exact allowlist를 사용하므로 defense-in-depth로 수용됐다.
- Controller evidence: `127 passed`; approved real QM301 dry-run 38 templates/119 rows, discrepancy 0, DB write/apply 0; source hash/size/mtime unchanged; tracked sensitive documents 0.
- 구현 상태: `P0A_P0B_COMPLETE_ACCEPTED; P1_AUTHORIZED_READY_NOT_STARTED; P2_AUTHORIZED_AFTER_P1_CONTRACT_GATE_NOT_STARTED`

## 승인 현황

|Gate|결정|상태|
|---|---|---|
|AP-01|사내망 Docker Compose·공개 배포 없음|승인|
|AP-02|외부 OCR/AI 기본 OFF 및 향후 opt-in 절차|승인|
|AP-03|canonical LOT + inbound allocation 데이터 모델|승인|
|AP-04|Local Auth/RBAC 및 ADMIN 비승인권|승인|
|AP-05|실 PDF/XLSX Git 커밋 금지·마스킹 fixture 정책|승인|
|Implementation|P0A/P0B/P1/P2|P0A/P0B complete·accepted; P1 authorized/ready, not started; P2 authorized after P1 contract gate, not started|
|Still prohibited|실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포/서비스 공개|미승인|

## 실행 Backlog

1. P0A read-only evidence freeze — Completed, source immutable PASS
2. P0B evidence tooling/fixture bootstrap와 ADR — Completed/accepted
3. P1 Repository/Contract foundation — Authorized and ready; not started
4. P2 Pure domain + DB invariants — Authorized after P1 contract gate; not started
5. P3 Fixture 기반 첫 수직 Slice
6. P4 OCR Golden/Provider benchmark
7. P5 Core MVP
8. P6 수집/운영/Pilot

P1은 authorized and ready지만 아직 시작하지 않았다. P2는 P1 contract gate 전에는 시작하지 않는다. 실데이터 apply/import, 외부 OCR/AI, 비일회성 migration, 배포와 서비스 공개는 시작하지 않는다.
