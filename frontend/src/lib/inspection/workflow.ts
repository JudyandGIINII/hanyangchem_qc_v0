import type {
  FixtureCalculationPolicy,
  FrozenFixtureSnapshot,
  InspectionAction,
  InspectionFixtureState,
  InternalTestFixture,
  TraceEventFixture,
} from "./types";
import { fixtureCalculationPolicy } from "./types";
import { deterministicFixtureContract } from "./fixtures";

export interface WorkflowGuard {
  allowed: boolean;
  blockers: string[];
}

const decimalPattern = /^(?:0|[1-9]\d*)(?:\.\d+)?$/;
const receiptDatePattern = /^\d{4}-\d{2}-\d{2}$/;

export function isCanonicalDecimalString(value: string): boolean {
  return decimalPattern.test(value);
}

function decimalParts(value: string): { digits: string; scale: number } | null {
  if (!isCanonicalDecimalString(value)) return null;
  const [integer, fraction = ""] = value.split(".");
  return { digits: `${integer}${fraction}`, scale: fraction.length };
}

function powerOfTen(power: number): bigint {
  let result = 1n;
  for (let remaining = power; remaining > 0; remaining -= 1) result *= 10n;
  return result;
}

function greatestCommonDivisor(left: bigint, right: bigint): bigint {
  let first = left < 0n ? -left : left;
  let second = right < 0n ? -right : right;
  while (second !== 0n) [first, second] = [second, first % second];
  return first;
}

function formatScaledDecimal(value: bigint, scale: number): string {
  const raw = value.toString().padStart(scale + 1, "0");
  if (scale === 0) return raw;
  const integer = raw.slice(0, raw.length - scale);
  const fraction = raw.slice(raw.length - scale).replace(/0+$/, "");
  return fraction ? `${integer}.${fraction}` : integer;
}

export function compareDecimalStrings(left: string, right: string): -1 | 0 | 1 | null {
  const leftParts = decimalParts(left);
  const rightParts = decimalParts(right);
  if (!leftParts || !rightParts) return null;
  const scale = Math.max(leftParts.scale, rightParts.scale);
  const scaledLeft = BigInt(leftParts.digits) * powerOfTen(scale - leftParts.scale);
  const scaledRight = BigInt(rightParts.digits) * powerOfTen(scale - rightParts.scale);
  return scaledLeft < scaledRight ? -1 : scaledLeft > scaledRight ? 1 : 0;
}

/** Returns null when the arithmetic mean cannot be represented exactly as a finite decimal. */
export function averageDecimalStrings(values: string[]): string | null {
  if (values.length === 0) return null;
  const parsed = values.map(decimalParts);
  if (parsed.some((part) => part === null)) return null;
  const parts = parsed as Array<{ digits: string; scale: number }>;
  const scale = parts.reduce((maximum, part) => Math.max(maximum, part.scale), 0);
  const sum = parts.reduce((total, part) => total + BigInt(part.digits) * powerOfTen(scale - part.scale), 0n);
  const count = BigInt(parts.length);
  const divisor = greatestCommonDivisor(sum, count);
  const numerator = sum / divisor;
  let denominator = count / divisor;
  let twos = 0;
  let fives = 0;
  while (denominator % 2n === 0n) { denominator /= 2n; twos += 1; }
  while (denominator % 5n === 0n) { denominator /= 5n; fives += 1; }
  if (denominator !== 1n) return null;
  const additionalScale = Math.max(twos, fives);
  return formatScaledDecimal(numerator * (powerOfTen(additionalScale) / (count / divisor)), scale + additionalScale);
}

function sumDecimalStrings(values: string[]): string | null {
  if (values.length === 0) return null;
  const parsed = values.map(decimalParts);
  if (parsed.some((part) => part === null)) return null;
  const parts = parsed as Array<{ digits: string; scale: number }>;
  const scale = parts.reduce((maximum, part) => Math.max(maximum, part.scale), 0);
  const sum = parts.reduce((total, part) => total + BigInt(part.digits) * powerOfTen(scale - part.scale), 0n);
  return formatScaledDecimal(sum, scale);
}

