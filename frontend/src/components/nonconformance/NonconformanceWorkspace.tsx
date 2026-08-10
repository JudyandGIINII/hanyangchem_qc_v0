"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "../../lib/api/client";
import {
  approveNonconformance,
  getDispositions,
  getNonconformances,
  rejectNonconformance,
  updateNonconformance,
} from "../../lib/api/nonconformance";
import type {
  Nonconformance,
  NonconformanceDisposition,
} from "../../lib/api/nonconformance";
import { canUseBackend, PUBLIC_DEMO_MODE } from "../../lib/public-demo";

const syntheticDispositions: NonconformanceDisposition[] = [
  {
    id: "disp-01",
    code: "RETURN",
    name: "공급사 반품 (변경된 마스터)",
    active: true,
    sort_order: 1,
    lock_version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "disp-02",
    code: "SCRAP",
    name: "현장 폐기 (변경된 마스터)",
    active: true,
    sort_order: 2,
    lock_version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
];

const syntheticNonconformances: Nonconformance[] = [
  {
    id: "fx-ncr-01",
    ncr_number: "NCR-2026-001",
    inspection_case_id: "fx-case-01",
    severity: null,
    quantity: "500.00",
    disposition_id: "disp-01",
    disposition_snapshot: { id: "disp-01", code: "RETURN", name: "공급사 반품 (스냅샷)" },
    target_completion_date: "2026-08-15",
    completion_date: null,
    status: "SUBMITTED",
    lock_version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    cause: "수분 초과",
    description: "합성 수분 검사 기준치 초과",
    retest_case_id: null,
    spec_item_id: null,
  },
  {
    id: "fx-ncr-02",
    ncr_number: "NCR-2026-002",
    inspection_case_id: "fx-case-01",
    severity: "MAJOR",
    quantity: "250.00",
    disposition_id: "disp-02",
    disposition_snapshot: { id: "disp-02", code: "SCRAP", name: "폐기 처리 (스냅샷)" },
    target_completion_date: "2026-08-10",
    completion_date: "2026-08-09",
    status: "APPROVED",
    lock_version: 2,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-09T00:00:00Z",
    cause: "외관 불량",
    description: "포장 파손 및 이물질 혼입",
    retest_case_id: null,
    spec_item_id: null,
  },
];

function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "danger" | "success" }) {
  return <p className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined} data-testid="ncr-error">{children}</p>;
}

export function renderSeverity(severity: "MAJOR" | "MINOR" | null | undefined) {
  if (!severity) {
    return <span className="placeholder-text" data-testid="severity-placeholder">심각도 미지정</span>;
  }
  return <strong data-testid="severity-value">{severity === "MAJOR" ? "중결함 (MAJOR)" : "경결함 (MINOR)"}</strong>;
}

export function renderDispositionFromSnapshot(record: Nonconformance) {
  const snapshot = record.disposition_snapshot;
  if (snapshot && typeof snapshot === "object") {
    const name = (snapshot as Record<string, unknown>).name;
    if (typeof name === "string" && name.trim()) {
      return <strong data-testid="disposition-snapshot-label">{name}</strong>;
    }
    const code = (snapshot as Record<string, unknown>).code;
    if (typeof code === "string" && code.trim()) {
      return <strong data-testid="disposition-snapshot-label">{code}</strong>;
    }
  }
  return <span className="placeholder-text" data-testid="disposition-placeholder">처리방안 미지정</span>;
}

