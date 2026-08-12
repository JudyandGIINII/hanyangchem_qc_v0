"use client";

import { useCallback, useEffect, useMemo, useReducer, useState } from "react";
import type { ReactNode } from "react";

import { createInspectionFixtureState } from "../../lib/inspection/fixtures";
import { createOcrReviewDrafts, reviewPanelVisibility, validateOcrReview } from "../../lib/inspection/ocr-review";
import type { OcrReviewDrafts } from "../../lib/inspection/ocr-review";
import type { DocumentSource, InspectionFixtureState, ReceiptFixture, WorkflowRole } from "../../lib/inspection/types";
import { areMatchesConfirmedForFixture, areRequiredTestsCompleteForFixture, canApprove, canSubmit, getInternalTestSemantics, isCanonicalDecimalString, isDocumentReviewCompleteForFixture, reduceInspection } from "../../lib/inspection/workflow";
import { ApiError } from "../../lib/api/client";
import { approveInspection, confirmReview, createInspection, createIntake, createLineage, extractDocument, fixtureContext, fixtureSession, getExtractionRun, getInspection, getTrace, putInternalResult, returnInspection, submitInspection, uploadDocument } from "../../lib/api/p3";
import type { DocumentRecord, ExtractionRun, FixtureContext, Inspection, Intake, LotTrace } from "../../lib/api/p3";
import { canUseBackend, PUBLIC_DEMO_MODE } from "../../lib/public-demo";
import { ReportPanel } from "../reports/ReportPanel";
import { StatisticsPanel } from "../statistics/StatisticsPanel";
import { NonconformanceWorkspace } from "../nonconformance/NonconformanceWorkspace";

const stages = ["목록", "입고/LOT", "문서 검토", "매칭", "자체검사", "제출", "팀장 검토", "LOT 추적", "부적합", "보고서·통계"] as const;
type Stage = (typeof stages)[number];
const statusCopy: Record<InspectionFixtureState["workflowStatus"], string> = { REVIEW_REQUIRED: "검토 필요", INTERNAL_TEST_PENDING: "자체검사 대기", READY_TO_SUBMIT: "제출 준비", SUBMITTED: "팀장 검토 대기", RETURNED: "반려됨", APPROVED: "승인·동결" };
const serverStatusCopy: Record<string, string> = {
  DRAFT: "초안",
  DOCUMENT_PENDING: "문서 대기",
  MATCH_REVIEW: "매칭 검토",
  SUPPLIER_REVIEW: "공급사 결과 검토",
  INTERNAL_TEST_PENDING: "자체검사 대기",
  READY_FOR_REVIEW: "제출 준비",
  LEAD_REVIEW: "팀장 검토 대기",
  RETURNED: "반려",
  ACCEPTED: "승인 완료",
  REJECTED: "부적합 확정",
  RETEST: "재검사",
  SPECIAL_ACCEPTED: "특채 승인",
  ON_HOLD: "보류",
  CLOSED: "종결",
  CANCELLED: "취소",
};

function Label({ children, htmlFor, required = false }: { children: ReactNode; htmlFor: string; required?: boolean }) { return <label className="field-label" htmlFor={htmlFor}>{children}{required ? <span aria-label="필수"> *</span> : null}</label>; }
function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "danger" | "success" }) { return <p className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined}>{children}</p>; }

