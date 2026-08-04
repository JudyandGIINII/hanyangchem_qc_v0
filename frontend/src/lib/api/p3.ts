import type { components } from "./generated";
import { apiRequest } from "./client";
import { buildReviewFields } from "../inspection/ocr-review";
import type { OcrReviewDrafts } from "../inspection/ocr-review";

export type FixtureContext = components["schemas"]["FixtureContextResponse"];
export type Intake = components["schemas"]["IntakeResponse"];
export type DocumentRecord = components["schemas"]["DocumentResponse"];
export type ExtractionRun = components["schemas"]["ExtractionRunResponse"];
export type Inspection = components["schemas"]["InspectionResponse"];
export type LotTrace = components["schemas"]["LotTraceResponse"];
export type FixtureRole = "INSPECTOR" | "LEAD" | "ADMIN";

const jsonHeaders = { "Content-Type": "application/json" };

export async function fixtureSession(role: FixtureRole) {
  const principal = role === "LEAD" ? "p3-lead" : role === "ADMIN" ? "p3-admin" : "p3-inspector";
  return (await apiRequest<components["schemas"]["LocalSessionResponse"]>(
    "/api/v1/local-auth/sessions",
    { method: "POST", headers: jsonHeaders, body: JSON.stringify({ fixture_principal: principal }) },
  )).body;
}

export async function fixtureContext(sessionHandle: string) {
  return (await apiRequest<FixtureContext>("/api/v1/fixtures/p3/context", {}, sessionHandle)).body;
}

export async function createIntake(sessionHandle: string, context: FixtureContext, marker: string) {
  return (await apiRequest<Intake>("/api/v1/intakes", {
    method: "POST",
    headers: { ...jsonHeaders, "Idempotency-Key": `web-intake-${marker}` },
    body: JSON.stringify({
      supplier_id: context.supplier_id,
      material_id: context.material_id,
      model_id: context.model_id,
      inbound_no: `P3-WEB-${marker}`,
      receipt_date: "2026-08-01",
      supplier_lot_no: `P3-WEB-LOT-${marker}`,
      quantity: "100.00",
      quantity_unit: "kg",
    }),
  }, sessionHandle)).body;
}

export async function uploadDocument(sessionHandle: string, file: File) {
  return (await apiRequest<DocumentRecord>("/api/v1/documents", {
    method: "POST",
    headers: { "X-Filename": file.name, "Content-Type": file.type || "application/octet-stream" },
    body: file,
  }, sessionHandle)).body;
}

export async function extractDocument(sessionHandle: string, documentId: string) {
  return (await apiRequest<ExtractionRun>(`/api/v1/documents/${documentId}/extractions`, { method: "POST" }, sessionHandle)).body;
}

export async function getExtractionRun(sessionHandle: string, documentId: string, runId: string) {
  return (await apiRequest<ExtractionRun>(`/api/v1/documents/${documentId}/extractions/${runId}`, {}, sessionHandle)).body;
}

export async function confirmReview(sessionHandle: string, documentId: string, run: ExtractionRun, allocationId: string, drafts: OcrReviewDrafts, specVersionId?: string) {
  if (run.provider_name === "local-paddleocr" && !specVersionId) throw new Error("Explicit local OCR review is required");
  const fields = buildReviewFields(run, drafts);
  return (await apiRequest<ExtractionRun>(`/api/v1/documents/${documentId}/reviews/${run.run_id}`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(run.version) },
    body: JSON.stringify({
      allocation_id: allocationId,
      spec_version_id: run.provider_name === "local-paddleocr" ? specVersionId : undefined,
      fields,
    }),
  }, sessionHandle)).body;
}

export async function createInspection(sessionHandle: string, allocationId: string, runId: string, marker: string) {
  return (await apiRequest<{ inspection_id: string }>("/api/v1/inspections", {
    method: "POST",
    headers: { ...jsonHeaders, "Idempotency-Key": `web-inspection-${marker}` },
    body: JSON.stringify({ allocation_id: allocationId, extraction_run_id: runId }),
  }, sessionHandle)).body;
}

export async function getInspection(sessionHandle: string, inspectionId: string) {
  return (await apiRequest<Inspection>(`/api/v1/inspections/${inspectionId}`, {}, sessionHandle)).body;
}

export async function putInternalResult(sessionHandle: string, inspection: Inspection) {
  const moisture = inspection.judgments.find((item) => item.item_code === "MOISTURE");
  if (!moisture) throw new Error("MOISTURE spec item missing");
  return (await apiRequest<Inspection>(`/api/v1/inspections/${inspection.inspection_id}/internal-results`, {
    method: "PUT",
    headers: { ...jsonHeaders, "If-Match": String(inspection.version) },
    body: JSON.stringify({ results: [{ spec_item_id: moisture.spec_item_id, values: ["0.10", "0.12", "0.11"] }] }),
  }, sessionHandle)).body;
}

export async function submitInspection(sessionHandle: string, inspection: Inspection) {
  return (await apiRequest<Inspection>(`/api/v1/inspections/${inspection.inspection_id}/submit`, {
    method: "POST", headers: { "If-Match": String(inspection.version) },
  }, sessionHandle)).body;
}

export async function approveInspection(sessionHandle: string, inspection: Inspection, marker: string) {
  return (await apiRequest<Inspection>(`/api/v1/inspections/${inspection.inspection_id}/approvals`, {
    method: "POST",
    headers: { ...jsonHeaders, "If-Match": String(inspection.version), "Idempotency-Key": `web-approve-${marker}` },
    body: JSON.stringify({ action: "APPROVE", reason: null }),
  }, sessionHandle)).body;
}

export async function createLineage(sessionHandle: string, inspection: Inspection, kind: "revisions" | "retests") {
  return (await apiRequest<Inspection>(`/api/v1/inspections/${inspection.inspection_id}/${kind}`, {
    method: "POST", headers: jsonHeaders, body: JSON.stringify({ reason: `P3 fixture ${kind}` }),
  }, sessionHandle)).body;
}

export async function getTrace(sessionHandle: string, lotId: string) {
  return (await apiRequest<LotTrace>(`/api/v1/lots/${lotId}/trace`, {}, sessionHandle)).body;
}