export function NonconformanceWorkspace({ publicDemo = PUBLIC_DEMO_MODE }: { publicDemo?: boolean }) {
  const [items, setItems] = useState<Nonconformance[]>(publicDemo ? syntheticNonconformances : []);
  const [dispositions, setDispositions] = useState<NonconformanceDisposition[]>(publicDemo ? syntheticDispositions : []);
  const [selectedId, setSelectedId] = useState<string | null>(publicDemo ? "fx-ncr-01" : null);
  const [statusMessage, setStatusMessage] = useState<string>(
    publicDemo ? "공개 합성 데모 · 서버 연결 없음" : "부적합 목록 로딩 중...",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [permissionMessage, setPermissionMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = items.find((item) => item.id === selectedId) ?? items[0] ?? null;
  const isApproved = selected?.status === "APPROVED";

  useEffect(() => {
    if (!canUseBackend(publicDemo)) return;

    let mounted = true;
    async function loadData() {
      try {
        setErrorMessage(null);
        const [ncrs, disps] = await Promise.all([
          getNonconformances(),
          getDispositions(),
        ]);
        if (mounted) {
          setItems(ncrs);
          setDispositions(disps);
          if (ncrs.length > 0 && !selectedId) setSelectedId(ncrs[0].id);
          setStatusMessage("부적합 목록 조회 완료");
        }
      } catch (error) {
        if (mounted) {
          const msg = error instanceof ApiError
            ? `API ${error.status}: ${error.message}`
            : `오류 발생: ${String(error)}`;
          setErrorMessage(msg);
          setStatusMessage(msg);
        }
      }
    }

    void loadData();

    return () => {
      mounted = false;
    };
  }, [publicDemo, selectedId]);

  const handleApprove = async () => {
    if (!selected) return;
    setErrorMessage(null);
    setPermissionMessage(null);

    if (!canUseBackend(publicDemo)) {
      setItems((prev) =>
        prev.map((item) =>
          item.id === selected.id ? { ...item, status: "APPROVED" as const, lock_version: item.lock_version + 1 } : item,
        ),
      );
      return;
    }

    setBusy(true);
    try {
      await approveNonconformance(selected.id, selected.lock_version);
      const updated = await getNonconformances();
      setItems(updated);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setPermissionMessage("403 Forbidden: 권한이 부족합니다. LEAD 역할만 승인/반려할 수 있습니다.");
      } else if (error instanceof ApiError && error.status === 409) {
        setErrorMessage("409 Conflict: 이미 승인 동결되었거나 동시 수정 충돌이 발생했습니다.");
      } else {
        setErrorMessage(error instanceof ApiError ? `API ${error.status}: ${error.message}` : String(error));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    if (!selected) return;
    setErrorMessage(null);
    setPermissionMessage(null);

    if (!canUseBackend(publicDemo)) {
      setItems((prev) =>
        prev.map((item) =>
          item.id === selected.id ? { ...item, status: "REJECTED" as const, lock_version: item.lock_version + 1 } : item,
        ),
      );
      return;
    }

    setBusy(true);
    try {
      await rejectNonconformance(selected.id, selected.lock_version);
      const updated = await getNonconformances();
      setItems(updated);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        setPermissionMessage("403 Forbidden: 권한이 부족합니다. LEAD 역할만 승인/반려할 수 있습니다.");
      } else if (error instanceof ApiError && error.status === 409) {
        setErrorMessage("409 Conflict: 동시 수정 충돌이 발생했습니다.");
      } else {
        setErrorMessage(error instanceof ApiError ? `API ${error.status}: ${error.message}` : String(error));
      }
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async () => {
    if (!selected || isApproved) return;
    setErrorMessage(null);

    if (!canUseBackend(publicDemo)) {
      setItems((prev) =>
        prev.map((item) =>
          item.id === selected.id ? { ...item, lock_version: item.lock_version + 1 } : item,
        ),
      );
      return;
    }

    setBusy(true);
    try {
      await updateNonconformance(selected.id, selected.lock_version, {
        inspection_case_id: selected.inspection_case_id,
        ncr_number: selected.ncr_number,
        quantity: selected.quantity,
        severity: selected.severity,
        status: selected.status,
        target_completion_date: selected.target_completion_date,
      });
      const updated = await getNonconformances();
      setItems(updated);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setErrorMessage("409 Conflict: 승인 동결된 부적합은 수정할 수 없거나 동시 수정 충돌이 발생했습니다.");
      } else {
        setErrorMessage(error instanceof ApiError ? `API ${error.status}: ${error.message}` : String(error));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">NONCONFORMANCE MANAGEMENT</p>
          <h1>부적합 관리 (NCR)</h1>
        </div>
        <div className="topbar-actions">
          <span className="status-badge" data-testid="ncr-status-badge">
            {publicDemo ? "합성 로컬 상태" : statusMessage}
          </span>
        </div>
      </header>

      <div className="fixture-banner" role="status">
        <strong>{publicDemo ? "공개 합성 데모" : "NCR API WORKSPACE"}</strong>
        <span>
          {publicDemo
            ? "서버 연결 없음 · 합성 부적합 데이터 시뮬레이션 · 서버 저장 없음."
            : "PostgreSQL 백엔드 NCR API 연결됨."}
        </span>
      </div>

      {permissionMessage ? (
        <section className="form-card" aria-label="권한 오류">
          <Notice tone="warn" data-testid="permission-error">{permissionMessage}</Notice>
        </section>
      ) : null}

      {errorMessage ? (
        <section className="form-card" aria-label="오류 메시지">
          <Notice tone="danger">{errorMessage}</Notice>
        </section>
      ) : null}

      <section className="stage-content" aria-labelledby="ncr-list-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">01 / NCR QUEUE</p>
            <h2 id="ncr-list-title">부적합 발생 목록</h2>
            <p>부적합 건별 심각도, 처리방안 스냅샷 (마스터 {dispositions.length}종), 진행 상태를 조회합니다.</p>
          </div>
        </div>
        <div className="table-wrap" role="region" tabIndex={0} aria-label="부적합 목록 표">
          <table>
            <thead>
              <tr>
                <th scope="col">부적합 번호</th>
                <th scope="col">심각도</th>
                <th scope="col">수량</th>
                <th scope="col">처리방안 (스냅샷)</th>
                <th scope="col">목표 완료일</th>
                <th scope="col">완료일</th>
                <th scope="col">상태</th>
                <th scope="col">선택</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr>
                  <td colSpan={8}>등록된 부적합 건이 없습니다.</td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id} className={selected?.id === item.id ? "selected-row" : ""}>
                    <th scope="row">
                      <strong data-testid="ncr-number">{item.ncr_number}</strong>
                    </th>
                    <td>{renderSeverity(item.severity)}</td>
                    <td>{item.quantity}</td>
                    <td>{renderDispositionFromSnapshot(item)}</td>
                    <td>{item.target_completion_date ?? "미지정"}</td>
                    <td>{item.completion_date ?? "미완료"}</td>
                    <td>
                      <span className={`status-text ${item.status.toLowerCase()}`}>
                        {item.status}
                      </span>
                    </td>
                    <td>
                      <button
                        className="text-button"
                        type="button"
                        onClick={() => setSelectedId(item.id)}
                      >
                        상세 보기
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      {selected ? (
        <section className="stage-content" aria-labelledby="ncr-detail-title">
          <div className="section-heading">
            <div>
              <p className="eyebrow">02 / NCR DETAIL & ACTION</p>
              <h2 id="ncr-detail-title">부적합 상세 및 승인/편집</h2>
              <p>
                {isApproved
                  ? "승인 완료(APPROVED) 상태로 동결되어 편집이 잠겼습니다."
                  : "LEAD 역할 승인/반려 및 내용 수정을 수행합니다."}
              </p>
            </div>
            {isApproved ? <span className="read-only-note" data-testid="approved-immutable-note">승인 동결됨 (Immutable)</span> : null}
          </div>

          <div className="form-card">
            <div className="form-grid">
              <div className="field">
                <label className="field-label" htmlFor="detail-ncr-no">부적합 번호</label>
                <input id="detail-ncr-no" value={selected.ncr_number} readOnly />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="detail-quantity">수량</label>
                <input
                  id="detail-quantity"
                  value={selected.quantity}
                  readOnly={isApproved}
                  onChange={(e) => {
                    const val = e.target.value;
                    setItems((prev) => prev.map((item) => item.id === selected.id ? { ...item, quantity: val } : item));
                  }}
                />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="detail-target-date">목표 완료일</label>
                <input
                  id="detail-target-date"
                  value={selected.target_completion_date ?? ""}
                  readOnly={isApproved}
                  onChange={(e) => {
                    const val = e.target.value;
                    setItems((prev) => prev.map((item) => item.id === selected.id ? { ...item, target_completion_date: val } : item));
                  }}
                />
              </div>
              <div className="field">
                <label className="field-label" htmlFor="detail-completion-date">완료일</label>
                <input
                  id="detail-completion-date"
                  value={selected.completion_date ?? ""}
                  readOnly={isApproved}
                  onChange={(e) => {
                    const val = e.target.value;
                    setItems((prev) => prev.map((item) => item.id === selected.id ? { ...item, completion_date: val } : item));
                  }}
                />
              </div>
            </div>

            <div className="button-row">
              <button
                data-testid="edit-update-button"
                className="secondary-button"
                type="button"
                disabled={busy || isApproved}
                onClick={() => void handleUpdate()}
              >
                {isApproved ? "편집 잠김 (APPROVED)" : "수정 내용 저장"}
              </button>
              <button
                data-testid="approve-ncr-button"
                className="primary-button"
                type="button"
                disabled={busy || isApproved}
                onClick={() => void handleApprove()}
              >
                LEAD 승인 (Approve)
              </button>
              <button
                data-testid="reject-ncr-button"
                className="secondary-button"
                type="button"
                disabled={busy || isApproved}
                onClick={() => void handleReject()}
              >
                LEAD 반려 (Reject)
              </button>
            </div>
          </div>
        </section>
      ) : null}
    </main>
  );
}