export function InspectionWorkspace({ publicDemo = PUBLIC_DEMO_MODE }: { publicDemo?: boolean }) {
  const [state, dispatch] = useReducer(reduceInspection, undefined, createInspectionFixtureState);
  const [active, setActive] = useState<Stage>("목록");
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [submitReason, setSubmitReason] = useState("FX fixture 제출 사유");
  const [reviewReason, setReviewReason] = useState("FX fixture 검토 사유");
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [sessionHandles, setSessionHandles] = useState<Partial<Record<WorkflowRole, string>>>({});
  const [context, setContext] = useState<FixtureContext | null>(null);
  const [intakeRecord, setIntakeRecord] = useState<Intake | null>(null);
  const [documentRecord, setDocumentRecord] = useState<DocumentRecord | null>(null);
  const [extractionRun, setExtractionRun] = useState<ExtractionRun | null>(null);
  const [ocrReviewDrafts, setOcrReviewDrafts] = useState<OcrReviewDrafts>({});
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const [trace, setTrace] = useState<LotTrace | null>(null);
  const [lineage, setLineage] = useState<Inspection[]>([]);
  const [apiMessage, setApiMessage] = useState(publicDemo ? "공개 합성 데모 · 서버 연결 없음" : "P3 fixture API session 준비 중");
  const [busy, setBusy] = useState(false);
  const [marker] = useState(() => `${Date.now()}`);
  const workflowStatus = inspection
    ? `${serverStatusCopy[inspection.status] ?? "서버 상태"} · ${inspection.status}`
    : publicDemo
      ? `합성 로컬 상태 · ${statusCopy[state.workflowStatus]}`
      : `검사 생성 전 · ${statusCopy[state.workflowStatus]}`;
  const frozen = state.workflowStatus === "APPROVED";
  const mutationLocked = state.workflowStatus === "SUBMITTED" || frozen;
  const reviewComplete = isDocumentReviewCompleteForFixture(state);
  const matchComplete = areMatchesConfirmedForFixture(state);
  const internalComplete = areRequiredTestsCompleteForFixture(state);
  const submitGuard = canSubmit(state, submitReason);
  const approveGuard = canApprove(state, reviewReason);
  const ocrReviewBlockers = extractionRun ? validateOcrReview(extractionRun, ocrReviewDrafts, context?.mapping_item_codes ?? []) : [];
  const reviewPanels = reviewPanelVisibility(publicDemo, extractionRun);
  const receiptErrors = useMemo(() => ({
    supplier: state.receipt.supplier.trim() ? "" : "공급사를 입력하세요.",
    material: state.receipt.material.trim() ? "" : "품목을 입력하세요.",
    receiptDate: /^\d{4}-\d{2}-\d{2}$/.test(state.receipt.receiptDate) ? "" : "입고일은 YYYY-MM-DD 형식으로 입력하세요.",
    rawLot: state.receipt.rawLot.trim() ? "" : "공급사 원 LOT를 입력하세요.",
    canonicalLot: state.receipt.canonicalLot.trim() ? "" : "정본 LOT를 입력하세요.",
    receivedQuantity: isCanonicalDecimalString(state.receipt.receivedQuantity) ? "" : "수량은 정본 소수 문자열(예: 1250.50)만 허용합니다.",
    allocationQuantity: isCanonicalDecimalString(state.receipt.allocationQuantity) ? "" : "배분 수량은 정본 소수 문자열만 허용합니다.",
    unit: state.receipt.unit.trim() ? "" : "입고 단위를 입력하세요.",
  }), [state.receipt]);
  // Statistics default to the current KST month, which is the calendar the backend
  // buckets on. Deriving it here rather than hardcoding a window keeps the panel
  // showing the period a user would expect on the day they open it.
  const reportPeriod = useMemo(() => {
    const now = new Date();
    const seoul = new Date(now.getTime() + 9 * 60 * 60 * 1000);
    const year = seoul.getUTCFullYear();
    const month = seoul.getUTCMonth();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return {
      start: iso(new Date(Date.UTC(year, month, 1))),
      end: iso(new Date(Date.UTC(year, month + 1, 0))),
    };
  }, []);
  const selected = (state.caseName.includes(query) || state.fixtureId.includes(query) || state.receipt.canonicalLot.includes(query)) && (filter === "ALL" || filter === state.workflowStatus);
  const go = (stage: Stage) => setActive(stage);
  const tokenFor = (role = state.selectedRole) => sessionHandles[role];
  const runApi = useCallback(async (label: string, action: () => Promise<void>) => {
    if (!canUseBackend(publicDemo)) {
      setApiMessage("공개 합성 데모 · 서버 연결 없음");
      return;
    }
    setBusy(true);
    try {
      await action();
      setApiMessage(`${label} 완료`);
    } catch (error) {
      setApiMessage(error instanceof ApiError ? `API ${error.status}: ${error.message}` : `${label}: ${String(error)}`);
    } finally {
      setBusy(false);
    }
  }, [publicDemo]);
  useEffect(() => {
    if (!canUseBackend(publicDemo)) return;
    void runApi("fixture session", async () => {
      const session = await fixtureSession("INSPECTOR");
      setSessionHandles({ INSPECTOR: session.session_handle });
      setContext(await fixtureContext(session.session_handle));
      const resumeKey = "hyc-local-ocr-resume-v1";
      const saved = window.sessionStorage.getItem(resumeKey);
      if (saved) {
        const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
        let ids: { documentId?: unknown; runId?: unknown };
        try {
          ids = JSON.parse(saved) as { documentId?: unknown; runId?: unknown };
        } catch {
          window.sessionStorage.removeItem(resumeKey);
          return;
        }
        if (typeof ids.documentId !== "string" || typeof ids.runId !== "string" || !uuid.test(ids.documentId) || !uuid.test(ids.runId)) {
          window.sessionStorage.removeItem(resumeKey);
          return;
        }
        try {
          const run = await getExtractionRun(session.session_handle, ids.documentId, ids.runId);
          setExtractionRun(run);
          setOcrReviewDrafts(createOcrReviewDrafts(run));
        } catch {
          window.sessionStorage.removeItem(resumeKey);
        }
      }
    });
  // The bootstrap is intentionally one-shot; subsequent role sessions are server-created on demand.
  }, [publicDemo, runApi]);
  const switchFixtureRole = (role: WorkflowRole) => {
    if (!canUseBackend(publicDemo)) {
      dispatch({ type: "setRole", role });
      return;
    }
    void runApi(`role ${role}`, async () => {
      let sessionHandle = sessionHandles[role];
      if (!sessionHandle) {
        sessionHandle = (await fixtureSession(role)).session_handle;
        setSessionHandles((current) => ({ ...current, [role]: sessionHandle }));
      }
      dispatch({ type: "setRole", role });
    });
  };
  const finishField = (id: string, source: DocumentSource, value: string, fallback: string) => {
    const typedReason = reasons[id]?.trim();
    const reason = typedReason || fallback;
    setReasons((current) => ({ ...current, [id]: reason }));
    dispatch({ type: "finalizeDocumentReview", fieldId: id, source, value, reason });
  };
  const updateOcrDraft = (fieldId: string, patch: Partial<OcrReviewDrafts[string]>) => setOcrReviewDrafts((current) => ({ ...current, [fieldId]: { ...current[fieldId], ...patch } }));
  const editableFields: Array<[Exclude<keyof ReceiptFixture, "allocations">, string, boolean]> = [["supplier", "공급사", true], ["material", "품목", true], ["receiptDate", "입고일", true], ["rawLot", "공급사 원 LOT", true], ["canonicalLot", "정본 LOT", true], ["receivedQuantity", "입고 수량", true], ["allocationQuantity", "배분 수량", true], ["unit", "단위", true]];

  return <main className="workspace-shell">
    <aside className="sidebar" aria-label="주요 탐색"><div className="brand"><span className="brand-mark" aria-hidden="true">H</span><span>HANYANG<br /><strong>QUALITY</strong></span></div><p className="nav-caption">수입 검사 워크스페이스</p><nav aria-label="검사 단계"><ol className="stage-nav">{stages.map((stage, index) => <li key={stage}><button type="button" className={active === stage ? "stage-link active" : "stage-link"} aria-current={active === stage ? "step" : undefined} onClick={() => go(stage)}><span>{String(index + 1).padStart(2, "0")}</span>{stage}</button></li>)}</ol></nav><div className="sidebar-foot"><span className="fixture-chip">{publicDemo ? "FIXTURE / PUBLIC" : "FIXTURE / LOCAL"}</span><p>역할 시뮬레이션<br />실제 인증 아님</p></div></aside>
    <section className="content-area">
      <header className="topbar"><div><p className="eyebrow">INCOMING QUALITY CONTROL</p><h1>입고 검사 운영</h1></div><div className="topbar-actions"><span className="status-badge" data-testid="workflow-status-badge">{workflowStatus}</span><span className="user-label">{state.selectedRole} · 역할 시뮬레이션</span></div></header>
      <div className="fixture-banner" role="status"><strong>{publicDemo ? "공개 합성 데모" : "LOCAL-ONLY OCR"}</strong><span>{publicDemo ? "서버 연결 없음 · 합성 fixture와 local reducer만 사용 · 실제 문서 아님 · 서버 저장 없음." : "로컬 PDF · 로컬 OCR 모델 · PostgreSQL/API 정본 · 외부 OCR/AI 전송 없음."}</span></div>
      <section className="case-header" aria-label="선택된 검사 건"><div><p className="eyebrow" data-testid="inspection-id">{inspection?.inspection_id ?? state.fixtureId}</p><h2>{context?.material_name ?? state.caseName}</h2>{publicDemo ? <p>합성 로컬 상태 <strong data-testid="server-status">{statusCopy[state.workflowStatus]}</strong> · 정본 LOT <strong data-testid="lot-id">{state.receipt.canonicalLot}</strong></p> : <p>실제 서버 상태 <strong data-testid="server-status">{inspection?.status ?? "SESSION_READY"}</strong> · 정본 LOT <strong data-testid="lot-id">{inspection?.material_lot_id ?? intakeRecord?.material_lot_id ?? "미생성"}</strong></p>}</div><div className="case-meta"><span className="priority">{apiMessage}</span><span>규격 {inspection?.spec_version_id ?? context?.spec_version_id ?? state.specVersion}</span></div></section>
      {publicDemo ? <section className="form-card" aria-label="공개 합성 데모 경계"><p className="eyebrow">PUBLIC SYNTHETIC FEEDBACK DEMO</p><h2>읽기 전용 서버 경계</h2><Notice>이 공개 화면은 합성 fixture와 브라우저의 local reducer만 시뮬레이션합니다. 실제 문서가 없고 백엔드·DB·worker·OCR·모델에 연결하지 않으며 서버에 저장하지 않습니다.</Notice></section> : <section className="form-card" aria-label="P3 API 실행 제어"><p className="eyebrow">POSTGRESQL-BACKED P3 VERTICAL SLICE</p><div className="button-row">
        <button data-testid="create-intake" className="secondary-button" type="button" disabled={busy || !context || !tokenFor("INSPECTOR") || Boolean(intakeRecord)} onClick={() => void runApi("intake", async () => setIntakeRecord(await createIntake(tokenFor("INSPECTOR")!, context!, marker)))}>1. 입고/LOT 등록</button>
        <label className="secondary-button" htmlFor="p3-document-upload">2. 로컬 PDF/문서 업로드</label><input id="p3-document-upload" data-testid="document-upload" type="file" disabled={busy || !tokenFor("INSPECTOR") || Boolean(documentRecord)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void runApi("document", async () => setDocumentRecord(await uploadDocument(tokenFor("INSPECTOR")!, file))); }} />
        <button data-testid="extract-document" className="secondary-button" type="button" disabled={busy || !documentRecord || Boolean(extractionRun)} onClick={() => void runApi("extraction", async () => { const run = await extractDocument(tokenFor("INSPECTOR")!, documentRecord!.document_id); setExtractionRun(run); setOcrReviewDrafts(createOcrReviewDrafts(run)); window.sessionStorage.setItem("hyc-local-ocr-resume-v1", JSON.stringify({ documentId: run.document_id, runId: run.run_id })); })}>3. 로컬/fixture 추출</button>
        <button data-testid="confirm-review" className="secondary-button" type="button" disabled={busy || !extractionRun || !intakeRecord || extractionRun.status === "CONFIRMED" || ocrReviewBlockers.length > 0} onClick={() => void runApi("review/match", async () => setExtractionRun(await confirmReview(tokenFor("INSPECTOR")!, extractionRun!.document_id, extractionRun!, intakeRecord!.allocation_id, ocrReviewDrafts, extractionRun!.provider_name === "local-paddleocr" ? context!.spec_version_id : undefined)))}>4. 검토·매칭 확정</button>
        <button data-testid="create-inspection" className="secondary-button" type="button" disabled={busy || extractionRun?.status !== "CONFIRMED" || !intakeRecord || Boolean(inspection)} onClick={() => void runApi("inspection", async () => { const created = await createInspection(tokenFor("INSPECTOR")!, intakeRecord!.allocation_id, extractionRun!.run_id, marker); setInspection(await getInspection(tokenFor("INSPECTOR")!, created.inspection_id)); })}>5. 검사 생성</button>
        <button data-testid="internal-result" className="secondary-button" type="button" disabled={busy || !inspection || !inspection.blockers.includes("INTERNAL_TEST_PENDING")} onClick={() => void runApi("internal result", async () => setInspection(await putInternalResult(tokenFor("INSPECTOR")!, inspection!)))}>6. 자체검사 저장</button>
        <button data-testid="submit-held-probe" className="secondary-button" type="button" disabled={busy || !inspection || !inspection.blockers.includes("INTERNAL_TEST_PENDING")} onClick={() => void runApi("held submit", async () => setInspection(await submitInspection(tokenFor("INSPECTOR")!, inspection!)))}>보류 상태 제출 서버 검증</button>
        <button data-testid="submit-inspection" className="secondary-button" type="button" disabled={busy || !inspection || inspection.status !== "READY_FOR_REVIEW"} onClick={() => void runApi("submit", async () => setInspection(await submitInspection(tokenFor("INSPECTOR")!, inspection!)))}>7. 검사자 제출</button>
        <button data-testid="approve-inspection" className="primary-button" type="button" disabled={busy || !inspection || inspection.status !== "LEAD_REVIEW" || !tokenFor()} onClick={() => void runApi("approval", async () => setInspection(await approveInspection(tokenFor()!, inspection!, marker)))}>8. 현재 역할 승인 시도</button>
        <button data-testid="return-inspection" className="secondary-button" type="button" disabled={busy || !inspection || inspection.status !== "LEAD_REVIEW" || !reviewReason.trim()} onClick={() => void runApi("return", async () => setInspection(await returnInspection(tokenFor()!, inspection!.inspection_id, inspection!.version, reviewReason)))}>9. 현재 역할 반려 시도</button>
        <button data-testid="load-trace" className="secondary-button" type="button" disabled={busy || !inspection || !tokenFor()} onClick={() => void runApi("trace", async () => setTrace(await getTrace(tokenFor()!, inspection!.material_lot_id)))}>LOT trace 조회</button>
        <button data-testid="create-revision" className="secondary-button" type="button" disabled={busy || !inspection?.final_decision} onClick={() => void runApi("revision", async () => { const created = await createLineage(tokenFor("INSPECTOR")!, inspection!, "revisions"); setLineage((current) => [...current, created]); })}>정정 revision</button>
        <button data-testid="create-retest" className="secondary-button" type="button" disabled={busy || !inspection?.final_decision} onClick={() => void runApi("retest", async () => { const created = await createLineage(tokenFor("INSPECTOR")!, inspection!, "retests"); setLineage((current) => [...current, created]); })}>재검사 round</button>
      </div><p aria-live="polite" data-testid="api-message">{apiMessage}</p>{extractionRun ? <p>추출 run {extractionRun.run_id} · {extractionRun.status} · 모든 field REVIEW_REQUIRED 시작</p> : null}{trace ? <p data-testid="trace-summary">trace: receipts {trace.receipts.length} · allocations {trace.allocations.length} · documents {trace.documents.length} · inspections {trace.inspections.length}</p> : null}{lineage.map((item) => <p key={item.inspection_id}>lineage {item.inspection_id} · round {item.round_no} / revision {item.revision_no}</p>)}</section>}
      <ol className="progress" aria-label="워크플로 화면 단계">{stages.map((stage, index) => <li key={stage} className={active === stage ? "current" : ""}><button type="button" aria-current={active === stage ? "step" : undefined} onClick={() => go(stage)}><span>{index + 1}</span><small>{stage}</small></button></li>)}</ol><div className="screen-reader-status" aria-live="polite" data-testid="workflow-status-live">현재 화면: {active}. 상태: {workflowStatus}. 시뮬레이션 역할: {state.selectedRole}.</div>

      {active === "목록" && <section className="stage-content" aria-labelledby="queue-title"><div className="section-heading"><div><p className="eyebrow">01 / WORK QUEUE</p><h2 id="queue-title">검사 작업 큐</h2><p>명확한 상태 텍스트와 필터로 fixture 사례를 검토합니다.</p></div><button className="secondary-button" type="button" onClick={() => go("입고/LOT")}>선택 건 열기</button></div><div className="kpi-grid"><article><span>오늘 대상</span><strong>03</strong><small>합성 queue 기준</small></article><article><span>검토 필요</span><strong>01</strong><small>문서 최종값 대기</small></article><article><span>자체검사 보류</span><strong>01</strong><small>INTERNAL_TEST_PENDING</small></article><article><span>승인 동결</span><strong>00</strong><small>local fixture 기준</small></article></div><div className="filter-row"><div><Label htmlFor="queue-search">통합 검색</Label><input id="queue-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="FX-ID, LOT, 품목 검색" /></div><div><Label htmlFor="queue-filter">상태 필터</Label><select id="queue-filter" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="ALL">전체 상태</option>{Object.entries(statusCopy).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div></div><div className="table-wrap" role="region" tabIndex={0} aria-label="검사 작업 큐 표"><table><thead><tr><th scope="col">상태</th><th scope="col">사례</th><th scope="col">공급사 / 품목</th><th scope="col">정본 LOT</th><th scope="col">입고 수량</th><th scope="col">작업</th></tr></thead><tbody>{selected ? <tr><td><span className="status-text">{statusCopy[state.workflowStatus]}</span></td><th scope="row"><strong>{state.fixtureId}</strong><br /><small>{state.caseName}</small></th><td>{state.receipt.supplier}<br /><small>{state.receipt.material}</small></td><td>{state.receipt.canonicalLot}</td><td>{state.receipt.receivedQuantity} {state.receipt.unit}</td><td><button className="text-button" type="button" onClick={() => go("입고/LOT")}>검토 시작 →</button></td></tr> : <tr><td colSpan={6}>조건에 맞는 fixture 사례가 없습니다.</td></tr>}</tbody></table></div></section>}

      {active === "입고/LOT" && <section className="stage-content" aria-labelledby="receipt-title"><div className="section-heading"><div><p className="eyebrow">02 / RECEIPT & CANONICAL LOT</p><h2 id="receipt-title">입고·정본 LOT</h2><p>입고 배분과 정본 LOT는 별개의 fixture 식별자입니다.</p></div><span className="read-only-note">{frozen ? "승인 후 동결됨" : mutationLocked ? "제출 후 팀장 검토 대기 — 입력 잠금" : "fixture 편집 가능"}</span></div><div className="form-card"><div className="form-grid">{editableFields.map(([field, label, required]) => <div key={field} className={receiptErrors[field as keyof typeof receiptErrors] ? "field has-error" : "field"}><Label htmlFor={`receipt-${field}`} required={required}>{label}</Label><input id={`receipt-${field}`} type={field === "receiptDate" ? "date" : "text"} value={state.receipt[field]} disabled={mutationLocked} aria-invalid={Boolean(receiptErrors[field as keyof typeof receiptErrors])} aria-describedby={receiptErrors[field as keyof typeof receiptErrors] ? `receipt-${field}-error` : undefined} onChange={(event) => dispatch({ type: "setReceiptField", field, value: event.target.value })} />{receiptErrors[field as keyof typeof receiptErrors] ? <small id={`receipt-${field}-error`} className="error-text">{receiptErrors[field as keyof typeof receiptErrors]}</small> : null}</div>)}</div><Notice>숫자 품질 값은 문자열로 유지합니다. 소수점 입력은 정본 형식만 허용하며 서버 검증·저장은 수행하지 않습니다.</Notice></div><div className="table-wrap" role="region" tabIndex={0} aria-label="입고 배분 표"><table><thead><tr><th scope="col">입고 allocation</th><th scope="col">정본 LOT</th><th scope="col">수량</th><th scope="col">용도</th><th scope="col">상태</th></tr></thead><tbody>{state.receipt.allocations.map((allocation) => <tr key={allocation.id}><th scope="row">{allocation.id}</th><td>{allocation.canonicalLot}</td><td>{allocation.quantity} {allocation.unit}</td><td>{allocation.purpose}</td><td>{allocation.status}</td></tr>)}</tbody></table></div></section>}

      {active === "문서 검토" && reviewPanels.persisted && extractionRun && <section className="form-card" aria-label="persisted local OCR review"><p className="eyebrow">PERSISTED EXTRACTION RUN</p><div className="table-wrap" role="region" tabIndex={0} aria-label="persisted local OCR review table"><table className="review-table"><thead><tr><th scope="col">OCR line</th><th scope="col">후보 / provenance</th><th scope="col">최종 문자열</th><th scope="col">MAP / UNMAPPED</th><th scope="col">현재 규격 코드</th><th scope="col">검토 사유</th></tr></thead><tbody>{extractionRun.fields.map((field) => { const draft = ocrReviewDrafts[field.field_id]; const local = extractionRun.provider_name === "local-paddleocr"; return <tr key={field.field_id}><th scope="row">{field.source_field_key}<small>page {field.page_number} · confidence {field.confidence}</small></th><td>{field.ocr_text}<small>{field.review_reasons?.join(" / ") || "review required"}</small><small>{JSON.stringify(field.provenance)}</small></td><td><input aria-label={`${field.source_field_key} 최종 문자열`} value={draft?.finalText ?? ""} disabled={extractionRun.status === "CONFIRMED"} onChange={(event) => updateOcrDraft(field.field_id, { finalText: event.target.value })} /></td><td>{local ? <select aria-label={`${field.source_field_key} 매핑 disposition`} value={draft?.mappingDisposition ?? ""} disabled={extractionRun.status === "CONFIRMED"} onChange={(event) => updateOcrDraft(field.field_id, { mappingDisposition: event.target.value as "" | "MAP" | "UNMAPPED", mappedFieldKey: event.target.value === "MAP" ? draft?.mappedFieldKey ?? "" : "" })}><option value="">선택 필요</option><option value="MAP">MAP</option><option value="UNMAPPED">UNMAPPED</option></select> : "fixture field"}</td><td>{local && draft?.mappingDisposition === "MAP" ? <select aria-label={`${field.source_field_key} 현재 규격 코드`} value={draft.mappedFieldKey} disabled={extractionRun.status === "CONFIRMED"} onChange={(event) => updateOcrDraft(field.field_id, { mappedFieldKey: event.target.value })}><option value="">현재 규격에서 선택</option>{context?.mapping_item_codes.map((code) => <option key={code} value={code}>{code}</option>)}</select> : "—"}</td><td><input aria-label={`${field.source_field_key} 검토 사유`} value={draft?.reason ?? ""} disabled={extractionRun.status === "CONFIRMED"} placeholder="명시적 검토 사유" onChange={(event) => updateOcrDraft(field.field_id, { reason: event.target.value })} /></td></tr>; })}</tbody></table></div>{ocrReviewBlockers.length ? <Notice tone="warn">확정 차단: {ocrReviewBlockers.join(" / ")}</Notice> : <Notice tone="success">명시적 검토가 완료되었습니다. 별도 확정 버튼을 눌러야 저장됩니다.</Notice>}</section>}

      {reviewPanels.synthetic && <>
      {active === "문서 검토" && <section className="stage-content" aria-labelledby="document-title"><div className="section-heading"><div><p className="eyebrow">03 / DOCUMENT REVIEW</p><h2 id="document-title">문서 검토</h2><p>{state.documentReview.documentId} · {state.documentReview.name}</p></div><span className="status-text">{reviewComplete ? "필수 필드 확정됨" : "최종값·사유 대기"}</span></div><div className="document-grid"><article className="preview-placeholder"><span>원문 미리보기 자리</span><strong>실제 문서 아님</strong><p>SYNTHETIC metadata only<br />{state.documentReview.name}<br />원문 파일과 OCR provider를 열지 않습니다.</p></article><article className="document-meta"><p className="eyebrow">DOCUMENT METADATA</p><dl><dt>식별자</dt><dd>{state.documentReview.documentId}</dd><dt>출처</dt><dd>SYNTHETIC / fixture</dd><dt>후보 상태</dt><dd>검사자 최종 확정 필요</dd><dt>원본</dt><dd>연결되지 않음</dd></dl></article></div><div className="table-wrap" role="region" tabIndex={0} aria-label="문서 교차 검증 표"><table className="review-table"><thead><tr><th scope="col">항목</th><th scope="col">원문</th><th scope="col">OCR 후보</th><th scope="col">수기</th><th scope="col">confidence / 경고</th><th scope="col">최종값·출처·사유</th></tr></thead><tbody>{state.documentReview.fields.map((field) => <tr key={field.id}><th scope="row">{field.label}{field.required ? <small> 필수</small> : null}</th><td>{field.originalValue || "누락"} {field.unit}</td><td>{field.ocrValue || "누락"} {field.ocrValue ? field.unit : ""}</td><td>{field.manualValue || "미입력"} {field.unit}</td><td><strong className={field.confidence === "HIGH" ? "confidence high" : "confidence low"}>{field.confidence}</strong><small>{field.warning}</small></td><td><div className="final-controls"><input aria-label={`${field.label} 최종값`} value={field.finalValue ?? ""} disabled={mutationLocked} onChange={(event) => finishField(field.id, field.finalSource ?? "MANUAL", event.target.value, field.reason ?? "")} /><select aria-label={`${field.label} 최종 출처`} value={field.finalSource ?? "MANUAL"} disabled={mutationLocked} onChange={(event) => finishField(field.id, event.target.value as DocumentSource, field.finalValue ?? field.manualValue, field.reason ?? "")}><option value="ORIGINAL">원문</option><option value="OCR">OCR 후보</option><option value="MANUAL">수기</option></select><input aria-label={`${field.label} 확정 사유`} placeholder="확정 사유 (필수)" value={reasons[field.id] ?? field.reason ?? ""} disabled={mutationLocked} onChange={(event) => setReasons((current) => ({ ...current, [field.id]: event.target.value }))} /><button className="secondary-button compact" type="button" disabled={mutationLocked} onClick={() => finishField(field.id, field.finalSource ?? "MANUAL", field.finalValue ?? field.manualValue, field.confidence === "HIGH" ? "OCR 후보와 수기 값을 대조함" : "저신뢰 또는 누락 후보를 수기 대조함")}>확정</button></div></td></tr>)}</tbody></table></div><Notice tone="warn">LOW와 MISSING은 항상 표에 표시됩니다. 최종 출처와 사유를 남기기 전에는 다음 단계 제출이 차단됩니다.</Notice></section>}
      </>}

      {active === "매칭" && <section className="stage-content" aria-labelledby="match-title"><div className="section-heading"><div><p className="eyebrow">04 / SECTION ↔ ALLOCATION</p><h2 id="match-title">section↔allocation 매칭</h2><p>후보는 자동 연결되지 않으며 검사자의 명시적 확인이 필요합니다.</p></div><span className="status-text">{matchComplete ? "검사자 확인됨" : "확정 전"}</span></div><div className="match-list">{state.matches.map((match) => <article className="match-card" key={match.id}><div className="match-route"><div><span>문서 section</span><strong>{match.section}</strong></div><b aria-hidden="true">↔</b><div><span>입고 allocation</span><strong>{match.allocation}</strong></div></div><dl><dt>근거</dt><dd>{match.evidence}</dd><dt>후보 사유</dt><dd>{match.reason}</dd><dt>충돌 표시</dt><dd><strong className="conflict">{match.conflict}</strong></dd></dl><button className={match.confirmed ? "secondary-button confirmed" : "primary-button"} type="button" disabled={match.confirmed || mutationLocked} onClick={() => dispatch({ type: "confirmMatch", matchId: match.id })}>{match.confirmed ? "검사자 확인 완료" : "검사자가 이 매칭 확인"}</button></article>)}</div></section>}

      {active === "자체검사" && <section className="stage-content" aria-labelledby="test-title"><div className="section-heading"><div><p className="eyebrow">05 / INTERNAL TEST</p><h2 id="test-title">자체검사</h2><p>가변 샘플 문자열을 정확한 소수 문자열 산술로 집계합니다.</p></div><span className={internalComplete ? "complete-mark" : "hold-badge"}>{internalComplete ? "필수 자체검사 완료" : "INTERNAL_TEST_PENDING"}</span></div><div className="test-list">{state.internalTests.map((item) => { const semantics = getInternalTestSemantics(item); const invalid = !semantics.completed; return <article className="test-card" key={item.id}><div className="test-card-head"><div><h3>{item.item}</h3><p>공급사 판정 {item.supplierDecision} · HYC {item.hycDecision} · {item.required ? "필수" : "선택"} · 단위 {item.unit}</p></div><span className={item.completed ? "complete-mark" : "hold-badge"}>{item.completed ? "입력값 확정됨" : item.holdReason}</span></div><div className="sample-row">{item.samples.map((sample, index) => { const errorId = `internal-${item.id}-sample-${index}-error`; return <div className="field" key={`${item.id}-${index}`}><Label htmlFor={`internal-sample-${item.id}-${index}`}>샘플 {index + 1}</Label><input id={`internal-sample-${item.id}-${index}`} value={sample} disabled={mutationLocked} aria-invalid={invalid} aria-describedby={invalid ? errorId : undefined} onChange={(event) => { const samples = [...item.samples]; samples[index] = event.target.value; dispatch({ type: "setInternalSamples", itemId: item.id, samples }); }} />{invalid ? <small id={errorId} className="error-text">{item.unit === "판정" ? "각 행은 적합 또는 부적합으로 입력하세요." : "정본 소수 문자열과 유한 평균, HYC 한계가 필요합니다."}</small> : null}</div>; })}</div><button className="text-button" type="button" disabled={mutationLocked} onClick={() => dispatch({ type: "setInternalSamples", itemId: item.id, samples: [...item.samples, ""] })}>+ 샘플 추가</button><button className="secondary-button compact" type="button" disabled={mutationLocked || !semantics.completed} onClick={() => dispatch({ type: "confirmInternalTest", itemId: item.id })}>입력값 확정</button><div className="aggregate"><span>결과 집계</span><strong>{invalid ? "입력 형식 오류" : semantics.aggregate}</strong><small>BigInt/string 기반 fixture helper 결과</small></div></article>; })}</div><Notice tone={internalComplete ? "success" : "warn"}>{internalComplete ? "필수 자체검사 항목이 완료되었습니다." : "필수 자체검사가 완료될 때까지 INTERNAL_TEST_PENDING hold가 유지됩니다."}</Notice></section>}

      {active === "제출" && <section className="stage-content" aria-labelledby="submit-title"><div className="section-heading"><div><p className="eyebrow">06 / INSPECTOR SUBMISSION</p><h2 id="submit-title">검사자 제출</h2><p>{state.workflowStatus === "SUBMITTED" ? "제출 후 팀장 검토 대기 — 입력 잠금" : state.workflowStatus === "RETURNED" ? "반려된 fixture를 보완한 뒤 재제출할 수 있습니다." : frozen ? "승인된 fixture는 동결되어 수정하거나 재제출할 수 없습니다." : state.workflowStatus === "READY_TO_SUBMIT" ? "제출 전 preflight가 완료되었습니다. 검사자 제출 사유를 확인해 제출하세요." : "preflight 완료 전에는 제출할 수 없습니다."}</p></div><span className="read-only-note">local fixture state only</span></div><div className="preflight-card"><h3>제출 전 확인</h3><ul className="check-list"><li className={reviewComplete ? "done" : ""}>{reviewComplete ? "완료" : "대기"} · 문서 최종값·사유 확정</li><li className={matchComplete ? "done" : ""}>{matchComplete ? "완료" : "대기"} · section↔allocation 검사자 확인</li><li className={internalComplete ? "done" : ""}>{internalComplete ? "완료" : "대기"} · 필수 자체검사 완료</li></ul>{state.workflowStatus === "SUBMITTED" ? <Notice tone="success">제출 후 팀장 검토 대기 — 입력 잠금</Notice> : state.workflowStatus === "APPROVED" ? <Notice tone="info">승인되어 동결되었습니다. 수정 또는 재제출할 수 없습니다.</Notice> : <>{state.workflowStatus === "RETURNED" ? <Notice tone="warn">팀장 반려 후 보완 상태입니다. 내용을 수정한 뒤 재제출할 수 있습니다.</Notice> : null}{submitGuard.blockers.length ? <Notice tone="danger">제출 차단: {submitGuard.blockers.join(" / ")}</Notice> : <Notice tone="success">제출 전 preflight가 완료되었습니다.</Notice>}</>}<div className="field"><Label htmlFor="submit-reason" required>검사자 제출 사유</Label><textarea id="submit-reason" value={submitReason} disabled={mutationLocked} onChange={(event) => setSubmitReason(event.target.value)} /></div><button className="primary-button" type="button" disabled={!submitGuard.allowed || mutationLocked} onClick={() => dispatch({ type: "submit", reason: submitReason })}>{state.workflowStatus === "SUBMITTED" ? "이미 제출됨 — 팀장 검토 대기" : frozen ? "승인·동결됨" : state.workflowStatus === "RETURNED" ? "보완 후 재제출 (서버 저장 없음)" : "검사자 제출 (서버 저장 없음)"}</button></div></section>}

      {active === "팀장 검토" && <section className="stage-content" aria-labelledby="approval-title">
        <div className="section-heading"><div><p className="eyebrow">07 / LEAD REVIEW</p><h2 id="approval-title">팀장 검토</h2><p>{publicDemo ? "공개 데모 역할 전환은 브라우저 안의 합성 시뮬레이션이며 API를 호출하지 않습니다." : "P3 fixture local identity/session — not production authentication. 역할은 서버가 검증합니다."}</p></div><span className="status-text">{inspection?.status ?? statusCopy[state.workflowStatus]}</span></div>
        <div className="approval-grid"><article className="role-card"><h3>검토 역할</h3><div className="role-switch" role="group" aria-label={publicDemo ? "공개 합성 데모 역할 시뮬레이션" : "P3 fixture local identity/session"}>{(["INSPECTOR", "LEAD", "ADMIN"] as WorkflowRole[]).map((role) => <button data-testid={`role-${role}`} type="button" key={role} className={state.selectedRole === role ? "selected" : ""} aria-pressed={state.selectedRole === role} disabled={false} onClick={() => switchFixtureRole(role)}>{role}</button>)}</div><p>{publicDemo ? "역할과 승인 상태는 local reducer에서만 바뀌며 실제 인증·권한 검증·서버 저장이 아닙니다." : "INSPECTOR와 ADMIN 승인 시도는 API 403입니다. LEAD와 제출자는 서로 다른 fixture actor입니다."}</p></article><article className="approval-card"><h3>결정 기록</h3><div className="field"><Label htmlFor="review-reason" required>팀장 검토 사유</Label><textarea id="review-reason" data-testid="return-reason-input" value={reviewReason} disabled={frozen} onChange={(event) => setReviewReason(event.target.value)} /></div>{approveGuard.blockers.length ? <Notice tone="warn">승인 조건: {approveGuard.blockers.join(" / ")}</Notice> : <Notice tone="success">LEAD 승인 조건을 충족했습니다.</Notice>}<div className="button-row"><button data-testid="return-submit-button" className="secondary-button" type="button" disabled={frozen || !reviewReason.trim()} onClick={() => { dispatch({ type: "return", reason: reviewReason }); if (!publicDemo && inspection && tokenFor()) { void runApi("return", async () => setInspection(await returnInspection(tokenFor()!, inspection.inspection_id, inspection.version, reviewReason))); } }}>반려 (사유 기록)</button>{publicDemo ? <button className="primary-button" type="button" disabled={frozen || !approveGuard.allowed} onClick={() => dispatch({ type: "approve", reason: reviewReason })}>합성 로컬 승인 (서버 저장 없음)</button> : <button className="primary-button" type="button" disabled={busy || !inspection || inspection.status !== "LEAD_REVIEW"} onClick={() => void runApi("approval", async () => setInspection(await approveInspection(tokenFor()!, inspection!, marker)))}>현재 역할로 API 승인</button>}</div></article></div>
        {publicDemo && frozen ? <article className="frozen-card"><h3>합성 로컬 승인 상태</h3><p>브라우저 local reducer에서만 동결되었으며 승인 snapshot이나 서버 기록은 생성되지 않았습니다.</p></article> : inspection?.final_decision ? <article className="frozen-card"><h3>승인 snapshot이 PostgreSQL에 동결되었습니다</h3><p>정본 LOT {inspection.material_lot_id} · 규격 {inspection.spec_version_id} · 최종 {inspection.final_decision}</p><Notice>정정은 새 revision, 재검사는 새 inspection round로 API가 생성합니다.</Notice></article> : null}
      </section>}

      {active === "LOT 추적" && <section className="stage-content" aria-labelledby="trace-title"><div className="section-heading"><div><p className="eyebrow">08 / LOT TRACE</p><h2 id="trace-title">LOT 추적</h2><p>분할 입고 배분, 합성 문서 section, 검사·규격·감사 관계를 시간순으로 표시합니다.</p></div><span className="fixture-chip">DETERMINISTIC TRACE</span></div><div className="relationship-strip"><div><span>정본 LOT</span><strong>{state.receipt.canonicalLot}</strong></div><b aria-hidden="true">→</b><div><span>입고 배분</span><strong>FX-ALLOC-01 / FX-ALLOC-02</strong></div><b aria-hidden="true">→</b><div><span>문서 section</span><strong>FX-SECTION-COA-01</strong></div><b aria-hidden="true">→</b><div><span>검사·승인</span><strong>FX-INSP-ROUND-01</strong></div></div><ol className="timeline">{[...state.trace].sort((left, right) => left.order - right.order).map((event) => <li key={event.id}><span>{String(event.order).padStart(2, "0")}</span><div><small>{event.type} · {event.id}</small><h3>{event.title}</h3><p>{event.detail}</p></div></li>)}</ol><Notice tone="warn">production LOT automatic ERP link is not enabled. 생산 LOT 자동 ERP 연계는 이 fixture UX와 현재 범위에서 활성화되어 있지 않습니다.</Notice></section>}
      {active === "부적합" && <section className="stage-content" aria-labelledby="ncr-stage-title"><div className="section-heading"><div><p className="eyebrow">09 / NONCONFORMANCE</p><h2 id="ncr-stage-title">부적합·후속조치</h2><p>부적합 기록과 추가만 가능한 후속조치 이력입니다.</p></div></div><NonconformanceWorkspace publicDemo={publicDemo} role={state.selectedRole} /></section>}
      {active === "보고서·통계" && <section className="stage-content" aria-labelledby="reports-title"><div className="section-heading"><div><p className="eyebrow">09 / REPORTS &amp; STATISTICS</p><h2 id="reports-title">보고서·통계</h2><p>승인 완료 검사 건의 출력물과 품질 통계입니다.</p></div></div><ReportPanel publicDemo={publicDemo} caseId={inspection?.inspection_id ?? state.fixtureId} /><StatisticsPanel publicDemo={publicDemo} periodStart={reportPeriod.start} periodEnd={reportPeriod.end} /></section>}
    </section>
  </main>;
}
