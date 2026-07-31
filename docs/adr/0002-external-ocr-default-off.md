# ADR 0002: External OCR and AI are off by default

**Status:** Accepted (AP-02, 2026-07-30)

## Decision

External OCR and AI transmission is disabled by default. OCR or LLM output is a review candidate only and can never make a final quality decision.

## Consequences

P0B tooling defaults to synthetic masked fixtures only and makes no external OCR/AI calls. Separately, the controller performed an approved local real-source **dry-run** evidenced at [`../evidence/2026-07-31-p0b-controller-real-dry-run.json`](../evidence/2026-07-31-p0b-controller-real-dry-run.json): it was read-only, made no external transmission, performed no apply or database write, and did not change the source. This narrow controller-only exception does not change the synthetic-only default or authorize real-data apply/import. Provider activation requires a later provider-specific opt-in after retention, training use, region, contract, and approved de-identified fixture review gates.

## Rollback and exceptions

Rollback is immediate provider disablement with existing candidates held for human review. An exception requires explicit authorized product, security, and operations approval; the exception cannot authorize external transmission of real source evidence by implication.
