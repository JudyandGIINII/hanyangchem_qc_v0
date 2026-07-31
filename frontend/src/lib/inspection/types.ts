export type WorkflowRole = "INSPECTOR" | "LEAD" | "ADMIN";

export type WorkflowStatus =
  | "REVIEW_REQUIRED"
  | "INTERNAL_TEST_PENDING"
  | "READY_TO_SUBMIT"
  | "SUBMITTED"
  | "RETURNED"
  | "APPROVED";

export type DocumentSource = "ORIGINAL" | "OCR" | "MANUAL";
export type DocumentFieldKind = "decimal" | "text";

export interface ReceiptAllocationFixture {
  id: string;
  canonicalLot: string;
  materialLot: string;
  quantity: string;
  unit: string;
  purpose: string;
  status: "문서 매칭 대기" | "검사 대상" | "보류";
}

export interface ReceiptFixture {
  receiptId: string;
  supplier: string;
  material: string;
  receiptDate: string;
  rawLot: string;
  canonicalLot: string;
  receivedQuantity: string;
  allocationQuantity: string;
  unit: string;
  allocations: ReceiptAllocationFixture[];
}

export interface DocumentFieldFixture {
  id: string;
  label: string;
  kind: DocumentFieldKind;
  unit?: string;
  required: boolean;
  originalValue: string;
  ocrValue: string;
  manualValue: string;
  confidence: "HIGH" | "LOW" | "MISSING";
  warning: string;
  finalValue?: string;
  finalSource?: DocumentSource;
  reason?: string;
}

export interface MatchFixture {
  id: string;
  section: string;
  allocation: string;
  evidence: string;
  reason: string;
  conflict: string;
  confirmed: boolean;
}

export interface InternalTestFixture {
  id: string;
  item: string;
  required: boolean;
  specificationId: string;
  hycSpecMin?: string;
  hycSpecMax?: string;
  supplierSpecMin?: string;
  supplierSpecMax?: string;
  supplierDecision: "후보" | "부적합" | "적합";
  hycDecision: "대기" | "부적합" | "적합";
  unit: string;
  samples: string[];
  aggregate: string | null;
  completed: boolean;
  holdReason: string;
}

export interface TraceEventFixture {
  id: string;
  order: number;
  type: string;
  title: string;
  detail: string;
}

/** Local-only evidence of the calculation behavior represented by this fixture. */
export interface FixtureCalculationPolicy {
  fixtureOnly: true;
  numericSampleAggregate: "EXACT_FINITE_DECIMAL_MEAN";
  numericBounds: "INCLUSIVE";
  qualitativeRows: "ALL_REPRESENTED_ROWS_VALID_ANY_NONCONFORMING_FAILS";
  missingOrInvalid: "HOLD";
  rounding: "NONE";
  requiredHycFailure: "OVERALL_NONCONFORMING";
}

/** Immutable, exact authority for each required local internal-test specification. */
export interface ExactInternalSpecificationContract {
  readonly id: string;
  readonly specificationId: string;
  readonly required: true;
  readonly item: string;
  readonly unit: string;
  readonly hycSpecMin: string | null;
  readonly hycSpecMax: string | null;
  readonly supplierSpecMin: string | null;
  readonly supplierSpecMax: string | null;
}

export interface DeterministicFixtureContract {
  readonly caseSpecVersion: string;
  readonly internalSpecificationProfileVersion: string;
  readonly requiredInternalSpecifications: ReadonlyArray<ExactInternalSpecificationContract>;
}

export const fixtureCalculationPolicy: FixtureCalculationPolicy = {
  fixtureOnly: true,
  numericSampleAggregate: "EXACT_FINITE_DECIMAL_MEAN",
  numericBounds: "INCLUSIVE",
  qualitativeRows: "ALL_REPRESENTED_ROWS_VALID_ANY_NONCONFORMING_FAILS",
  missingOrInvalid: "HOLD",
  rounding: "NONE",
  requiredHycFailure: "OVERALL_NONCONFORMING",
};

export interface FrozenFixtureSnapshot {
  fixtureOnly: true;
  fixtureId: string;
  caseName: string;
  priority: "높음" | "보통";
  receipt: {
    receiptId: string;
    supplier: string;
    material: string;
    receiptDate: string;
    rawLot: string;
    canonicalLot: string;
    receivedQuantity: string;
    allocationQuantity: string;
    unit: string;
  };
  allocations: ReadonlyArray<{
    id: string;
    canonicalLot: string;
    materialLot: string;
    quantity: string;
    unit: string;
    purpose: string;
    status: ReceiptAllocationFixture["status"];
  }>;
  document: { documentId: string; name: string };
  specVersion: string;
  confirmedMatches: ReadonlyArray<{
    id: string;
    section: string;
    allocation: string;
    evidence: string;
    reason: string;
    conflict: string;
    confirmed: true;
  }>;
  documentFinals: ReadonlyArray<{
    id: string;
    label: string;
    kind: DocumentFieldKind;
    unit?: string;
    originalValue: string;
    ocrCandidate: string;
    manualValue: string;
    confidence: DocumentFieldFixture["confidence"];
    warning: string;
    finalValue: string;
    finalSource: DocumentSource;
    reason: string;
  }>;
  requiredInternalRecords: ReadonlyArray<{
    id: string;
    item: string;
    required: true;
    specificationId: string;
    unit: string;
    samples: ReadonlyArray<string>;
    aggregate: string;
    hycSpecMin: string | null;
    hycSpecMax: string | null;
    supplierSpecMin: string | null;
    supplierSpecMax: string | null;
    supplierDecision: InternalTestFixture["supplierDecision"];
    hycDecision: Exclude<InternalTestFixture["hycDecision"], "대기">;
    holdReason: string;
  }>;
  calculationPolicy: FixtureCalculationPolicy;
  overallDecision: Exclude<InternalTestFixture["hycDecision"], "대기">;
  submissionReason: string;
  approvalReason: string;
  simulatedSubmitterRole: "INSPECTOR";
  simulatedApproverRole: "LEAD";
  trace: ReadonlyArray<TraceEventFixture>;
}

export interface InspectionFixtureState {
  fixtureId: string;
  fixtureOnly: true;
  caseName: string;
  priority: "높음" | "보통";
  workflowStatus: WorkflowStatus;
  selectedRole: WorkflowRole;
  receipt: ReceiptFixture;
  documentReview: {
    documentId: string;
    name: string;
    fields: DocumentFieldFixture[];
  };
  matches: MatchFixture[];
  internalTests: InternalTestFixture[];
  calculationPolicy: FixtureCalculationPolicy;
  specVersion: string;
  submissionReason?: string;
  reviewerReason?: string;
  frozenSnapshot?: FrozenFixtureSnapshot;
  trace: TraceEventFixture[];
}

export type InspectionAction =
  | { type: "setRole"; role: WorkflowRole }
  | { type: "setReceiptField"; field: Exclude<keyof ReceiptFixture, "allocations">; value: string }
  | { type: "finalizeDocumentReview"; fieldId: string; source: DocumentSource; value: string; reason: string }
  | { type: "confirmMatch"; matchId: string }
  | { type: "setInternalSamples"; itemId: string; samples: string[] }
  | { type: "confirmInternalTest"; itemId: string }
  | { type: "submit"; reason: string }
  | { type: "return"; reason: string }
  | { type: "approve"; reason: string };