function isDocumentReviewComplete(state: InspectionFixtureState): boolean {
  const required = state.documentReview.fields.filter((field) => field.required);
  return required.length > 0 && required.every((field) =>
    Boolean(field.finalValue?.trim() && field.finalSource && field.reason?.trim())
    && (field.kind !== "decimal" || isCanonicalDecimalString(field.finalValue!.trim())),
  );
}

function areMatchesConfirmed(state: InspectionFixtureState): boolean {
  return state.matches.length > 0 && state.matches.every((match) =>
    match.confirmed && Boolean(match.evidence.trim()) && Boolean(match.reason.trim()),
  );
}

export interface InternalTestSemantics {
  aggregate: string | null;
  completed: boolean;
  hycDecision: InternalTestFixture["hycDecision"];
}

/** Derives completion from values, never from editable aggregate/decision fields. */
export function getInternalTestSemantics(item: InternalTestFixture): InternalTestSemantics {
  if (item.unit === "%") {
    const numericBounds = [item.hycSpecMin, item.hycSpecMax, item.supplierSpecMin, item.supplierSpecMax];
    const hasHycBound = item.hycSpecMin !== undefined || item.hycSpecMax !== undefined;
    const hasSupplierBound = item.supplierSpecMin !== undefined || item.supplierSpecMax !== undefined;
    if (!hasHycBound || !hasSupplierBound || numericBounds.some((bound) => bound !== undefined && !isCanonicalDecimalString(bound))) {
      return { aggregate: null, completed: false, hycDecision: "대기" };
    }
    const aggregate = averageDecimalStrings(item.samples);
    if (item.samples.length === 0 || item.samples.some((sample) => !isCanonicalDecimalString(sample)) || !aggregate) {
      return { aggregate: null, completed: false, hycDecision: "대기" };
    }
    const aboveMinimum = item.hycSpecMin !== undefined ? compareDecimalStrings(aggregate, item.hycSpecMin) : 1;
    const belowMaximum = item.hycSpecMax !== undefined ? compareDecimalStrings(aggregate, item.hycSpecMax) : -1;
    return {
      aggregate,
      completed: true,
      hycDecision: aboveMinimum !== null && belowMaximum !== null && aboveMinimum >= 0 && belowMaximum <= 0 ? "적합" : "부적합",
    };
  }
  if (item.unit === "판정") {
    if (item.samples.length === 0) return { aggregate: null, completed: false, hycDecision: "대기" };
    const values = item.samples.map((sample) => sample.trim());
    if (values.some((value) => value !== "적합" && value !== "부적합")) return { aggregate: null, completed: false, hycDecision: "대기" };
    const hycDecision = values.includes("부적합") ? "부적합" : "적합";
    return { aggregate: hycDecision, completed: true, hycDecision };
  }
  return { aggregate: null, completed: false, hycDecision: "대기" };
}

function isRequiredTestComplete(item: InternalTestFixture): boolean {
  const semantics = getInternalTestSemantics(item);
  return semantics.completed
    && item.completed === semantics.completed
    && item.aggregate === semantics.aggregate
    && item.hycDecision === semantics.hycDecision;
}

function areRequiredTestsComplete(state: InspectionFixtureState): boolean {
  const required = state.internalTests.filter((item) => item.required);
  return required.length > 0 && required.every(isRequiredTestComplete);
}

export function isDocumentReviewCompleteForFixture(state: InspectionFixtureState): boolean { return isDocumentReviewComplete(state); }
export function areMatchesConfirmedForFixture(state: InspectionFixtureState): boolean { return areMatchesConfirmed(state); }
export function areRequiredTestsCompleteForFixture(state: InspectionFixtureState): boolean { return areRequiredTestsComplete(state); }

function isFxIdentity(value: string): boolean {
  return Boolean(value) && value === value.trim() && value.startsWith("FX-");
}

function hasTrimmedValue(value: string): boolean { return Boolean(value.trim()); }

function hasUniqueNonemptyValues(values: string[]): boolean {
  return values.every(hasTrimmedValue) && new Set(values).size === values.length;
}

function sameCalculationPolicy(policy: FixtureCalculationPolicy): boolean {
  return Object.entries(fixtureCalculationPolicy).every(([key, value]) =>
    policy[key as keyof FixtureCalculationPolicy] === value,
  ) && Object.keys(policy).length === Object.keys(fixtureCalculationPolicy).length;
}

