import {
  fixtureCalculationPolicy,
  type DeterministicFixtureContract,
  type InspectionFixtureState,
} from "./types";

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nestedValue of Object.values(value as Record<string, unknown>)) deepFreeze(nestedValue);
    Object.freeze(value);
  }
  return value;
}

function deepClone<T>(value: T): T {
  if (Array.isArray(value)) return value.map((entry) => deepClone(entry)) as T;
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, entry]) => [key, deepClone(entry)])) as T;
  }
  return value;
}

/** Explicit immutable specification design for the one local deterministic fixture. */
const deterministicRequiredInternalSpecificationDesign = [
  {
    id: "FX-INTERNAL-MOISTURE-01",
    specificationId: "FX-SPEC-CACL2-MOISTURE-v1.0",
    required: true,
    item: "자체 수분 검사",
    unit: "%",
    hycSpecMin: "0",
    hycSpecMax: "0.20",
    supplierSpecMin: null,
    supplierSpecMax: "0.30",
  },
  {
    id: "FX-INTERNAL-APPEARANCE-01",
    specificationId: "FX-SPEC-CACL2-APPEARANCE-v1.0",
    required: true,
    item: "자체 외관 확인",
    unit: "판정",
    hycSpecMin: null,
    hycSpecMax: null,
    supplierSpecMin: null,
    supplierSpecMax: null,
  },
] as const;

/** Immutable authority for the one local deterministic inspection fixture. */
export const deterministicFixtureContract: DeterministicFixtureContract = deepFreeze({
  caseSpecVersion: "FX-SPEC-CACL2-v1.0",
  internalSpecificationProfileVersion: "FX-SPEC-CACL2-INTERNAL-v1.0",
  requiredInternalSpecifications: deterministicRequiredInternalSpecificationDesign.map((specification) => ({ ...specification })),
});

