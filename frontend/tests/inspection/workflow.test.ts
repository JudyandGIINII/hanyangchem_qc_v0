import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { createInspectionFixtureState, deterministicFixtureContract, inspectionFixture } from "../../src/lib/inspection/fixtures";
import * as inspectionWorkflow from "../../src/lib/inspection/workflow";
import {
  areMatchesConfirmedForFixture,
  areRequiredTestsCompleteForFixture,
  averageDecimalStrings,
  canApprove,
  canReturn,
  canSubmit,
  deriveCanonicalTrace,
  getInternalTestSemantics,
  isCanonicalDecimalString,
  isDocumentReviewCompleteForFixture,
  isFixtureOnlyCase,
  reduceInspection,
} from "../../src/lib/inspection/workflow";
import type { InspectionFixtureState } from "../../src/lib/inspection/types";

function preflightState(): InspectionFixtureState {
  let state = createInspectionFixtureState();
  for (const field of state.documentReview.fields) {
    state = reduceInspection(state, { type: "finalizeDocumentReview", fieldId: field.id, source: "MANUAL", value: field.manualValue || field.originalValue, reason: "fixture review" });
  }
  for (const match of state.matches) state = reduceInspection(state, { type: "confirmMatch", matchId: match.id });
  // The seed samples are valid. Confirmation, not a fake edit, records their derived result.
  for (const item of state.internalTests) state = reduceInspection(state, { type: "confirmInternalTest", itemId: item.id });
  return state;
}

function submittedState(): InspectionFixtureState {
  return reduceInspection(preflightState(), { type: "submit", reason: "fixture submit" });
}

function recursivelyFrozen(value: unknown): boolean {
  return !value || typeof value !== "object" || (Object.isFrozen(value) && Object.values(value).every(recursivelyFrozen));
}

