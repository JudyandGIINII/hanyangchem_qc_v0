# AGENTS.md — 한양화학 v0

## Authority

- `Prd.md` is the canonical product requirement.
- `docs/plans/2026-07-30-integrated-implementation-plan.md` is the approved delivery contract through P3 and the phase contract for P4: P0A through P3 are complete and accepted at their source gates, P3 is committed, fresh-main fast-forward integrated, and delivered to `origin/main`, and P4-A Offline/Synthetic remediation is source complete and worker-verified but awaiting controller QA and fresh independent read-only review before acceptance/Git delivery. Git history is authoritative for the delivered live tip.
- `docs/TRACEABILITY_MATRIX.md` is the requirement-to-phase/owner/test/gate mapping; keep it synchronized with PRD and the integrated plan.
- When the plan and PRD conflict, stop and escalate; do not silently reinterpret the PRD.

## Approval boundary

- Current state is `P0A_P0B_P1_P2_P3_SOURCE_COMPLETE_ACCEPTED_P3_DELIVERED_TO_ORIGIN_MAIN_P4A_OFFLINE_SYNTHETIC_REMEDIATION_SOURCE_COMPLETE_WORKER_VERIFIED_AWAITING_CONTROLLER_QA_AND_FRESH_INDEPENDENT_REVIEW`.
- AP-01 through AP-05 remain approved. P0A and P0B are complete and accepted. P0B final independent review returned `APPROVE` (HIGH 0, MEDIUM 0); its one LOW lexical-contract note was accepted as defense-in-depth because consumed relationship roles use exact allowlists.
- Under the user's explicit 2026-07-31 authorization, Hermes directly completed the final controller verification in place of the unavailable Claude reapproval, and the P1 contract gate passed. P1 is complete and accepted. P2 is complete, accepted, committed, fresh-main integrated, and—under separate explicit 2026-08-01 user authorization—delivered to `origin/main`: source commit `996056b` and first integration-documentation commit `58e963c` were delivered from fresh `origin/main` baseline `1e96836`. Commit `58e963c` is verified first-push/integration evidence and a durable ancestor; Git history is authoritative for the current live tip. Under a later explicit 2026-08-01 authorization, P3 was implemented in this isolated worktree and passed final independent backend/UI review plus Hermes controller QA with blocker/major/medium 0. P3 source commit `91465f0413d0c0ca2633577078ec1300a6096442` (`feat: complete P3 vertical slice`; exactly 52 files, 8911 insertions, 119 deletions) was fast-forward integrated without a merge commit or rebase from clean fresh baseline `b7bc4a8ca258d1d44d240f8884a4b4ec8cbb6abf` and delivered to `origin/main`. Post-fetch local `main`, `origin/main`, and remote `main` all equal `91465f0413d0c0ca2633577078ec1300a6096442`; both baseline and source commit are ancestors of `origin/main`, and the main/candidate worktrees were verified clean immediately before this documentation-only reconciliation. Fresh integrated gates passed: bootstrap/check, Ruff, strict mypy 39, backend 346 passed/77 deselected, frontend Vitest 32 and Next production build, migration contract 4, scans/Compose, P2 PostgreSQL 10, P3 PostgreSQL 67, and real Playwright 3/3. Cleanup left HYC containers/networks/volumes at 0/0/0 and user-owned n8n untouched. This delivery does not authorize deployment, release, public exposure, real-data import/apply, external OCR/AI, production or non-disposable migration, production DB-role activation, P4/P5 start, or a production-readiness claim. Fixture-only N-1 validation ordering, N-2 GET seeding, and N-5 session eviction remain disclosed follow-ups.
- Under the user's explicit 2026-08-02 authorization, P4-A Offline/Synthetic foundation was implemented and remediated in isolated worktree `/tmp/hyc_p4a` on base HEAD `2d5c02dbc612f9b612f27a36263b95e842c24e75`. The latest remediation closes fail-closed warning evidence on non-success extraction and pins Decimal geometry/ratio precision plus `ROUND_HALF_EVEN`; worker verification passed, but these source/doc mutations invalidate the prior review, so controller QA and a fresh independent read-only review are required before the candidate can again be accepted for Git delivery. It remains uncommitted, unintegrated, and unpushed. The pre-documentation source freeze is exactly 16 paths with sorted-path+NUL+bytes+NUL SHA-256 `cf30f5c1cfad535143a0ed7fe8002e44e84ec0a67aaa9dcf15d06e32edfd5541`; later source/documentation edits change the candidate hash. Hermes/controller owns final QA/review and the already-authorized exact staging, commit, fresh-main integration/push, and ancestry verification. P4-A used only generated non-sensitive synthetic fixtures and the existing synthetic provider seam. P4-B remains independently `BLOCKED_QUALITY_CORPUS_APPROVAL`; P4-C remains independently `BLOCKED_AP02_PROVIDER_OPT_IN`. No real data, external Provider/OCR/AI, credential, network, deployment, migration, DB/API/frontend/service change, or production activation occurred.
- P2 follow-up N-M3 is accepted technical debt, not a fixed finding: an app-role DB-direct writer with broad direct case-table and evidence-table privileges can create an unfinalized case already at `LEAD_REVIEW` and then finalize it with complete valid evidence, bypassing intermediate status history. Decision integrity and evidence/immutability controls still hold; revisit this defense-in-depth gap before any production DB-role activation.
- P0B was limited to read-only evidence freeze plus derived fixture/importer dry-run tooling. Real-data apply/import, external OCR/AI calls, migration against non-disposable data, deployment, and service exposure remain unauthorized.
- A test pass or feature flag does not substitute for a product/operations approval gate.

## Data and secrets

- Treat root PDF/XLSX files as potentially sensitive, untracked source evidence.
- AP-05 is approved with a continuing prohibition: do not commit, upload, mirror, or transmit the real source files. Only local read-only inspection is allowed.
- Only approved redacted fixtures and hashes may enter Git.
- Never print or commit secrets. Use placeholders in `.env.example` and a secret store/environment at runtime.

## Required invariants

- OCR/LLM outputs candidates only; no AI final decision.
- Supplier and HYC specifications/results/decisions remain separate.
- Use Decimal/NUMERIC, never binary floating point for quality decisions.
- Freeze the effective specification and a value-complete decision snapshot at approval.
- Missing, unmapped, low-confidence, or required internal-test-incomplete cases fail closed.
- Canonical material LOT and inbound allocation are separate; no hidden 1:1 assumptions.
- Approval, audit, snapshot, idempotency, and optimistic-lock protections must be tested at API and DB boundaries.

## Coding workflow after approval

- Hermes is PM/controller and independent QA.
- Use Orca-managed isolated worktrees; Codex CLI is the primary builder.
- Claude Code is a read-only specialist for architecture/security/high-risk review unless separately authorized.
- Do not mutate main/shared CWD or run multiple mutating agents in one worktree.
- Implementation agents do not add, commit, push, merge, reset, restore, stash, rebase, or deploy.
- Work tests-first in the integrated plan's dependency order. Verify real commands before reporting completion.

## Documentation sync

After every accepted increment update the traceability matrix, relevant ADR/runbook, `docs/DEVLOG.md`, `docs/KANBAN.md`, and the Hermes Kanban card. Record commands actually run and distinguish verified results from planned commands.
