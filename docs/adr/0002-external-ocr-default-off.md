# ADR 0002: External OCR and AI are off by default

**Status:** Accepted (AP-02, 2026-07-30)

## Decision

External OCR and AI transmission is disabled by default. OCR or LLM output is a review candidate only and can never make a final quality decision.

## Consequences

P0B uses synthetic masked fixtures only and makes no external OCR/AI calls. Provider activation requires a later provider-specific opt-in after retention, training use, region, contract, and approved de-identified fixture review gates.

## Rollback and exceptions

Rollback is immediate provider disablement with existing candidates held for human review. An exception requires explicit authorized product, security, and operations approval; the exception cannot authorize external transmission of real source evidence by implication.
