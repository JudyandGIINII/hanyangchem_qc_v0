# P2 Claude review remediation closure evidence

**Date:** 2026-08-01
**Review input:** `/tmp/hyc-p2-claude-review.md`
**Verified review SHA-256:** `57a374b41c9404dad81f7b050042fcdeff027c0d35a086a55bcda4b620d61625`
**Final-minor review input:** `/tmp/hyc-p2-fresh-final-claude-review.md`
**Verified final-minor review SHA-256:** `84266c614f67b98c559619d64034d3ea1915e780904a2f7bbdfdf9bb5d92fec7`
**Absolute-final review input:** `/tmp/hyc-p2-absolute-final-claude-review.md`
**Verified absolute-final review SHA-256:** `6a1ef045b9bbdfadb322a04819875a0b53ca2ec045bf09cfce8157918aa68848`
**Disposition:** P2 source-complete and accepted after independent Hermes QA and final Claude `PASS`; N-M3 accepted as an unfixed pre-production-privilege follow-up

## Finding closure

|Finding|Closure|Regression evidence|
|---|---|---|
|B1|AP-03 v1 key is exactly supplier+material+NFKC/trim LOT No.; production/package values are conflict evidence. Missing LOT No. is provisional. Promotion, conflict review, distinct-actor merge, bounded surviving-lot resolution, repeat/split receipt behavior, and merged allocation denial are explicit.|LOT unit/portable tests; PostgreSQL concurrent identity, dual-actor merge, same-actor denial, and merged-allocation denial.|
|B2|`ApprovalRepository.finalize` no longer accepts candidate, snapshot, or re-evaluation flags. It locks the case, checks expected version/LEAD/separation, selects the persisted ACTIVE/effective spec, reloads persisted results, runs `JudgmentEngine`, guards the transition, requires deviation reason, permits plain `ACCEPTED` only for an `ACCEPTED` candidate, builds the snapshot, then atomically flushes case+approval+audit+outbox.|Signature regression, wrong-role/ADMIN/same-actor, caller-override, DRAFT, REJECTED/ON_HOLD override, and zero-partial-mutation tests.|
|B3|Approval snapshot required fields include document hashes, engine/policy/rounding/conversion versions, approver, sample policy, LOT/allocation refs, spec/results/reasons. Null/empty required values fail; canonical deep-copy/hash is recomputed in domain, repository, and PostgreSQL.|Forged and all-null unit/PG probes plus repository snapshot assertions.|
|B4|Decimal conversion and average arithmetic use versioned 96-digit `localcontext` precision/rounding/traps. Average records pre-round/result/rounding/arithmetic version. Arithmetic failures become coded `DecimalValidationError`.|Mutated global precision/rounding regression tests and conversion audit assertions.|
|B5|Disposable app role has SELECT on all tables, DML on mutable business tables, INSERT-only on snapshot/audit/documents/approvals/merge approvals/outbox, and no UPDATE/DELETE there. Repository and DB require selected ACTIVE/effective spec; DRAFT finalization rolls back atomically.|App-role append/read/DML/privilege/denial matrix; DRAFT zero-partial test; migration roundtrip.|
|M1|LOT re-entry follows a bounded `merged_into_id` chain to a live canonical survivor; PostgreSQL blocks allocation insert/update to MERGED lots.|Portable re-entry plus PG allocation denial.|
|M2|All eight quality-bearing numeric ORM columns use `StrictNumeric`, rejecting Python float at bind time.|Column inventory and `0.1+0.2` bind rejection.|
|M3|DB CHECK allowlists cover source/missing/sample policies, case/receipt/document/link statuses, standard data type, approval role/action, and existing decision/operator/mapping states.|Invalid policy/status/rule portable constraints and migration/model drift gate.|
|M4|Operator CHECK is bidirectional; invalid rules return coded `ON_HOLD/INVALID_RULE`, never raw `ValueError`.|Invalid persisted-style rule regression.|
|M5|One centralized merge rule requires distinct LEAD quality + ADMIN master-data actors; ADMIN cannot finalize/override quality decisions.|Domain/repository/PG same-actor denial, ADMIN finalization denial, ADR 0003/0004.|
|M6|Optimistic conflicts subclass `CodedDomainError` with `STALE_VERSION`; authorization uses distinct `AUTHORIZATION_DENIED`.|Stable-code regression.|
|M7|`BOTH_ALL_MUST_PASS` with missing supplier evidence is always `ON_HOLD`, independent of missing policy/internal pass.|All-missing-policy parameter matrix.|
|M8|Every `Versioned` SQLAlchemy entity configures `version_id_col`; PostgreSQL optimistic triggers cover all 16 versioned tables. Normal ORM updates bump exactly once.|SQLite and PostgreSQL ordinary ORM update tests; direct stale-update denial.|
|M9|The deterministic transition map is keyed by current+target+role, reaches all 15 states, removes DRAFT→READY bypass, and makes document/match/supplier/internal gates reachable. INTERNAL_TEST_PENDING has no submit/approve edge.|Reachability and full role/reason/re-evaluation matrix.|
|m1|Ruff E501 is enabled; only the frozen migration and raw-SQL PostgreSQL probe file have targeted per-file E501 ignores.|Ruff full gate.|
|m2|Synthetic PostgreSQL fixture credentials are removed from the global value allowlist and approved only by exact path+SHA-256 content.|Renamed/modified/path-bound secret fixture tests and secret scan.|
|m3|`check_migrations.py` compares Alembic head to ORM metadata and requires an empty autogenerate diff on SQLite and disposable PostgreSQL.|Migration contract and PostgreSQL runner.|
|m4|Negative zero, lowercase hexadecimal SHA-256, quantity > 0, page range, and parent revision +1 policies are enforced/tested.|Unit, portable, and PG boundary tests.|
|m5|Same-person dual-role merge, every append-only table privilege denial, and MERGED allocation branches now have negative tests.|PostgreSQL suite.|
|m6|Domain import boundary recursively scans all Python modules and allows only stdlib + `hyc_domain` imports.|Domain import unit gate.|
|m7|`ON_HOLD > REJECTED > ACCEPTED` is explicitly retained as fail-closed v1 policy, documented and tested.|Judgment regression, integrated plan, traceability, and snapshot reason metadata.|

