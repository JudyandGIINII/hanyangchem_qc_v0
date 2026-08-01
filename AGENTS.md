# AGENTS.md — 한양화학 v0

## Authority

- `Prd.md` is the canonical product requirement.
- `docs/plans/2026-07-30-integrated-implementation-plan.md` is the approved delivery contract through P2: P0A through P2 are complete and accepted at their source gates, while P3 remains separately gated and unauthorized.
- `docs/TRACEABILITY_MATRIX.md` is the requirement-to-phase/owner/test/gate mapping; keep it synchronized with PRD and the integrated plan.
- When the plan and PRD conflict, stop and escalate; do not silently reinterpret the PRD.

## Approval boundary

- Current state is `P0A_P0B_P1_P2_COMPLETE_ACCEPTED_P3_BLOCKED_NOT_AUTHORIZED`.
- AP-01 through AP-05 remain approved. P0A and P0B are complete and accepted. P0B final independent review returned `APPROVE` (HIGH 0, MEDIUM 0); its one LOW lexical-contract note was accepted as defense-in-depth because consumed relationship roles use exact allowlists.
- Under the user's explicit 2026-07-31 authorization, Hermes directly completed the final controller verification in place of the unavailable Claude reapproval, and the P1 contract gate passed. P1 is complete and accepted. P2 is complete, accepted, committed, fresh-main integrated, and—under separate explicit 2026-08-01 user authorization—delivered to `origin/main`: source commit `996056b` and first integration-documentation commit `58e963c` were delivered from fresh `origin/main` baseline `1e96836`. Commit `58e963c` is the verified first-push/integration-evidence commit and a durable ancestor; this post-push documentation reconciliation will be a later descendant, and Git history is authoritative for the current live tip. P3 is not authorized and remains blocked.
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
