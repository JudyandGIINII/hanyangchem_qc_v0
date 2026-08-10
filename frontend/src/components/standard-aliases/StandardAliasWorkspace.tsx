"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "../../lib/api/client";
import { getAliases } from "../../lib/api/standard-aliases";
import type { StandardTestItemAlias } from "../../lib/api/standard-aliases";
import { canUseBackend, PUBLIC_DEMO_MODE } from "../../lib/public-demo";

const syntheticAliases: StandardTestItemAlias[] = [
  {
    id: "fx-alias-01",
    alias_text: "수분 함유량 (Moisture)",
    standard_test_item_id: "std-item-moisture-01",
    supplier_id: null,
    material_id: null,
    model_id: null,
    priority: 10,
    active: true,
    lock_version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
  {
    id: "fx-alias-02",
    alias_text: "Moisture Content (%)",
    standard_test_item_id: "std-item-moisture-01",
    supplier_id: "sup-dh-01",
    material_id: "mat-cc-01",
    model_id: null,
    priority: 1,
    active: true,
    lock_version: 1,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
  },
];

function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "danger" | "success" }) {
  return <p className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined} data-testid="alias-error">{children}</p>;
}

export function renderAliasScope(
  supplierId: string | null | undefined,
  materialId: string | null | undefined,
  modelId: string | null | undefined,
) {
  if (!supplierId && !materialId && !modelId) {
    return <span className="placeholder-scope" data-testid="scope-placeholder">전체 범위</span>;
  }
  const parts: string[] = [];
  if (supplierId) parts.push(`공급사: ${supplierId}`);
  if (materialId) parts.push(`품목: ${materialId}`);
  if (modelId) parts.push(`모델: ${modelId}`);
  return <span data-testid="scope-value">{parts.join(" / ")}</span>;
}

export function StandardAliasWorkspace({ publicDemo = PUBLIC_DEMO_MODE }: { publicDemo?: boolean }) {
  const [aliases, setAliases] = useState<StandardTestItemAlias[]>(publicDemo ? syntheticAliases : []);
  const [statusMessage, setStatusMessage] = useState<string>(
    publicDemo ? "공개 합성 데모 · 서버 연결 없음" : "표준 별칭 목록 로딩 중...",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!canUseBackend(publicDemo)) return;

    let mounted = true;
    async function loadData() {
      try {
        setErrorMessage(null);
        const data = await getAliases();
        if (mounted) {
          setAliases(data);
          setStatusMessage("표준 별칭 목록 조회 완료");
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
  }, [publicDemo]);

  return (
    <main className="workspace-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">STANDARD TEST ITEM ALIASES</p>
          <h1>표준 항목 별칭 관리</h1>
        </div>
        <div className="topbar-actions">
          <span className="candidate-badge" data-testid="alias-candidate-only-badge">
            후보 추천 전용 · 수동 확정 필요
          </span>
          <span className="status-badge" data-testid="alias-status-badge">
            {publicDemo ? "합성 로컬 상태" : statusMessage}
          </span>
        </div>
      </header>

      <div className="fixture-banner" role="status">
        <strong>{publicDemo ? "공개 합성 데모" : "ALIAS LOOKUP CANDIDATE API"}</strong>
        <span>
          {publicDemo
            ? "서버 연결 없음 · 별칭 후보 추천 시뮬레이션 · 수동 확정 전용."
            : "PostgreSQL 백엔드 표준 별칭 API 연결됨."}
        </span>
      </div>

      <Notice tone="info">
        별칭은 매칭 검토 시 **후보 추천 전용 (Lookup Candidate Only)** 으로 사용되며 매칭을 제안만 합니다. 최종 매칭 확정은 항상 검사자의 수동 확인이 필요합니다.
      </Notice>

      {errorMessage ? (
        <section className="form-card" aria-label="오류 메시지">
          <Notice tone="danger">{errorMessage}</Notice>
        </section>
      ) : null}

      <section className="stage-content" aria-labelledby="alias-list-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">01 / ALIAS LIST</p>
            <h2 id="alias-list-title">표준 항목 별칭 매핑 목록</h2>
            <p>등록된 별칭 텍스트, 표준 항목 reference, 적용 범위 및 우선순위를 조회합니다.</p>
          </div>
        </div>
        <div className="table-wrap" role="region" tabIndex={0} aria-label="표준 항목 별칭 표">
          <table>
            <thead>
              <tr>
                <th scope="col">별칭 텍스트</th>
                <th scope="col">표준 항목 ID</th>
                <th scope="col">적용 범위 (Scope)</th>
                <th scope="col">우선순위</th>
                <th scope="col">사용 상태</th>
                <th scope="col">매칭 정책</th>
              </tr>
            </thead>
            <tbody>
              {aliases.length === 0 ? (
                <tr>
                  <td colSpan={6}>등록된 표준 항목 별칭이 없습니다.</td>
                </tr>
              ) : (
                aliases.map((item) => (
                  <tr key={item.id}>
                    <th scope="row">
                      <strong data-testid="alias-text">{item.alias_text}</strong>
                    </th>
                    <td><code>{item.standard_test_item_id}</code></td>
                    <td>{renderAliasScope(item.supplier_id, item.material_id, item.model_id)}</td>
                    <td>{item.priority}</td>
                    <td>
                      <span className={item.active ? "status-text active" : "status-text inactive"}>
                        {item.active ? "사용" : "미사용"}
                      </span>
                    </td>
                    <td>
                      <span className="candidate-chip" data-testid="candidate-only-indicator">
                        후보 추천 전용 (수동 확정 필요)
                      </span>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