## Hermes controller-QA H1 correction

Hermes found that the B2 repository guard covered a persisted `REJECTED` candidate but
not a persisted fail-closed `ON_HOLD` candidate. The corrected guard permits plain
`ACCEPTED` only when the re-evaluated persisted engine candidate is `ACCEPTED`;
`REJECTED` and `ON_HOLD` accepting overrides require `SPECIAL_ACCEPTED` and a non-empty
reason. A portable repository regression creates a genuine `ON_HOLD` from missing
required internal evidence, proves a reason does not authorize plain `ACCEPTED`, checks
zero snapshot/approval/audit/outbox or case mutation after rollback, and then proves
reasoned `SPECIAL_ACCEPTED` succeeds.

H1 verification:

- Red phase: the focused new regression failed because plain `ACCEPTED` did not raise.
- Focused corrected approval slice: **5 passed, 37 deselected**.
- Final re-review `make check`: exit 0; Ruff passed, strict mypy passed across 28 files,
  backend **344 passed, 9 PostgreSQL deselected**, migration contract **4 passed**,
  frontend **3 files / 32 passed** plus lint/type/build, scans, and Compose rendering.
- The later final re-review remediation reran the disposable PostgreSQL suite: **9 passed**
  plus upgrade→downgrade→upgrade and empty model/migration drift.
- Final `git diff --check`, secret scan, and sensitive-document scan passed. Protected
  P0B hashes remained `61caebd0...e23` and `c0799b04...801`, byte-identical to
  `origin/main`; frontend/contracts/API/worker/fixtures remained diff-free; and the
  `hyc-p2-test-` container/network/volume cleanup inventory was empty.

## Final Claude re-review N1/N2/N3 correction

- N1: the deferred PostgreSQL finalization trigger now denies plain `ACCEPTED` for both
  `REJECTED` and `ON_HOLD` persisted candidates. The DB-direct regression failed before
  the fix (`DID NOT RAISE`), then passed while proving zero case/version/snapshot/approval/
  audit/outbox mutation and positive normal/special-acceptance controls.
- N2: nullable receipt-lot `model_id` is represented on `receipt_lot_allocations`.
  Repository and PostgreSQL selection now require the unique highest-specificity
  material/supplier/model ACTIVE/effective scope, preserve nullable fallback, exclude a
  different model, and fail closed on equal-specificity ambiguity or overlap. Four focused
  repository regressions passed.
- N3: at that re-review stage the aggregate was **344 passed, 9 PostgreSQL deselected**
  and PostgreSQL **9 passed**. Those values remain historical evidence and are superseded
  by the N-M1/N-M2 hardening measurements below.