function parseSpecVersion(value: string): { profile: string; version: string } | null {
  const match = /^FX-SPEC-([A-Z0-9]+)-v(\d+(?:\.\d+)*)$/.exec(value);
  return match ? { profile: match[1], version: match[2] } : null;
}

function parseSpecificationId(value: string): { profile: string; version: string } | null {
  const match = /^FX-SPEC-([A-Z0-9]+)-[A-Z0-9-]+-v(\d+(?:\.\d+)*)$/.exec(value);
  return match ? { profile: match[1], version: match[2] } : null;
}

function hasBoundSpecificationIds(state: InspectionFixtureState): boolean {
  const canonicalCase = parseSpecVersion(deterministicFixtureContract.caseSpecVersion);
  const canonicalInternal = parseSpecificationId(deterministicFixtureContract.internalSpecificationProfileVersion);
  if (
    state.specVersion !== deterministicFixtureContract.caseSpecVersion
    || !canonicalCase
    || !canonicalInternal
    || canonicalCase.profile !== canonicalInternal.profile
    || canonicalCase.version !== canonicalInternal.version
  ) return false;
  return state.internalTests.every((item) => {
    const specification = parseSpecificationId(item.specificationId);
    return specification?.profile === canonicalCase.profile && specification?.version === canonicalCase.version;
  });
}

function hasExactRequiredInternalSpecifications(state: InspectionFixtureState): boolean {
  const actual = state.internalTests;
  const expected = deterministicFixtureContract.requiredInternalSpecifications;
  if (
    actual.length !== expected.length
    || new Set(actual.map((item) => item.id)).size !== actual.length
    || new Set(expected.map((item) => item.id)).size !== expected.length
  ) return false;
  return expected.every((specification) => {
    const item = actual.find((candidate) => candidate.id === specification.id);
    return item !== undefined
      && item.specificationId === specification.specificationId
      && item.required === specification.required
      && item.item === specification.item
      && item.unit === specification.unit
      && (item.hycSpecMin ?? null) === specification.hycSpecMin
      && (item.hycSpecMax ?? null) === specification.hycSpecMax
      && (item.supplierSpecMin ?? null) === specification.supplierSpecMin
      && (item.supplierSpecMax ?? null) === specification.supplierSpecMax;
  });
}

function hasUniqueMatchRelationships(matches: InspectionFixtureState["matches"]): boolean {
  const relationshipKeys = matches.map((match) => JSON.stringify([match.section.trim(), match.allocation.trim()]));
  return new Set(relationshipKeys).size === relationshipKeys.length;
}

/** Derives local-only trace records from authoritative current fixture values. */
export function deriveCanonicalTrace(state: InspectionFixtureState): TraceEventFixture[] {
  const allocationIds = state.receipt.allocations.map((allocation) => allocation.id).join(" / ");
  const sections = state.matches.map((match) => match.section).join(" / ");
  const relations = state.matches.map((match) => `${match.section} ↔ ${match.allocation}`).join(" / ");
  const internalTestIds = state.internalTests.map((item) => item.id).join(" / ");
  const { receiptId, canonicalLot } = state.receipt;
  const { documentId } = state.documentReview;
  const { specVersion } = state;
  return [
    { id: "FX-TRACE-01", order: 1, type: "입고", title: "분할 입고 생성", detail: `${receiptId} → ${allocationIds}` },
    { id: "FX-TRACE-02", order: 2, type: "LOT", title: "정본 LOT 연결", detail: canonicalLot },
    { id: "FX-TRACE-03", order: 3, type: "문서", title: "합성 문서 section", detail: `${documentId} · ${sections}` },
    { id: "FX-TRACE-04", order: 4, type: "매칭", title: "section·allocation 관계", detail: relations },
    { id: "FX-TRACE-05", order: 5, type: "검사", title: "필수 자체검사", detail: internalTestIds },
    { id: "FX-TRACE-06", order: 6, type: "규격", title: "고정될 규격 버전", detail: specVersion },
    { id: "FX-TRACE-07", order: 7, type: "감사", title: "fixture local 결정 근거", detail: `${receiptId} | ${allocationIds} | ${canonicalLot} | ${documentId} | ${relations} | ${internalTestIds} | ${specVersion}` },
  ];
}

