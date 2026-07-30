# 한양화학 v0 — 수입검사 디지털화 및 LOT 추적

현재 저장소는 수입검사 업무의 원본 보존, OCR 후보 검토, 한양화학 기준 판정, 검사자 제출·팀장 승인, LOT 추적을 디지털화하기 위한 신규 프로젝트다. AP-01~05는 승인됐고 P0A와 P0B는 complete/accepted다. P1은 authorized and ready지만 아직 시작·완료되지 않았고, P2는 P1 contract gate 후에만 authorized다.

## 현재 상태

- 정본 요구사항: [`Prd.md`](./Prd.md)
- 통합 구현 계획: [`docs/plans/2026-07-30-integrated-implementation-plan.md`](./docs/plans/2026-07-30-integrated-implementation-plan.md)
- Hermes 독립 계획: [`docs/plans/2026-07-30-hermes-independent-plan.md`](./docs/plans/2026-07-30-hermes-independent-plan.md)
- Claude Code Opus 5 독립 계획: [`docs/plans/2026-07-30-claude-opus5-independent-plan.md`](./docs/plans/2026-07-30-claude-opus5-independent-plan.md)
- 요구사항 추적 정본: [`docs/TRACEABILITY_MATRIX.md`](./docs/TRACEABILITY_MATRIX.md)
- 독립 계획 QA: [`docs/reviews/2026-07-30-integrated-plan-alfred-qa.md`](./docs/reviews/2026-07-30-integrated-plan-alfred-qa.md) — formal/substantive PASS
- P0A read-only evidence freeze: [`docs/evidence/2026-07-30-p0a-evidence-freeze.md`](./docs/evidence/2026-07-30-p0a-evidence-freeze.md) — source immutable PASS
- P0B final independent review: `APPROVE` — 67 in-memory probes, HIGH 0, MEDIUM 0; one accepted LOW generic scheme-specific URI-semantics note is defense-in-depth because consumed relationship roles use exact allowlists
- 구현 상태: `P0A_P0B_COMPLETE_ACCEPTED; P1_AUTHORIZED_READY_NOT_STARTED; P2_AUTHORIZED_AFTER_P1_CONTRACT_GATE_NOT_STARTED`

## 핵심 안전 원칙

1. OCR/LLM은 추출 후보만 만든다.
2. 최종 판정은 Decimal 기반 결정론적 엔진과 사람 승인으로만 확정한다.
3. 공급사 규격/판정과 한양화학 기준/판정을 분리한다.
4. 검사 생성 당시 기준 버전과 승인 Snapshot을 불변 보존한다.
5. 누락·미매핑·저신뢰·자체검사 미완은 fail-closed(`ON_HOLD`)다.
6. AP-05에 따라 현재 PDF/XLSX 실원본은 계속 Git 커밋·외부 전송 금지 대상으로 취급한다.

## 다음 게이트

P1은 시작할 준비가 됐지만 아직 구현을 시작하지 않았다. P2는 P1 contract gate를 통과하기 전까지 시작하지 않는다. 실데이터 apply/import, 외부 OCR/AI 호출, 비일회성 migration, 배포 및 서비스 공개는 계속 미승인이다.

## 작업 기록

- [`docs/DEVLOG.md`](./docs/DEVLOG.md)
- [`docs/KANBAN.md`](./docs/KANBAN.md)