## Fresh final review N-M1/N-M2 closure

- N-M1: immutable follow-up revision `20260801_0003` adds a PostgreSQL `BEFORE INSERT`
  guard that requires `inspection_cases.final_decision IS NULL` at creation. Frozen
  revision `20260731_0002` remains byte-identical at SHA-256
  `546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`.
  The app-role regression's red phase at `0002` was `DID NOT RAISE` after complete valid
  snapshot/approval/audit/outbox evidence; after `0003`, the same transaction is denied
  and leaves zero partial state, while a normal unfinalized insert succeeds.
- N-M2: document transitions now use a stable tuple, a map keyed by
  `(current, target, role)`, and an import-time cardinality assertion. The focused matrix
  covers all 13 existing transitions, wrong-role denial, uniqueness, and required reason.
- Claude's noted unit-coverage gap is closed by a dedicated supplier-only versus model-only
  equal-specificity ambiguity test, which fails closed for the same matching context.

At that checkpoint this remained verified candidate evidence only, pending final Hermes QA
and a fresh Claude source-diff review. The final disposition below supersedes that gate state
while preserving this review history.

## Absolute-final acceptance disposition

Independent Hermes QA remained green, and the final Claude report above returned `PASS` with
BLOCKER 0, MAJOR 0, and MINOR 1. It re-closed B1–B5, M1–M9, m1–m7, H1, N1, N2, N3, N-M1,
and N-M2 against the exact source candidate. The reproduced gates were `make check` exit 0;
backend 346 passed/10 PostgreSQL deselected; strict mypy 29 files; migration contract 4;
FE8 frontend 32 plus lint/typecheck/build; scans/Compose; PostgreSQL 10 plus
upgrade→downgrade→upgrade and empty drift; and cleanup 0/0/0. Head remains
`20260801_0003`, with frozen `20260731_0002` SHA-256
`546acd12aff2778c9ee6b6a11f8d24f87417dc8a792945f468971011a43c6f82`.

N-M3 is accepted follow-up, not fixed. A DB-direct app-role writer with broad direct
`inspection_cases` INSERT/UPDATE and all required evidence-table INSERT privileges can create
an unfinalized case already at `LEAD_REVIEW` and finalize it with complete valid evidence,
bypassing intermediate status history. N1 decision integrity, mandatory evidence, and
finalized-row immutability still hold. This defense-in-depth gap must be revisited before any
production DB-role activation.

P2 is source-complete and accepted. This does not claim commit, main integration, push,
deployment, release, operationalization, or P3 start; P3 and production/operations gates remain
blocked and unapproved.

## Commands actually run

- `shasum -a 256 /tmp/hyc-p2-fresh-final-claude-review.md` → `84266c614f67b98c559619d64034d3ea1915e780904a2f7bbdfdf9bb5d92fec7`.
- `uv lock --project backend --check` → exit 0.
- N-M1 red phase at frozen head `20260731_0002`: the new direct-finalized app-role
  INSERT test failed with `DID NOT RAISE`; the other 9 PostgreSQL tests passed.
- N-M2/equal-specificity red phase: document uniqueness failed because the keyed map did
  not yet exist, while supplier-only/model-only ambiguity already passed fail-closed;
  after implementation the focused pair passed **2 passed**.
- `make check` → exit 0:
  - Ruff passed with E501 enabled.
  - strict mypy passed across 29 source files.
  - backend pytest: **346 passed, 10 deselected**, one upstream Starlette/httpx warning.
  - migration contract: **4 passed**.
  - frontend fixture regression: **3 files / 32 passed**, lint/typegen/typecheck/build passed.
  - contract/client drift, compileall, secret scan, sensitive-document scan, and Compose render passed.
- `sh backend/scripts/run_p2_postgres_tests.sh` → exit 0: **10 passed**, then PostgreSQL upgrade→downgrade→upgrade and empty-autogenerate-diff checks passed.
- `git diff --check` → exit 0.
- P0B hashes matched `origin/main` byte-for-byte:
  - importer `61caebd06f8ee7697c77a2f3c07265e1578b10924fea6fbd74e53bd76f818e23`
  - importer dry-run test `c0799b0413f093b06de41d56f9c27b20e388cb2448ef55e39de6e78120dba801`
- Frontend/contracts/API/worker/fixtures diff probe returned empty.
- Docker cleanup inventory for names/networks/volumes matching `hyc-p2-test-` returned empty after the successful runner.

## Remediation-touched paths