describe("inspection fixture workflow", () => {
  it("keeps snapshot construction outside the public workflow API", () => {
    expect(inspectionWorkflow).not.toHaveProperty("buildFrozenSnapshot");
  });

  it("uses strict decimal strings and BigInt/string arithmetic", () => {
    expect(isCanonicalDecimalString("1250.50")).toBe(true);
    expect(isCanonicalDecimalString("01.2")).toBe(false);
    expect(isCanonicalDecimalString("1e3")).toBe(false);
    expect(isCanonicalDecimalString(" 1.2")).toBe(false);
    expect(averageDecimalStrings(["99.8", "100.0", "100.2"])).toBe("100");
    expect(averageDecimalStrings(["1", "1", "2"])).toBeNull();
    const businessSources = ["workflow.ts", "fixtures.ts", "types.ts"].map((file) => readFileSync(resolve(process.cwd(), "src/lib/inspection", file), "utf8")).join("\n");
    expect(businessSources).not.toMatch(/\b(Number|parseFloat)\s*\(/);
  });

  it("fails closed for empty required documents, matches, and internal tests", () => {
    const state = createInspectionFixtureState();
    expect(isDocumentReviewCompleteForFixture({ ...state, documentReview: { ...state.documentReview, fields: [] } })).toBe(false);
    expect(areMatchesConfirmedForFixture({ ...state, matches: [] })).toBe(false);
    expect(areRequiredTestsCompleteForFixture({ ...state, internalTests: [] })).toBe(false);
    expect(canSubmit(state).blockers).toEqual(expect.arrayContaining(["문서 검토 확정 필요", "section↔allocation 확인 필요", "자체검사 필수 항목 미완료"]));
  });

  it("requires confirmed matches to carry trimmed evidence and reasons for submit and approval", () => {
    const ready = preflightState();
    for (const field of ["evidence", "reason"] as const) {
      const incomplete = {
        ...ready,
        matches: ready.matches.map((match) => ({ ...match, [field]: " " })),
        submissionReason: "submit",
      };
      expect(areMatchesConfirmedForFixture(incomplete)).toBe(false);
      expect(canSubmit(incomplete, "submit").allowed).toBe(false);
      const directApproval = { ...incomplete, workflowStatus: "SUBMITTED" as const, selectedRole: "LEAD" as const, submissionReason: "submit" };
      expect(canApprove(directApproval, "approve").allowed).toBe(false);
      expect(reduceInspection(directApproval, { type: "approve", reason: "approve" })).toBe(directApproval);
    }
  });

  it("requires trimmed document finals and valid decimal finals", () => {
    const state = createInspectionFixtureState();
    const invalid = {
      ...state,
      documentReview: { ...state.documentReview, fields: state.documentReview.fields.map((field) => ({ ...field, finalSource: "MANUAL" as const, finalValue: field.kind === "decimal" ? "1e3" : "  ", reason: "  " })) },
    };
    expect(isDocumentReviewCompleteForFixture(invalid)).toBe(false);
    expect(canSubmit(invalid).blockers).toContain("문서 검토 확정 필요");
  });

  it("keeps represented qualitative blank rows pending after trim", () => {
    const qualitative = createInspectionFixtureState().internalTests.find((item) => item.unit === "판정")!;
    expect(getInternalTestSemantics({ ...qualitative, samples: ["적합", ""] })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(getInternalTestSemantics({ ...qualitative, samples: [" ", "적합"] })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(getInternalTestSemantics({ ...qualitative, samples: ["적합", "부적합"] })).toEqual({ aggregate: "부적합", completed: true, hycDecision: "부적합" });
  });

  it("keeps numeric internal tests pending when HYC or supplier thresholds are missing or malformed", () => {
    const numeric = createInspectionFixtureState().internalTests.find((item) => item.unit === "%")!;
    expect(getInternalTestSemantics({ ...numeric, hycSpecMin: undefined, hycSpecMax: undefined })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(getInternalTestSemantics({ ...numeric, supplierSpecMin: undefined, supplierSpecMax: undefined })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(getInternalTestSemantics({ ...numeric, hycSpecMax: "0.2 " })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(getInternalTestSemantics({ ...numeric, supplierSpecMax: "0,30" })).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
  });

  it("requires explicit confirmation for valid initial samples and resets it when samples change", () => {
    const seed = createInspectionFixtureState();
    expect(areRequiredTestsCompleteForFixture(seed)).toBe(false);
    const confirmed = preflightState();
    expect(confirmed.workflowStatus).toBe("READY_TO_SUBMIT");
    const changed = reduceInspection(confirmed, { type: "setInternalSamples", itemId: confirmed.internalTests[0].id, samples: ["0.10", "0.11"] });
    expect(changed.internalTests[0]).toMatchObject({ aggregate: null, completed: false, hycDecision: "대기" });
  });

  it("allows only READY_TO_SUBMIT or RETURNED submission sources", () => {
    const ready = preflightState();
    expect(canSubmit(ready, "submit").allowed).toBe(true);
    for (const workflowStatus of ["REVIEW_REQUIRED", "INTERNAL_TEST_PENDING"] as const) {
      expect(canSubmit({ ...ready, workflowStatus }, "submit").blockers).toContain("READY_TO_SUBMIT 또는 RETURNED 상태에서만 제출 가능");
    }
    const submitted = submittedState();
    const returned = reduceInspection(reduceInspection(submitted, { type: "setRole", role: "LEAD" }), { type: "return", reason: "보완 필요" });
    expect(returned.workflowStatus).toBe("RETURNED");
    expect(canSubmit(reduceInspection(returned, { type: "setRole", role: "INSPECTOR" }), "resubmit").allowed).toBe(true);
  });

  it("derives return and approval authority only from selectedRole", () => {
    const submitted = submittedState();
    expect(canReturn(submitted, "보완 필요").allowed).toBe(false);
    expect(canApprove(submitted, "검토 완료").allowed).toBe(false);
    expect(reduceInspection(submitted, { type: "return", reason: "보완 필요" })).toBe(submitted);
    expect(reduceInspection(submitted, { type: "approve", reason: "검토 완료" })).toBe(submitted);
    const lead = reduceInspection(submitted, { type: "setRole", role: "LEAD" });
    expect(reduceInspection(lead, { type: "return", reason: "보완 필요" }).workflowStatus).toBe("RETURNED");
    expect(reduceInspection(lead, { type: "approve", reason: "검토 완료" }).workflowStatus).toBe("APPROVED");
  });

  it("rejects direct-state approval attempts without an authoritative submission reason", () => {
    const ready = preflightState();
    const forgedSubmitted = { ...ready, workflowStatus: "SUBMITTED" as const, selectedRole: "LEAD" as const };
    expect(canApprove(forgedSubmitted, "검토 완료")).toMatchObject({ allowed: false, blockers: expect.arrayContaining(["제출 사유 필요"]) });
    expect(reduceInspection(forgedSubmitted, { type: "approve", reason: "검토 완료" })).toBe(forgedSubmitted);
  });

  it("fails closed for receipt, allocation, fixture boundary, and relationship inconsistency", () => {
    const valid = preflightState();
    const expectBlocker = (state: InspectionFixtureState, blocker: string) => expect(canSubmit(state, "submit").blockers).toContain(blocker);
    expectBlocker({ ...valid, receipt: { ...valid.receipt, allocations: [] } }, "입고 배분이 최소 1건 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, allocations: valid.receipt.allocations.map((allocation, index) => index === 0 ? { ...allocation, canonicalLot: "FX-OTHER" } : allocation) } }, "입고 배분 정본 LOT가 입고 정본 LOT와 불일치");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, allocations: valid.receipt.allocations.map((allocation, index) => index === 0 ? { ...allocation, quantity: "7,50" } : allocation) } }, "입고 배분 수량 정본 소수 문자열 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, allocationQuantity: "700.25", allocations: valid.receipt.allocations } }, "입고 배분 수량이 첫 번째 allocation 수량과 불일치");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, receivedQuantity: "1250.51" } }, "입고 배분 수량 합계가 입고 수량과 불일치");
    expectBlocker({ ...valid, matches: [{ ...valid.matches[0], allocation: "FX-ALLOC-MISSING" }] }, "매칭 allocation 참조가 입고 배분에 없음");
    expectBlocker({ ...valid, matches: [{ ...valid.matches[0], section: "SECTION-01" }] }, "매칭 문서 section은 FX 식별자여야 함");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, receiptId: "RECEIPT-01" } }, "FX fixture-only 식별자만 허용");
  });

  it("validates receipt scalars, unique relationship IDs, bound specification IDs, and canonical trace", () => {
    const valid = preflightState();
    const expectBlocker = (state: InspectionFixtureState, blocker: string) => expect(canSubmit(state, "submit").blockers).toContain(blocker);
    expectBlocker({ ...valid, receipt: { ...valid.receipt, supplier: " " } }, "공급사 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, material: " " } }, "품목 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, receiptDate: "2026/07/31" } }, "입고일은 YYYY-MM-DD 형식 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, unit: " " } }, "입고 단위 필요");
    expectBlocker({ ...valid, receipt: { ...valid.receipt, allocations: [{ ...valid.receipt.allocations[0] }, { ...valid.receipt.allocations[1], id: valid.receipt.allocations[0].id }] } }, "입고 배분 ID는 고유한 필수 값이어야 함");
    expectBlocker({ ...valid, documentReview: { ...valid.documentReview, fields: [valid.documentReview.fields[0], { ...valid.documentReview.fields[1], id: valid.documentReview.fields[0].id }, valid.documentReview.fields[2]] } }, "문서 필드 ID는 고유한 필수 값이어야 함");
    expectBlocker({ ...valid, matches: [valid.matches[0], { ...valid.matches[0] }] }, "매칭 ID는 고유한 필수 값이어야 함");
    expectBlocker({ ...valid, internalTests: [valid.internalTests[0], { ...valid.internalTests[1], id: valid.internalTests[0].id }] }, "자체검사 ID는 고유한 필수 값이어야 함");
    expectBlocker({ ...valid, trace: [{ ...valid.trace[0] }, { ...valid.trace[1], id: valid.trace[0].id }] }, "trace ID와 순서는 고유해야 함");
    expectBlocker({ ...valid, internalTests: valid.internalTests.map((item) => ({ ...item, specificationId: "FX-SPEC-OTHER-MOISTURE-v1.0" })) }, "자체검사 specificationId는 specVersion profile/version과 일치해야 함");
    const traceDrift = { ...valid, trace: valid.trace.map((event, index) => index === 0 ? { ...event, detail: "FX-DRIFT" } : event) };
    expectBlocker(traceDrift, "결정적 trace가 현재 fixture 관계와 불일치");
    expect(canApprove({ ...traceDrift, workflowStatus: "SUBMITTED", selectedRole: "LEAD" }, "approve").allowed).toBe(false);
  });

  it("fails closed when coordinated specification substitutions drift from the immutable fixture contract", () => {
    const valid = preflightState();
    expect(recursivelyFrozen(deterministicFixtureContract)).toBe(true);
    const coordinatedUnrelated = {
      ...valid,
      specVersion: "FX-SPEC-OTHER-v9.9",
      internalTests: valid.internalTests.map((item) => ({ ...item, specificationId: "FX-SPEC-OTHER-INTERNAL-v9.9" })),
    };
    const coordinatedSameProfile = {
      ...valid,
      specVersion: "FX-SPEC-CACL2-v9.9",
      internalTests: valid.internalTests.map((item) => ({ ...item, specificationId: "FX-SPEC-CACL2-INTERNAL-v9.9" })),
    };
    for (const drifted of [coordinatedUnrelated, coordinatedSameProfile]) {
      expect(canSubmit(drifted, "submit").blockers).toContain("자체검사 specificationId는 specVersion profile/version과 일치해야 함");
      expect(canApprove({ ...drifted, workflowStatus: "SUBMITTED", selectedRole: "LEAD" }, "approve").allowed).toBe(false);
    }
  });

  it("requires every exact required internal specification identity and immutable bound", () => {
    const valid = preflightState();
    const snapshotCandidate = (state: InspectionFixtureState): InspectionFixtureState => ({
      ...state,
      workflowStatus: "SUBMITTED",
      selectedRole: "LEAD",
      submissionReason: "submit",
      reviewerReason: "approve",
      trace: deriveCanonicalTrace(state),
    });
    const otherSpecificationIds = {
      ...valid,
      internalTests: valid.internalTests.map((item) => ({ ...item, specificationId: "FX-SPEC-CACL2-OTHER-v1.0" })),
    };
    const thresholdDrift = {
      ...valid,
      internalTests: valid.internalTests.map((item) => item.unit === "%" ? { ...item, supplierSpecMax: "999" } : item),
    };
    const missingRequiredRecord = { ...valid, internalTests: valid.internalTests.slice(1) };
    const extraRequiredRecord = {
      ...valid,
      internalTests: [...valid.internalTests, { ...valid.internalTests[0], id: "FX-INTERNAL-EXTRA-01" }],
    };
    const duplicatedRequiredRecord = {
      ...valid,
      internalTests: [valid.internalTests[0], { ...valid.internalTests[0] }],
    };
    for (const drifted of [otherSpecificationIds, thresholdDrift, missingRequiredRecord, extraRequiredRecord, duplicatedRequiredRecord]) {
      expect(canSubmit(drifted, "submit").allowed).toBe(false);
      expect(canApprove(snapshotCandidate(drifted), "approve").allowed).toBe(false);
    }
  });

  it("rejects an otherwise-valid optional-looking internal test outside the frozen contract", () => {
    const valid = preflightState();
    const internalTests = [...valid.internalTests, { ...valid.internalTests[0], id: "FX-INTERNAL-OPTIONAL-EXTRA-01", required: false }];
    const withExtra = { ...valid, internalTests };
    const optionalLookingExtra = { ...withExtra, trace: deriveCanonicalTrace(withExtra) };
    const directApproval = { ...optionalLookingExtra, workflowStatus: "SUBMITTED" as const, selectedRole: "LEAD" as const, submissionReason: "submit" };

    expect(canSubmit(optionalLookingExtra, "submit").blockers).toContain("필수 자체검사 정본 규격 계약과 불일치");
    expect(canApprove(directApproval, "approve").allowed).toBe(false);
    expect(reduceInspection(directApproval, { type: "approve", reason: "approve" })).toBe(directApproval);
  });

  it("rejects whitespace-padded semantic duplicate section-allocation relationships", () => {
    const valid = preflightState();
    const duplicateRelationship = {
      ...valid,
      matches: [
        ...valid.matches,
        { ...valid.matches[0], id: "FX-MATCH-02", section: ` ${valid.matches[0].section}`, allocation: `${valid.matches[0].allocation} ` },
      ],
    };
    const submittedLead = {
      ...duplicateRelationship,
      workflowStatus: "SUBMITTED" as const,
      selectedRole: "LEAD" as const,
      submissionReason: "submit",
      reviewerReason: "approve",
      trace: deriveCanonicalTrace(duplicateRelationship),
    };
    expect(canSubmit(duplicateRelationship, "submit").blockers).toContain("매칭 section·allocation 관계는 고유해야 함");
    expect(canApprove(submittedLead, "approve").allowed).toBe(false);
    expect(reduceInspection(submittedLead, { type: "approve", reason: "approve" })).toBe(submittedLead);
  });

  it("rejects duplicate section-allocation pairs even with distinct match IDs", () => {
    const valid = preflightState();
    const duplicateRelationship = {
      ...valid,
      matches: [...valid.matches, { ...valid.matches[0], id: "FX-MATCH-02" }],
    };
    expect(canSubmit(duplicateRelationship, "submit").blockers).toContain("매칭 section·allocation 관계는 고유해야 함");
    expect(canApprove({ ...duplicateRelationship, workflowStatus: "SUBMITTED", selectedRole: "LEAD" }, "approve").allowed).toBe(false);
  });

  it("blocks completion, submission, approval, and snapshots when a numeric record has no supplier bounds", () => {
    const valid = preflightState();
    const missingSupplierBounds = {
      ...valid,
      internalTests: valid.internalTests.map((item) => item.unit === "%" ? {
        ...item,
        supplierSpecMin: undefined,
        supplierSpecMax: undefined,
      } : item),
    };
    const numeric = missingSupplierBounds.internalTests.find((item) => item.unit === "%")!;
    expect(getInternalTestSemantics(numeric)).toEqual({ aggregate: null, completed: false, hycDecision: "대기" });
    expect(reduceInspection(missingSupplierBounds, { type: "confirmInternalTest", itemId: numeric.id })).toBe(missingSupplierBounds);
    expect(areRequiredTestsCompleteForFixture(missingSupplierBounds)).toBe(false);
    expect(canSubmit(missingSupplierBounds, "submit").allowed).toBe(false);
    expect(canApprove({ ...missingSupplierBounds, workflowStatus: "SUBMITTED", selectedRole: "LEAD" }, "approve").allowed).toBe(false);
  });

  it("blocks reducer-path readiness, submit, and approval after receipt unit diverges from allocations", () => {
    const ready = preflightState();
    const diverged = reduceInspection(ready, { type: "setReceiptField", field: "unit", value: "g" });
    expect(diverged.workflowStatus).toBe("REVIEW_REQUIRED");
    expect(canSubmit(diverged, "submit").blockers).toContain("입고 배분 단위가 입고 단위와 불일치");
    expect(canApprove({ ...diverged, workflowStatus: "SUBMITTED", selectedRole: "LEAD" }, "approve").allowed).toBe(false);
    const reconciled = { ...diverged, receipt: { ...diverged.receipt, allocations: diverged.receipt.allocations.map((allocation) => ({ ...allocation, unit: "g" })) } };
    const readyAgain = reduceInspection(reconciled, { type: "setReceiptField", field: "unit", value: "g" });
    expect(readyAgain.workflowStatus).toBe("READY_TO_SUBMIT");
    expect(canSubmit(readyAgain, "submit").allowed).toBe(true);
    const submitted = reduceInspection(readyAgain, { type: "submit", reason: "submit" });
    expect(reduceInspection(reduceInspection(submitted, { type: "setRole", role: "LEAD" }), { type: "approve", reason: "approve" }).workflowStatus).toBe("APPROVED");
  });

  it("creates a complete deterministic approval snapshot and recursively freezes approved state", () => {
    const submitted = submittedState();
    const lead = reduceInspection(submitted, { type: "setRole", role: "LEAD" });
    const approved = reduceInspection(lead, { type: "approve", reason: "검토 완료" });
    expect(approved.workflowStatus).toBe("APPROVED");
    expect(recursivelyFrozen(approved)).toBe(true);
    expect(approved.frozenSnapshot).toMatchObject({
      fixtureOnly: true,
      fixtureId: "FX-CASE-20260731-001",
      receipt: { receiptId: "FX-RECEIPT-01", supplier: "SYNTHETIC 동해화학", receiptDate: "2026-07-31", canonicalLot: "FX-HYC-CC-20260731-01", unit: "kg" },
      document: { documentId: "FX-DOC-COA-001", name: "SYNTHETIC-COA-CC-001" },
      specVersion: "FX-SPEC-CACL2-v1.0",
      submissionReason: "fixture submit",
      approvalReason: "검토 완료",
      overallDecision: "적합",
    });
    expect(approved.frozenSnapshot?.documentFinals.every((field) => field.finalValue && field.reason && field.finalSource && field.ocrCandidate !== undefined)).toBe(true);
    expect(approved.frozenSnapshot?.requiredInternalRecords.every((item) => item.aggregate && item.supplierDecision && item.hycDecision && item.specificationId)).toBe(true);
    const serializedSnapshot = JSON.parse(JSON.stringify(approved.frozenSnapshot)) as typeof approved.frozenSnapshot;
    for (const item of serializedSnapshot!.requiredInternalRecords) {
      expect(Object.keys(item)).toEqual(expect.arrayContaining(["hycSpecMin", "hycSpecMax", "supplierSpecMin", "supplierSpecMax"]));
    }
    const numeric = serializedSnapshot!.requiredInternalRecords.find((item) => item.unit === "%")!;
    expect(numeric).toMatchObject({ hycSpecMin: "0", hycSpecMax: "0.20", supplierSpecMin: null, supplierSpecMax: "0.30" });
    const qualitative = serializedSnapshot!.requiredInternalRecords.find((item) => item.unit === "판정")!;
    expect(qualitative).toMatchObject({ hycSpecMin: null, hycSpecMax: null, supplierSpecMin: null, supplierSpecMax: null });
    expect(approved.frozenSnapshot?.calculationPolicy).toMatchObject({ numericSampleAggregate: "EXACT_FINITE_DECIMAL_MEAN", numericBounds: "INCLUSIVE", missingOrInvalid: "HOLD", rounding: "NONE" });
    expect(approved.frozenSnapshot?.trace).toEqual(deriveCanonicalTrace(approved));
    expect(recursivelyFrozen(approved.frozenSnapshot)).toBe(true);
    expect(Object.keys(approved.frozenSnapshot ?? {}).sort()).toEqual([
      "allocations",
      "approvalReason",
      "calculationPolicy",
      "caseName",
      "confirmedMatches",
      "document",
      "documentFinals",
      "fixtureId",
      "fixtureOnly",
      "overallDecision",
      "priority",
      "receipt",
      "requiredInternalRecords",
      "simulatedApproverRole",
      "simulatedSubmitterRole",
      "specVersion",
      "submissionReason",
      "trace",
    ]);
    expect(() => { approved.receipt.canonicalLot = "FX-MUTATED"; }).toThrow();
    expect(() => { approved.internalTests[0].samples[0] = "0.99"; }).toThrow();
    expect(approved.frozenSnapshot?.receipt.canonicalLot).toBe("FX-HYC-CC-20260731-01");
  });

  it("rejects invalid public approval transitions and preserves the fixture-only seed boundary", () => {
    const ready = preflightState();
    const submittedEvidence = { ...ready, workflowStatus: "SUBMITTED" as const, selectedRole: "LEAD" as const, submissionReason: "submit" };
    const invalidApprovalStates = [
      { ...ready, submissionReason: "submit" },
      { ...submittedEvidence, documentReview: { ...submittedEvidence.documentReview, fields: submittedEvidence.documentReview.fields.map((field) => ({ ...field, reason: "" })) } },
      { ...submittedEvidence, matches: submittedEvidence.matches.map((match) => ({ ...match, confirmed: false })) },
      { ...submittedEvidence, matches: submittedEvidence.matches.map((match) => ({ ...match, evidence: " " })) },
      { ...submittedEvidence, matches: submittedEvidence.matches.map((match) => ({ ...match, reason: "" })) },
      { ...submittedEvidence, internalTests: submittedEvidence.internalTests.map((item) => ({ ...item, aggregate: null })) },
      { ...submittedEvidence, internalTests: submittedEvidence.internalTests.map((item) => item.unit === "%" ? { ...item, hycSpecMax: "bad" } : item) },
    ];
    for (const invalid of invalidApprovalStates) {
      expect(canApprove(invalid, "approve").allowed).toBe(false);
      expect(reduceInspection(invalid, { type: "approve", reason: "approve" })).toBe(invalid);
    }
    expect(isFixtureOnlyCase(inspectionFixture)).toBe(true);
    expect(recursivelyFrozen(inspectionFixture)).toBe(true);
  });
});