function hasCanonicalTrace(state: InspectionFixtureState): boolean {
  const canonical = deriveCanonicalTrace(state);
  return state.trace.length === canonical.length && state.trace.every((event, index) => {
    const expected = canonical[index];
    return event.id === expected.id && event.order === expected.order && event.type === expected.type
      && event.title === expected.title && event.detail === expected.detail;
  });
}

export function isFixtureOnlyCase(state: InspectionFixtureState): boolean {
  const allocationIds = new Set(state.receipt.allocations.map((allocation) => allocation.id));
  return state.fixtureOnly
    && [state.fixtureId, state.documentReview.documentId, state.receipt.receiptId, state.receipt.rawLot, state.receipt.canonicalLot, state.specVersion]
      .every(isFxIdentity)
    && state.receipt.allocations.every((allocation) =>
      [allocation.id, allocation.canonicalLot, allocation.materialLot].every(isFxIdentity),
    )
    && state.matches.every((match) => [match.id, match.section, match.allocation].every(isFxIdentity) && allocationIds.has(match.allocation))
    && state.internalTests.every((item) => [item.id, item.specificationId].every(isFxIdentity))
    && state.trace.every((event) => isFxIdentity(event.id))
    && state.documentReview.fields.every((field) => isFxIdentity(field.id))
    && hasBoundSpecificationIds(state)
    && hasExactRequiredInternalSpecifications(state)
    && sameCalculationPolicy(state.calculationPolicy);
}

