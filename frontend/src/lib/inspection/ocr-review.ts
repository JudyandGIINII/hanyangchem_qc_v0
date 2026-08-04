import type { ExtractionRun } from "../api/p3";
import { isCanonicalDecimalString } from "./workflow";

export type MappingDisposition = "" | "MAP" | "UNMAPPED";

export type OcrReviewDraft = {
  finalText: string;
  mappingDisposition: MappingDisposition;
  mappedFieldKey: string;
  reason: string;
};

export type OcrReviewDrafts = Record<string, OcrReviewDraft>;

export function reviewPanelVisibility(publicDemo: boolean, run: ExtractionRun | null) {
  return {
    persisted: !publicDemo && run !== null,
    synthetic: publicDemo || run?.provider_name !== "local-paddleocr",
  };
}

export function createOcrReviewDrafts(run: ExtractionRun): OcrReviewDrafts {
  return Object.fromEntries(run.fields.map((field) => [field.field_id, {
    finalText: field.final_text ?? field.ocr_text,
    mappingDisposition: field.mapping_disposition ?? "",
    mappedFieldKey: field.mapped_field_key ?? "",
    reason: field.reason ?? "",
  }]));
}

export function validateOcrReview(
  run: ExtractionRun | null,
  drafts: OcrReviewDrafts,
  mappingItemCodes: readonly string[],
): string[] {
  if (!run) return ["OCR 추출 결과가 필요합니다."];
  const localOcr = run.provider_name === "local-paddleocr";
  const blockers: string[] = [];
  const mapped = new Set<string>();
  for (const field of run.fields) {
    const draft = drafts[field.field_id];
    if (!draft || !draft.reason.trim()) blockers.push(`${field.source_field_key}: 검토 사유 필요`);
    if (!draft || !draft.finalText) blockers.push(`${field.source_field_key}: 최종 문자열 필요`);
    if (!localOcr || !draft) continue;
    if (draft.mappingDisposition !== "MAP" && draft.mappingDisposition !== "UNMAPPED") {
      blockers.push(`${field.source_field_key}: MAP 또는 UNMAPPED 선택 필요`);
      continue;
    }
    if (draft.mappingDisposition === "UNMAPPED") {
      if (draft.mappedFieldKey) blockers.push(`${field.source_field_key}: UNMAPPED 대상 금지`);
      continue;
    }
    if (!mappingItemCodes.includes(draft.mappedFieldKey)) {
      blockers.push(`${field.source_field_key}: 현재 규격 항목 선택 필요`);
    } else if (mapped.has(draft.mappedFieldKey)) {
      blockers.push(`${draft.mappedFieldKey}: 중복 매핑 금지`);
    } else {
      mapped.add(draft.mappedFieldKey);
    }
    if (!isCanonicalDecimalString(draft.finalText)) {
      blockers.push(`${field.source_field_key}: 정본 유한 소수 문자열 필요`);
    }
  }
  return blockers;
}

export function buildReviewFields(run: ExtractionRun, drafts: OcrReviewDrafts) {
  const localOcr = run.provider_name === "local-paddleocr";
  return run.fields.map((field) => {
    const draft = drafts[field.field_id];
    if (!draft) throw new Error("OCR review draft missing");
    return {
      field_id: field.field_id,
      field_key: field.source_field_key,
      manual_text: draft.finalText === field.ocr_text ? null : draft.finalText,
      final_text: draft.finalText,
      source: draft.finalText === field.ocr_text ? "OCR" as const : "MANUAL" as const,
      reason: draft.reason,
      logic_conflict: false,
      ...(localOcr ? {
        mapping_disposition: draft.mappingDisposition as "MAP" | "UNMAPPED",
        mapped_field_key: draft.mappingDisposition === "MAP" ? draft.mappedFieldKey : null,
      } : {}),
    };
  });
}
