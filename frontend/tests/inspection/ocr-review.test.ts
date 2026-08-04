import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import type { ExtractionRun } from "../../src/lib/api/p3";
import { buildReviewFields, createOcrReviewDrafts, reviewPanelVisibility, validateOcrReview } from "../../src/lib/inspection/ocr-review";

const run: ExtractionRun = {
  run_id: "00000000-0000-4000-8000-000000000001",
  document_id: "00000000-0000-4000-8000-000000000002",
  status: "REVIEW_REQUIRED",
  version: 1,
  provider_name: "local-paddleocr",
  conflicts: [],
  fields: [
    { field_id: "00000000-0000-4000-8000-000000000011", field_key: "OCR_TEXT_0001", source_field_key: "OCR_TEXT_0001", original_text: "97.50", ocr_text: "97.50", final_text: null, source: null, reason: null, confidence: "0.90", page_number: 1, bbox: { left: 0, top: 0, right: 1, bottom: 1 }, required: true, status: "REVIEW_REQUIRED", mapping_disposition: null, mapped_field_key: null, review_reasons: ["HUMAN_REVIEW_REQUIRED"], provenance: {} },
    { field_id: "00000000-0000-4000-8000-000000000012", field_key: "OCR_TEXT_0002", source_field_key: "OCR_TEXT_0002", original_text: "note", ocr_text: "note", final_text: null, source: null, reason: null, confidence: "0.70", page_number: 2, bbox: { left: 0, top: 0, right: 1, bottom: 1 }, required: true, status: "REVIEW_REQUIRED", mapping_disposition: null, mapped_field_key: null, review_reasons: ["LOW_CONFIDENCE"], provenance: {} },
  ],
};

describe("local OCR review helpers", () => {
  it("creates no default disposition, mapping, or reason", () => {
    const drafts = createOcrReviewDrafts(run);
    expect(Object.values(drafts).map(({ mappingDisposition, mappedFieldKey, reason }) => [mappingDisposition, mappedFieldKey, reason])).toEqual([["", "", ""], ["", "", ""]]);
    expect(validateOcrReview(run, drafts, ["CACL2_PURITY", "MOISTURE"])).toEqual(expect.arrayContaining([
      "OCR_TEXT_0001: MAP 또는 UNMAPPED 선택 필요",
      "OCR_TEXT_0002: MAP 또는 UNMAPPED 선택 필요",
    ]));
  });

  it("blocks duplicate/out-of-spec mappings and noncanonical string values", () => {
    const drafts = createOcrReviewDrafts(run);
    drafts[run.fields[0].field_id] = { finalText: "97.50", mappingDisposition: "MAP", mappedFieldKey: "CACL2_PURITY", reason: "checked" };
    drafts[run.fields[1].field_id] = { finalText: "1e2", mappingDisposition: "MAP", mappedFieldKey: "CACL2_PURITY", reason: "checked" };
    expect(validateOcrReview(run, drafts, ["CACL2_PURITY", "MOISTURE"])).toEqual(expect.arrayContaining([
      "CACL2_PURITY: 중복 매핑 금지",
      "OCR_TEXT_0002: 정본 유한 소수 문자열 필요",
    ]));
  });

  it("builds explicit mapped and unmapped payloads with string values", () => {
    const drafts = createOcrReviewDrafts(run);
    drafts[run.fields[0].field_id] = { finalText: "97.50", mappingDisposition: "MAP", mappedFieldKey: "CACL2_PURITY", reason: "checked" };
    drafts[run.fields[1].field_id] = { finalText: "note", mappingDisposition: "UNMAPPED", mappedFieldKey: "", reason: "checked" };
    const fields = buildReviewFields(run, drafts);
    expect(fields[0]).toMatchObject({ field_id: run.fields[0].field_id, field_key: "OCR_TEXT_0001", final_text: "97.50", mapping_disposition: "MAP", mapped_field_key: "CACL2_PURITY" });
    expect(typeof fields[0].final_text).toBe("string");
    expect(fields[1]).toMatchObject({ mapping_disposition: "UNMAPPED", mapped_field_key: null });
  });

  it("preserves edited non-local review drafts and blocks an empty reason", () => {
    const fixtureRun: ExtractionRun = { ...run, provider_name: "FixtureExtractionProvider" };
    const drafts = createOcrReviewDrafts(fixtureRun);
    drafts[fixtureRun.fields[0].field_id] = {
      ...drafts[fixtureRun.fields[0].field_id],
      finalText: "edited fixture text",
      reason: "human-reviewed generated fixture",
    };
    drafts[fixtureRun.fields[1].field_id] = {
      ...drafts[fixtureRun.fields[1].field_id],
      reason: "",
    };
    expect(validateOcrReview(fixtureRun, drafts, [])).toContain("OCR_TEXT_0002: 검토 사유 필요");
    drafts[fixtureRun.fields[1].field_id].reason = "reviewed generated note";
    const fields = buildReviewFields(fixtureRun, drafts);
    expect(fields[0]).toMatchObject({
      field_id: fixtureRun.fields[0].field_id,
      final_text: "edited fixture text",
      reason: "human-reviewed generated fixture",
    });
    expect(fields[0]).not.toHaveProperty("mapping_disposition");
    expect(validateOcrReview(fixtureRun, drafts, [])).toEqual([]);
  });

  it("shows persisted review for every non-public run while retaining the fixture reducer stage", () => {
    const fixtureRun: ExtractionRun = { ...run, provider_name: "FixtureExtractionProvider" };
    expect(reviewPanelVisibility(false, run)).toEqual({ persisted: true, synthetic: false });
    expect(reviewPanelVisibility(false, fixtureRun)).toEqual({ persisted: true, synthetic: true });
    expect(reviewPanelVisibility(true, run)).toEqual({ persisted: false, synthetic: true });
    expect(reviewPanelVisibility(true, null)).toEqual({ persisted: false, synthetic: true });
  });

  it("renders persisted fields without automatic confirmation and resumes by UUID only", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    expect(workspace).toContain('aria-label="persisted local OCR review table"');
    expect(workspace).toContain("extractionRun.fields.map");
    expect(workspace).toContain("getExtractionRun(session.session_handle, ids.documentId, ids.runId)");
    expect(workspace).toContain('JSON.stringify({ documentId: run.document_id, runId: run.run_id })');
    expect(workspace).not.toContain("useEffect(() => void confirmReview");
    expect(workspace).not.toMatch(/sessionStorage\.setItem\([^\n]*(ocr_text|finalText|fields)/);
    expect(workspace).toContain("const reviewPanels = reviewPanelVisibility(publicDemo, extractionRun);");
    expect(workspace).toContain("reviewPanels.persisted");
    expect(workspace).toContain("reviewPanels.synthetic");
    const api = readFileSync(resolve(process.cwd(), "src/lib/api/p3.ts"), "utf8");
    expect(api).toContain("const fields = buildReviewFields(run, drafts);");
    expect(api).not.toContain("P3 synthetic fixture reviewed in API-backed UI");
  });
});