function receiptAndBusinessPrerequisiteBlockers(state: InspectionFixtureState): string[] {
  const blockers: string[] = [];
  const { receipt } = state;
  if (!hasTrimmedValue(state.fixtureId) || !hasTrimmedValue(state.caseName) || (state.priority !== "높음" && state.priority !== "보통")) blockers.push("fixture 사례 식별자·이름·우선순위 필요");
  if (!hasTrimmedValue(receipt.supplier)) blockers.push("공급사 필요");
  if (!hasTrimmedValue(receipt.material)) blockers.push("품목 필요");
  if (!receiptDatePattern.test(receipt.receiptDate)) blockers.push("입고일은 YYYY-MM-DD 형식 필요");
  if (!hasTrimmedValue(receipt.unit)) blockers.push("입고 단위 필요");
  if (!receipt.rawLot.trim()) blockers.push("공급사 원 LOT 필요");
  if (!receipt.canonicalLot.trim()) blockers.push("정본 LOT 필요");
  if (!isCanonicalDecimalString(receipt.receivedQuantity)) blockers.push("입고 수량 정본 소수 문자열 필요");
  if (!isCanonicalDecimalString(receipt.allocationQuantity)) blockers.push("배분 수량 정본 소수 문자열 필요");
  if (receipt.allocations.length === 0) blockers.push("입고 배분이 최소 1건 필요");
  if (!hasUniqueNonemptyValues(receipt.allocations.map((allocation) => allocation.id))) blockers.push("입고 배분 ID는 고유한 필수 값이어야 함");
  if (receipt.allocations.some((allocation) => !hasTrimmedValue(allocation.materialLot) || !hasTrimmedValue(allocation.unit) || !hasTrimmedValue(allocation.purpose) || !hasTrimmedValue(allocation.status))) blockers.push("입고 배분 필수 값 필요");
  if (receipt.allocations.some((allocation) => allocation.canonicalLot !== receipt.canonicalLot)) blockers.push("입고 배분 정본 LOT가 입고 정본 LOT와 불일치");
  if (receipt.allocations.some((allocation) => !isCanonicalDecimalString(allocation.quantity))) blockers.push("입고 배분 수량 정본 소수 문자열 필요");
  if (receipt.allocations.some((allocation) => allocation.unit !== receipt.unit)) blockers.push("입고 배분 단위가 입고 단위와 불일치");
  if (receipt.allocations.length > 0 && receipt.allocationQuantity !== receipt.allocations[0].quantity) blockers.push("입고 배분 수량이 첫 번째 allocation 수량과 불일치");
  const allocationSum = sumDecimalStrings(receipt.allocations.map((allocation) => allocation.quantity));
  if (allocationSum === null || compareDecimalStrings(allocationSum, receipt.receivedQuantity) !== 0) blockers.push("입고 배분 수량 합계가 입고 수량과 불일치");
  const allocationIds = new Set(receipt.allocations.map((allocation) => allocation.id));
  if (!hasTrimmedValue(state.documentReview.documentId) || !hasTrimmedValue(state.documentReview.name)) blockers.push("문서 식별자와 이름 필요");
  if (!hasUniqueNonemptyValues(state.documentReview.fields.map((field) => field.id))) blockers.push("문서 필드 ID는 고유한 필수 값이어야 함");
  if (state.documentReview.fields.some((field) => !hasTrimmedValue(field.label) || !hasTrimmedValue(field.warning))) blockers.push("문서 필드 라벨과 경고 필요");
  if (!hasUniqueNonemptyValues(state.matches.map((match) => match.id))) blockers.push("매칭 ID는 고유한 필수 값이어야 함");
  if (!hasUniqueMatchRelationships(state.matches)) blockers.push("매칭 section·allocation 관계는 고유해야 함");
  if (!hasUniqueNonemptyValues(state.internalTests.map((item) => item.id))) blockers.push("자체검사 ID는 고유한 필수 값이어야 함");
  if (!hasUniqueNonemptyValues(state.trace.map((event) => event.id)) || new Set(state.trace.map((event) => event.order)).size !== state.trace.length) blockers.push("trace ID와 순서는 고유해야 함");
  if (state.matches.some((match) => !allocationIds.has(match.allocation))) blockers.push("매칭 allocation 참조가 입고 배분에 없음");
  if (state.matches.some((match) => !isFxIdentity(match.section))) blockers.push("매칭 문서 section은 FX 식별자여야 함");
  if (state.matches.some((match) => !hasTrimmedValue(match.section) || !hasTrimmedValue(match.allocation) || !hasTrimmedValue(match.evidence) || !hasTrimmedValue(match.reason) || !hasTrimmedValue(match.conflict))) blockers.push("매칭 관계 필수 근거·사유·충돌 값 필요");
  if (state.trace.some((event) => !hasTrimmedValue(event.type) || !hasTrimmedValue(event.title) || !hasTrimmedValue(event.detail))) blockers.push("trace 관계 제목과 상세 필요");
  if (!hasBoundSpecificationIds(state)) blockers.push("자체검사 specificationId는 specVersion profile/version과 일치해야 함");
  if (!hasExactRequiredInternalSpecifications(state)) blockers.push("필수 자체검사 정본 규격 계약과 불일치");
  if (!sameCalculationPolicy(state.calculationPolicy)) blockers.push("fixture 계산 정책 근거가 불완전함");
  if (!hasCanonicalTrace(state)) blockers.push("결정적 trace가 현재 fixture 관계와 불일치");
  if (!isDocumentReviewComplete(state)) blockers.push("문서 검토 확정 필요");
  if (!areMatchesConfirmed(state)) blockers.push("section↔allocation 확인 필요");
  if (!areRequiredTestsComplete(state)) blockers.push("자체검사 필수 항목 미완료");
  if (!isFixtureOnlyCase(state)) blockers.push("FX fixture-only 식별자만 허용");
  return blockers;
}

function isSubmittableSourceStatus(status: InspectionFixtureState["workflowStatus"]): boolean {
  return status === "READY_TO_SUBMIT" || status === "RETURNED";
}

export function canSubmit(state: InspectionFixtureState, reason = "fixture submit"): WorkflowGuard {
  const blockers = receiptAndBusinessPrerequisiteBlockers(state);
  if (state.selectedRole !== "INSPECTOR") blockers.push("검사자(INSPECTOR) 역할만 제출할 수 있음");
  if (!reason.trim()) blockers.push("제출 사유 필요");
  if (state.workflowStatus === "SUBMITTED") blockers.push("이미 제출된 fixture는 중복 제출할 수 없음");
  else if (state.workflowStatus === "APPROVED") blockers.push("승인된 fixture는 수정·재제출할 수 없음");
  else if (!isSubmittableSourceStatus(state.workflowStatus)) blockers.push("READY_TO_SUBMIT 또는 RETURNED 상태에서만 제출 가능");
  return { allowed: blockers.length === 0, blockers };
}

