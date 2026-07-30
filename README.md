# 한양화학 v0 — 수입검사 디지털화 및 LOT 추적

현재 저장소는 수입검사 업무의 원본 보존, OCR 후보 검토, 한양화학 기준 판정, 검사자 제출·팀장 승인, LOT 추적을 디지털화하기 위한 신규 프로젝트다. AP-01~05와 P0A/P0B/P1 구현이 승인됐으며, 이후 Phase는 별도 승인 전까지 시작하지 않는다.

## 현재 상태

- 정본 요구사항: [`Prd.md`](./Prd.md)
- 통합 구현 계획: [`docs/plans/2026-07-30-integrated-implementation-plan.md`](./docs/plans/2026-07-30-integrated-implementation-plan.md)
- Hermes 독립 계획: [`docs/plans/2026-07-30-hermes-independent-plan.md`](./docs/plans/2026-07-30-hermes-independent-plan.md)
- Claude Code Opus 5 독립 계획: [`docs/plans/2026-07-30-claude-opus5-independent-plan.md`](./docs/plans/2026-07-30-claude-opus5-independent-plan.md)
- 요구사항 추적 정본: [`docs/TRACEABILITY_MATRIX.md`](./docs/TRACEABILITY_MATRIX.md)
- 독립 계획 QA: [`docs/reviews/2026-07-30-integrated-plan-alfred-qa.md`](./docs/reviews/2026-07-30-integrated-plan-alfred-qa.md) — formal/substantive PASS
- 구현 상태: `P0A_P0B_P1_AUTHORIZED`

## 핵심 안전 원칙

1. OCR/LLM은 추출 후보만 만든다.
2. 최종 판정은 Decimal 기반 결정론적 엔진과 사람 승인으로만 확정한다.
3. 공급사 규격/판정과 한양화학 기준/판정을 분리한다.
4. 검사 생성 당시 기준 버전과 승인 Snapshot을 불변 보존한다.
5. 누락·미매핑·저신뢰·자체검사 미완은 fail-closed(`ON_HOLD`)다.
6. AP-05에 따라 현재 PDF/XLSX 실원본은 계속 Git 커밋·외부 전송 금지 대상으로 취급한다.

## 다음 게이트

P0A/P0B/P1은 승인 범위 안에서 진행한다. 실데이터 apply/import, 외부 OCR/AI 호출, P2 이후 도메인·DB 구현, 비일회성 migration, 배포 및 서비스 공개는 다음 명시적 승인 전까지 시작하지 않는다.

## 작업 기록

- [`docs/DEVLOG.md`](./docs/DEVLOG.md)
- [`docs/KANBAN.md`](./docs/KANBAN.md)