export const inspectionFixture: InspectionFixtureState = deepFreeze({
  fixtureId: "FX-CASE-20260731-001",
  fixtureOnly: true,
  caseName: "염화칼슘 비드 · 합성 입고 검사",
  priority: "높음",
  workflowStatus: "REVIEW_REQUIRED",
  selectedRole: "INSPECTOR",
  receipt: {
    receiptId: "FX-RECEIPT-01",
    supplier: "SYNTHETIC 동해화학",
    material: "염화칼슘 비드 (SYNTHETIC)",
    receiptDate: "2026-07-31",
    rawLot: "FX-SUP-CC-0731-A",
    canonicalLot: "FX-HYC-CC-20260731-01",
    receivedQuantity: "1250.50",
    allocationQuantity: "750.25",
    unit: "kg",
    allocations: [
      {
        id: "FX-ALLOC-01",
        canonicalLot: "FX-HYC-CC-20260731-01",
        materialLot: "FX-MATERIAL-LOT-CC-01",
        quantity: "750.25",
        unit: "kg",
        purpose: "자체검사 대상",
        status: "검사 대상",
      },
      {
        id: "FX-ALLOC-02",
        canonicalLot: "FX-HYC-CC-20260731-01",
        materialLot: "FX-MATERIAL-LOT-CC-01",
        quantity: "500.25",
        unit: "kg",
        purpose: "보류 재고",
        status: "보류",
      },
    ],
  },
  documentReview: {
    documentId: "FX-DOC-COA-001",
    name: "SYNTHETIC-COA-CC-001",
    fields: [
      {
        id: "FX-DOC-FIELD-MOISTURE",
        label: "수분",
        kind: "decimal",
        unit: "%",
        required: true,
        originalValue: "0.12",
        ocrValue: "0.12",
        manualValue: "0.12",
        confidence: "LOW",
        warning: "OCR confidence 62% — 수기 대조와 사유가 필요합니다.",
      },
      {
        id: "FX-DOC-FIELD-PURITY",
        label: "CaCl₂ 순도",
        kind: "decimal",
        unit: "%",
        required: true,
        originalValue: "96.50",
        ocrValue: "96.50",
        manualValue: "96.50",
        confidence: "HIGH",
        warning: "최종 출처를 검사자가 확정해야 합니다.",
      },
      {
        id: "FX-DOC-FIELD-APPEARANCE",
        label: "외관",
        kind: "text",
        required: true,
        originalValue: "백색 구상",
        ocrValue: "",
        manualValue: "백색 구상",
        confidence: "MISSING",
        warning: "OCR 누락 — 원문 또는 수기 값을 확정해야 합니다.",
      },
    ],
  },
  matches: [
    {
      id: "FX-MATCH-01",
      section: "FX-SECTION-COA-01",
      allocation: "FX-ALLOC-01",
      evidence: "공급사 LOT FX-SUP-CC-0731-A 및 품목명이 일치",
      reason: "후보 점수 0.94 · 문서의 포장 단위와 배분 1이 부합",
      conflict: "확정 전 잠정 후보 — 자동 연결하지 않습니다.",
      confirmed: false,
    },
  ],
  internalTests: [
    {
      id: "FX-INTERNAL-MOISTURE-01",
      item: "자체 수분 검사",
      required: true,
      specificationId: "FX-SPEC-CACL2-MOISTURE-v1.0",
      hycSpecMin: "0",
      hycSpecMax: "0.20",
      supplierSpecMax: "0.30",
      supplierDecision: "후보",
      hycDecision: "대기",
      unit: "%",
      samples: ["0.10", "0.12", "0.11"],
      aggregate: null,
      completed: false,
      holdReason: "INTERNAL_TEST_PENDING",
    },
    {
      id: "FX-INTERNAL-APPEARANCE-01",
      item: "자체 외관 확인",
      required: true,
      specificationId: "FX-SPEC-CACL2-APPEARANCE-v1.0",
      supplierDecision: "후보",
      hycDecision: "대기",
      unit: "판정",
      samples: ["적합"],
      aggregate: null,
      completed: false,
      holdReason: "INTERNAL_TEST_PENDING",
    },
  ],
  calculationPolicy: fixtureCalculationPolicy,
  specVersion: deterministicFixtureContract.caseSpecVersion,
  trace: [
    { id: "FX-TRACE-01", order: 1, type: "입고", title: "분할 입고 생성", detail: "FX-RECEIPT-01 → FX-ALLOC-01 / FX-ALLOC-02" },
    { id: "FX-TRACE-02", order: 2, type: "LOT", title: "정본 LOT 연결", detail: "FX-HYC-CC-20260731-01" },
    { id: "FX-TRACE-03", order: 3, type: "문서", title: "합성 문서 section", detail: "FX-DOC-COA-001 · FX-SECTION-COA-01" },
    { id: "FX-TRACE-04", order: 4, type: "매칭", title: "section·allocation 관계", detail: "FX-SECTION-COA-01 ↔ FX-ALLOC-01" },
    { id: "FX-TRACE-05", order: 5, type: "검사", title: "필수 자체검사", detail: "FX-INTERNAL-MOISTURE-01 / FX-INTERNAL-APPEARANCE-01" },
    { id: "FX-TRACE-06", order: 6, type: "규격", title: "고정될 규격 버전", detail: "FX-SPEC-CACL2-v1.0" },
    { id: "FX-TRACE-07", order: 7, type: "감사", title: "fixture local 결정 근거", detail: "FX-RECEIPT-01 | FX-ALLOC-01 / FX-ALLOC-02 | FX-HYC-CC-20260731-01 | FX-DOC-COA-001 | FX-SECTION-COA-01 ↔ FX-ALLOC-01 | FX-INTERNAL-MOISTURE-01 / FX-INTERNAL-APPEARANCE-01 | FX-SPEC-CACL2-v1.0" },
  ],
});

/** Creates an isolated local fixture state for each UI reducer instance. */
export function createInspectionFixtureState(): InspectionFixtureState {
  return deepClone(inspectionFixture);
}