export function canReturn(state: InspectionFixtureState, reason: string): WorkflowGuard {
  const blockers: string[] = [];
  if (state.selectedRole !== "LEAD") blockers.push("팀장(LEAD) 역할만 반려할 수 있음");
  if (!reason.trim()) blockers.push("반려 사유 필요");
  if (state.workflowStatus !== "SUBMITTED") blockers.push("제출된 fixture만 반려 가능");
  return { allowed: blockers.length === 0, blockers };
}

export function canApprove(state: InspectionFixtureState, reason: string): WorkflowGuard {
  const blockers = receiptAndBusinessPrerequisiteBlockers(state);
  if (state.selectedRole !== "LEAD") blockers.push("팀장(LEAD) 역할만 승인할 수 있음");
  if (!state.submissionReason?.trim()) blockers.push("제출 사유 필요");
  if (!reason.trim()) blockers.push("검토 사유 필요");
  if (state.workflowStatus !== "SUBMITTED") blockers.push("제출된 fixture만 승인 가능");
  return { allowed: blockers.length === 0, blockers };
}

function derivePreSubmitStatus(state: InspectionFixtureState): InspectionFixtureState["workflowStatus"] {
  if (state.workflowStatus === "RETURNED") return "RETURNED";
  const blockers = receiptAndBusinessPrerequisiteBlockers(state);
  if (blockers.length === 0) return "READY_TO_SUBMIT";
  return blockers.every((blocker) => blocker === "자체검사 필수 항목 미완료") ? "INTERNAL_TEST_PENDING" : "REVIEW_REQUIRED";
}

function withDerivedPreSubmitStatus(state: InspectionFixtureState): InspectionFixtureState {
  return { ...state, workflowStatus: derivePreSubmitStatus(state) };
}

function resetInternalTest(item: InternalTestFixture, samples: string[]): InternalTestFixture {
  return { ...item, samples, aggregate: null, completed: false, hycDecision: "대기", holdReason: "INTERNAL_TEST_PENDING" };
}

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    for (const nested of Object.values(value as Record<string, unknown>)) deepFreeze(nested);
    Object.freeze(value);
  }
  return value;
}

/** Builds only a submitted LEAD-authoritative, evidence-complete deterministic record. */
function buildFrozenSnapshot(state: InspectionFixtureState): FrozenFixtureSnapshot | null {
  if (
    !state.submissionReason?.trim()
    || !state.reviewerReason?.trim()
    || state.workflowStatus !== "SUBMITTED"
    || state.selectedRole !== "LEAD"
    || !canApprove(state, state.reviewerReason).allowed
    || receiptAndBusinessPrerequisiteBlockers(state).length > 0
    || !isDocumentReviewComplete(state)
    || !areMatchesConfirmed(state)
    || !areRequiredTestsComplete(state)
  ) return null;
  const requiredTests = state.internalTests.filter((item) => item.required);
  const decisions = requiredTests.map((item) => item.hycDecision);
  if (decisions.some((decision) => decision === "대기")) return null;
  return deepFreeze({
    fixtureOnly: true,
    fixtureId: state.fixtureId,
    caseName: state.caseName,
    priority: state.priority,
    receipt: {
      receiptId: state.receipt.receiptId,
      supplier: state.receipt.supplier,
      material: state.receipt.material,
      receiptDate: state.receipt.receiptDate,
      rawLot: state.receipt.rawLot,
      canonicalLot: state.receipt.canonicalLot,
      receivedQuantity: state.receipt.receivedQuantity,
      allocationQuantity: state.receipt.allocationQuantity,
      unit: state.receipt.unit,
    },
    allocations: state.receipt.allocations.map(({ id, canonicalLot, materialLot, quantity, unit, purpose, status }) => ({ id, canonicalLot, materialLot, quantity, unit, purpose, status })),
    document: { documentId: state.documentReview.documentId, name: state.documentReview.name },
    specVersion: state.specVersion,
    confirmedMatches: state.matches.map(({ id, section, allocation, evidence, reason, conflict }) => ({ id, section, allocation, evidence, reason, conflict, confirmed: true as const })),
    documentFinals: state.documentReview.fields.filter((field) => field.required).map((field) => ({
      id: field.id,
      label: field.label,
      kind: field.kind,
      unit: field.unit,
      originalValue: field.originalValue,
      ocrCandidate: field.ocrValue,
      manualValue: field.manualValue,
      confidence: field.confidence,
      warning: field.warning,
      finalValue: field.finalValue!.trim(),
      finalSource: field.finalSource!,
      reason: field.reason!.trim(),
    })),
    requiredInternalRecords: requiredTests.map((item) => ({
      id: item.id,
      item: item.item,
      required: true as const,
      specificationId: item.specificationId,
      unit: item.unit,
      samples: [...item.samples],
      aggregate: item.aggregate!,
      hycSpecMin: item.hycSpecMin ?? null,
      hycSpecMax: item.hycSpecMax ?? null,
      supplierSpecMin: item.supplierSpecMin ?? null,
      supplierSpecMax: item.supplierSpecMax ?? null,
      supplierDecision: item.supplierDecision,
      hycDecision: item.hycDecision as Exclude<InternalTestFixture["hycDecision"], "대기">,
      holdReason: item.holdReason,
    })),
    calculationPolicy: { ...state.calculationPolicy },
    overallDecision: decisions.includes("부적합") ? "부적합" : "적합",
    submissionReason: state.submissionReason.trim(),
    approvalReason: state.reviewerReason.trim(),
    simulatedSubmitterRole: "INSPECTOR",
    simulatedApproverRole: "LEAD",
    trace: deriveCanonicalTrace(state),
  });
}

