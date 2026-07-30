# KANBAN — 한양화학 v0

> 정본 실행 보드는 Hermes Kanban `hanyang-chemical-v0`이다. 이 문서는 프로젝트 내 사람이 읽을 수 있는 mirror다.

## 현재 작업

|Card|상태|내용|완료 조건|
|---|---|---|---|
|`t_7d493a1e`|Completed|PRD 기반 독립 계획 2개 비교·통합·문서화|Opus 5 증빙 확인, 비교표/통합 계획/전수 추적, Alfred R1 formal+substantive PASS, DEVLOG/링크 검증 완료|
|`t_715483aa`|In progress|AP-01~05 승인 후 P0A/P0B/P1 구현|민감 실원본 제외 baseline push, Orca orchestration 구현, 독립 QA, origin/main 통합·검증|

## 검증 결과

- Claude Code canonical model: `claude-opus-5`, `is_error=false`
- Alfred 1차 findings: HIGH 3건·MEDIUM 2건, 총 5건을 보정했고 R1에서 모두 `RESOLVED`
- Alfred R1: 신규 HIGH/MEDIUM blocker 0, `substantive_plan_assessment: PASS`
- 구현 상태: `P0A_P0B_P1_AUTHORIZED`

## 승인 현황

|Gate|결정|상태|
|---|---|---|
|AP-01|사내망 Docker Compose·공개 배포 없음|승인|
|AP-02|외부 OCR/AI 기본 OFF 및 향후 opt-in 절차|승인|
|AP-03|canonical LOT + inbound allocation 데이터 모델|승인|
|AP-04|Local Auth/RBAC 및 ADMIN 비승인권|승인|
|AP-05|실 PDF/XLSX Git 커밋 금지·마스킹 fixture 정책|승인|
|Implementation|P0A/P0B/P1 구현|승인|
|Next gate|P2, 실데이터 apply/import, 외부 OCR/AI, 배포|미승인|

## 실행 Backlog

1. P0A read-only evidence freeze
2. P0B Evidence tooling/fixture bootstrap와 ADR
3. P1 Repository/Contract foundation
4. P2 Pure domain + DB invariants — 승인 대기
5. P3 Fixture 기반 첫 수직 Slice
6. P4 OCR Golden/Provider benchmark
7. P5 Core MVP
8. P6 수집/운영/Pilot

현재 P0A/P0B/P1 구현 Card를 실행 중이다. P2 이후와 외부 시스템·실데이터·배포는 시작하지 않는다.