- `backend/alembic/versions/20260801_0003_require_unfinalized_case_insert.py`
- `backend/alembic/versions/20260731_0002_p2_domain_invariants.py`
- `backend/pyproject.toml`
- `backend/scripts/check_migrations.py`
- `backend/src/hyc_data/models.py`
- `backend/src/hyc_data/repositories.py`
- `backend/src/hyc_domain/decimals.py`
- `backend/src/hyc_domain/errors.py`
- `backend/src/hyc_domain/judgment.py`
- `backend/src/hyc_domain/lots.py`
- `backend/src/hyc_domain/snapshots.py`
- `backend/src/hyc_domain/workflow.py`
- `backend/tests/contract/test_readiness_and_secret_scan.py`
- `backend/tests/integration/db/test_p2_portable_invariants.py`
- `backend/tests/integration/db/test_p2_postgres_invariants.py`
- `backend/tests/unit/test_decimal_boundary.py`
- `backend/tests/unit/test_domain_imports.py`
- `backend/tests/unit/test_judgment.py`
- `backend/tests/unit/test_lot_identity.py`
- `backend/tests/unit/test_snapshot_idempotency.py`
- `backend/tests/unit/test_units.py`
- `docs/DEVLOG.md`
- `docs/KANBAN.md`
- `docs/TRACEABILITY_MATRIX.md`
- `docs/adr/0003-canonical-lot-and-receipt-allocation-identity.md`
- `docs/adr/0004-local-auth-rbac-and-real-source-prohibition.md`
- `docs/plans/2026-07-30-integrated-implementation-plan.md`
- `docs/reviews/2026-08-01-p2-claude-remediation.md`
- `scripts/scan_secrets.py`

## Complete current worktree change inventory

This is the exact modified/untracked inventory at final verification. It includes the
pre-review P2 candidate paths as well as the remediation-touched paths above.

- `.github/workflows/ci.yml`
- `Makefile`
- `backend/alembic/env.py`
- `backend/alembic/versions/20260731_0002_p2_domain_invariants.py`
- `backend/pyproject.toml`
- `backend/scripts/check_migrations.py`
- `backend/scripts/p2_postgres_init.sql`
- `backend/scripts/run_p2_postgres_tests.sh`
- `backend/src/hyc_data/__init__.py`
- `backend/src/hyc_data/models.py`
- `backend/src/hyc_data/repositories.py`
- `backend/src/hyc_domain/__init__.py`
- `backend/src/hyc_domain/decimals.py`
- `backend/src/hyc_domain/errors.py`
- `backend/src/hyc_domain/idempotency.py`
- `backend/src/hyc_domain/judgment.py`
- `backend/src/hyc_domain/lots.py`
- `backend/src/hyc_domain/snapshots.py`
- `backend/src/hyc_domain/specs.py`
- `backend/src/hyc_domain/workflow.py`
- `backend/tests/contract/test_migrations.py`
- `backend/tests/contract/test_p0b_artifact_integrity.py`
- `backend/tests/contract/test_readiness_and_secret_scan.py`
- `backend/tests/integration/db/test_p2_portable_invariants.py`
- `backend/tests/integration/db/test_p2_postgres_invariants.py`
- `backend/tests/unit/test_decimal_boundary.py`
- `backend/tests/unit/test_domain_imports.py`
- `backend/tests/unit/test_judgment.py`
- `backend/tests/unit/test_lot_identity.py`
- `backend/tests/unit/test_snapshot_idempotency.py`
- `backend/tests/unit/test_spec_selection.py`
- `backend/tests/unit/test_units.py`
- `compose.p2-test.yaml`
- `docs/DEVLOG.md`
- `docs/KANBAN.md`
- `docs/TRACEABILITY_MATRIX.md`
- `docs/adr/0003-canonical-lot-and-receipt-allocation-identity.md`
- `docs/adr/0004-local-auth-rbac-and-real-source-prohibition.md`
- `docs/plans/2026-07-30-integrated-implementation-plan.md`
- `docs/reviews/2026-08-01-p2-claude-remediation.md`
- `pytest.ini`
- `scripts/scan_secrets.py`

## Boundary

No real PDF/XLS/XLSX source was opened, copied, committed, uploaded, mirrored, or transmitted. No external OCR/AI call, real-data apply/import, non-disposable migration, deployment, service exposure, or prohibited Git operation occurred. P2 is source-complete and accepted; N-M3 remains accepted follow-up, and P3 remains blocked/unapproved.