export function reduceInspection(state: InspectionFixtureState, action: InspectionAction): InspectionFixtureState {
  if (state.workflowStatus === "APPROVED") return state;
  if (action.type === "setRole") return { ...state, selectedRole: action.role };
  if (state.workflowStatus === "SUBMITTED") {
    if (action.type === "return") {
      const guard = canReturn(state, action.reason);
      return guard.allowed ? { ...state, workflowStatus: "RETURNED", reviewerReason: action.reason.trim() } : state;
    }
    if (action.type === "approve") {
      const authoritativeReviewerState = { ...state, reviewerReason: action.reason.trim() };
      const guard = canApprove(authoritativeReviewerState, authoritativeReviewerState.reviewerReason);
      const frozenSnapshot = guard.allowed ? buildFrozenSnapshot(authoritativeReviewerState) : null;
      return frozenSnapshot ? deepFreeze({ ...authoritativeReviewerState, workflowStatus: "APPROVED", frozenSnapshot }) : state;
    }
    return state;
  }
  if (action.type === "setReceiptField") {
    if (action.field === "allocationQuantity") {
      return withDerivedPreSubmitStatus({ ...state, receipt: { ...state.receipt, allocationQuantity: action.value, allocations: state.receipt.allocations.map((allocation, index) => index === 0 ? { ...allocation, quantity: action.value } : allocation) } });
    }
    return withDerivedPreSubmitStatus({ ...state, receipt: { ...state.receipt, [action.field]: action.value } });
  }
  if (action.type === "finalizeDocumentReview") {
    return withDerivedPreSubmitStatus({ ...state, documentReview: { ...state.documentReview, fields: state.documentReview.fields.map((field) => field.id === action.fieldId ? { ...field, finalSource: action.source, finalValue: action.value, reason: action.reason } : field) } });
  }
  if (action.type === "confirmMatch") return withDerivedPreSubmitStatus({ ...state, matches: state.matches.map((match) => match.id === action.matchId ? { ...match, confirmed: true } : match) });
  if (action.type === "setInternalSamples") return withDerivedPreSubmitStatus({ ...state, internalTests: state.internalTests.map((item) => item.id === action.itemId ? resetInternalTest(item, action.samples) : item) });
  if (action.type === "confirmInternalTest") {
    const item = state.internalTests.find((candidate) => candidate.id === action.itemId);
    const semantics = item ? getInternalTestSemantics(item) : null;
    if (!item || !semantics?.completed) return state;
    return withDerivedPreSubmitStatus({ ...state, internalTests: state.internalTests.map((candidate) => candidate.id === action.itemId ? { ...candidate, ...semantics, holdReason: "" } : candidate) });
  }
  if (action.type === "submit") {
    const guard = canSubmit(state, action.reason);
    return guard.allowed ? { ...state, workflowStatus: "SUBMITTED", submissionReason: action.reason.trim() } : state;
  }
  // Return and approve are valid only in the explicit SUBMITTED branch above.
  return state;
}
