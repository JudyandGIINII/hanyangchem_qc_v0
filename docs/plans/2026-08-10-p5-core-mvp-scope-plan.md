# P5 Core MVP — scope classification and first structural slice

Status: `SCOPE_PLAN_ONLY / P5 NOT APPROVED AS A WHOLE`. Authored 2026-08-10.

P5 had no plan document. Every earlier phase has one under `docs/plans/`; P5 existed only as 21 `P5`-tagged rows in [`TRACEABILITY_MATRIX.md`](../TRACEABILITY_MATRIX.md) plus the `KANBAN.md` statement that P5 is unstarted and unapproved pending separate approval. This document supplies the missing scope classification. It does not grant P5 approval, and it does not itself authorize the approval-blocked rows below.

## 1. Why P5 cannot be completed as a single autonomous step

Four P5 rows are gated on QUALITY or AP-02 approvals that do not exist in this repository. They are precisely the rows that encode inspection policy, so implementing them would mean inventing sampling and pass/fail rules for a chemical incoming-inspection system.

|FR|Subject|Documented gate|
|---|---|---|
|FR-SPEC-003|표준 검사항목|QUALITY review|
|FR-SPEC-007|샘플 계산/판정 정책|항목 정책 QUALITY 승인|
|FR-MAP-003|학습형 별칭 운영 (승인 전 전역 금지)|QUALITY approval|
|FR-OCR-001|정확도 우선 파이프라인|AP-02 + QUALITY benchmark; depends on P4-B/P4-C, both still blocked|

These stay closed. No policy value, threshold, sampling rule, or alias-promotion rule may be invented to satisfy them.

## 2. Classification of all 21 P5-tagged rows

**Structural — implementable now.** These add API/UI surface over data structures P2 already delivered, or add mechanism without policy.

|FR|Subject|Note|
|---|---|---|
|FR-MST-001|품목 마스터|`materials` table exists; no API route exists|
|FR-MST-002|공급업체 마스터|`suppliers` table exists; no API route exists|
|FR-MST-003|모델 마스터|`material_models` table exists; no API route exists|
|FR-MST-005|nullable 코드/후속 업데이트|`*_code` columns are nullable and unique; no regression pins the semantics|
|FR-NCR-004|모듈 Feature Flag|Mechanism only; invariant guards must remain non-disableable|

**Structural but sequenced after the above.** These depend on the master-data API or on the NCR module existing.

|FR|Subject|Blocking dependency|
|---|---|---|
|FR-MST-004|품목-공급사-모델 매핑|Master-data API|
|FR-MAP-001|표준 항목 별칭|Master-data API; must stay scope-limited, never global|
|FR-SPEC-002|Draft/Active 기준 버전·적용일|Master-data API; lifecycle mechanism only, no policy|
|FR-NCR-001|처리방안|NCR module|
|FR-NCR-002|부적합 기록/승인/기한/증빙|NCR module|
|FR-NCR-003|재검사 연결|NCR module; P2/P3 lineage already exists|
|FR-INT-006|사진/시험기록 증빙|Attachment storage/audit design|
|FR-APR-003|반려/사유/재제출|Extends existing P3 approval transitions|

**Already substantially delivered by P2/P3/P4; P5 tag is incremental only.** FR-JDG-004, FR-INT-001, FR-INT-002, FR-INT-003. These need re-confirmation against the matrix rather than new construction, and FR-INT-003 (가변 샘플) touches sampling, so any behavioral change there falls under the FR-SPEC-007 gate.

## 3. First slice authorized by this plan

Only the five structural rows in the first table above, delivered in two sequenced lanes:

1. **Backend master data** — read/write API for `Supplier`, `Material`, `MaterialModel` following the existing `backend/src/hyc_api/routes/lots.py` pattern (`APIRouter(prefix="/api/v1")`, `require_principal`, `database_session`, response models in `hyc_api/contracts.py`, registration in `hyc_api/main.py`), reusing the existing `Versioned.lock_version` optimistic lock. Plus a DB-level regression pinning nullable-code semantics: several rows may hold a `NULL` code, a duplicate non-null code is rejected on insert, and an update into an existing code is rejected.
2. **Frontend master data** — a read view over that API once lane 1 is verified.

The lanes are sequenced rather than parallel because the frontend consumes the backend contract, and because both lanes would otherwise contend on `contracts.py` and `main.py`.

## 4. Non-goals

No policy invention; no real-data apply/import; no external OCR/AI/Provider, credential, or network call; no production or non-disposable migration; no production DB-role activation; no deployment or release claim. Soft-delete, audit, and existing fail-closed invariants stay intact, and no existing invariant may be placed behind a feature flag.

## 5. Verification

Each lane must pass `make check` plus the PostgreSQL suites relevant to it, and must leave disposable Docker resources at 0/0/0. Note two environment facts recorded in `HANDOFF.md`: `make p3-e2e` requires `COMPOSE_BAKE=false` on this checkout because the repository path is non-ASCII, and `make p4-local-ocr-preflight` fails closed with `LOCAL_OCR_MODEL_MISSING` because no models are bootstrapped here.

Completing this slice delivers the five structural rows only. It does not constitute P5 Core MVP completion, which additionally requires the sequenced rows and the four approval-gated rows.
