"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { ApiError } from "../../lib/api/client";
import { getMaterialModels, getMaterials, getSuppliers } from "../../lib/api/master-data";
import type { Material, MaterialModel, Supplier } from "../../lib/api/master-data";
import { canUseBackend, PUBLIC_DEMO_MODE } from "../../lib/public-demo";

const syntheticSuppliers: Supplier[] = [
  {
    id: "fx-sup-01",
    supplier_code: "SUP-DH-01",
    name: "동해화학 (SYNTHETIC)",
    active: true,
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
  {
    id: "fx-sup-02",
    supplier_code: null,
    name: "신규 미할당 공급사 (SYNTHETIC)",
    active: true,
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
];

const syntheticMaterials: Material[] = [
  {
    id: "fx-mat-01",
    material_code: "MAT-CC-01",
    name: "염화칼슘 비드 (SYNTHETIC)",
    default_unit: "kg",
    active: true,
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
  {
    id: "fx-mat-02",
    material_code: null,
    name: "임시 등록 품목 (SYNTHETIC)",
    default_unit: "kg",
    active: false,
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
];

const syntheticModels: MaterialModel[] = [
  {
    id: "fx-mod-01",
    model_code: "MOD-CC-96",
    name: "CaCl₂ 96% Standard",
    material_id: "fx-mat-01",
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
  {
    id: "fx-mod-02",
    model_code: null,
    name: "CaCl₂ 미할당 모델",
    material_id: "fx-mat-01",
    lock_version: 1,
    created_at: "2026-07-30T00:00:00Z",
    updated_at: "2026-07-30T00:00:00Z",
  },
];

function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "warn" | "danger" | "success" }) {
  return <p className={`notice notice-${tone}`} role={tone === "danger" ? "alert" : undefined} data-testid="master-data-error">{children}</p>;
}

export function renderCodeCell(code: string | null | undefined) {
  if (code === null || code === undefined || code.trim() === "") {
    return <span className="placeholder-code" data-testid="unassigned-code-placeholder">코드 미할당</span>;
  }
  return <code data-testid="master-code">{code}</code>;
}

export function MasterDataWorkspace({ publicDemo = PUBLIC_DEMO_MODE }: { publicDemo?: boolean }) {
  const [suppliers, setSuppliers] = useState<Supplier[]>(publicDemo ? syntheticSuppliers : []);
  const [materials, setMaterials] = useState<Material[]>(publicDemo ? syntheticMaterials : []);
  const [models, setModels] = useState<MaterialModel[]>(publicDemo ? syntheticModels : []);
  const [statusMessage, setStatusMessage] = useState<string>(
    publicDemo ? "공개 합성 데모 · 서버 연결 없음" : "마스터 데이터 로딩 중...",
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!canUseBackend(publicDemo)) return;

    let mounted = true;
    async function loadData() {
      try {
        setErrorMessage(null);
        const [sups, mats, mods] = await Promise.all([
          getSuppliers(),
          getMaterials(),
          getMaterialModels(),
        ]);
        if (mounted) {
          setSuppliers(sups);
          setMaterials(mats);
          setModels(mods);
          setStatusMessage("마스터 데이터 조회 완료");
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
          <p className="eyebrow">MASTER DATA MANAGEMENT</p>
          <h1>마스터 데이터 조회</h1>
        </div>
        <div className="topbar-actions">
          <span className="status-badge" data-testid="master-status-badge">
            {publicDemo ? "합성 로컬 상태" : statusMessage}
          </span>
        </div>
      </header>

      <div className="fixture-banner" role="status">
        <strong>{publicDemo ? "공개 합성 데모" : "MASTER DATA API"}</strong>
        <span>
          {publicDemo
            ? "서버 연결 없음 · 합성 마스터 데이터 시뮬레이션 · 서버 저장 없음."
            : "PostgreSQL 백엔드 마스터 데이터 연결됨."}
        </span>
      </div>

      {errorMessage ? (
        <section className="form-card" aria-label="오류 메시지">
          <Notice tone="danger">{errorMessage}</Notice>
        </section>
      ) : null}

      <section className="stage-content" aria-labelledby="suppliers-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">01 / SUPPLIERS</p>
            <h2 id="suppliers-title">공급사 마스터</h2>
            <p>등록된 공급사 식별 코드 및 상태 목록입니다.</p>
          </div>
        </div>
        <div className="table-wrap" role="region" tabIndex={0} aria-label="공급사 마스터 표">
          <table>
            <thead>
              <tr>
                <th scope="col">식별자 (ID)</th>
                <th scope="col">공급사 코드</th>
                <th scope="col">공급사명</th>
                <th scope="col">사용 상태</th>
                <th scope="col">버전</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.length === 0 ? (
                <tr>
                  <td colSpan={5}>등록된 공급사가 없습니다.</td>
                </tr>
              ) : (
                suppliers.map((item) => (
                  <tr key={item.id}>
                    <td><small>{item.id}</small></td>
                    <td>{renderCodeCell(item.supplier_code)}</td>
                    <td><strong>{item.name}</strong></td>
                    <td>
                      <span className={item.active ? "status-text active" : "status-text inactive"}>
                        {item.active ? "사용" : "미사용"}
                      </span>
                    </td>
                    <td>{item.lock_version}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stage-content" aria-labelledby="materials-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">02 / MATERIALS</p>
            <h2 id="materials-title">품목 마스터</h2>
            <p>등록된 자재 품목 코드 및 단위 정보입니다.</p>
          </div>
        </div>
        <div className="table-wrap" role="region" tabIndex={0} aria-label="품목 마스터 표">
          <table>
            <thead>
              <tr>
                <th scope="col">식별자 (ID)</th>
                <th scope="col">품목 코드</th>
                <th scope="col">품목명</th>
                <th scope="col">기본 단위</th>
                <th scope="col">사용 상태</th>
                <th scope="col">버전</th>
              </tr>
            </thead>
            <tbody>
              {materials.length === 0 ? (
                <tr>
                  <td colSpan={6}>등록된 품목이 없습니다.</td>
                </tr>
              ) : (
                materials.map((item) => (
                  <tr key={item.id}>
                    <td><small>{item.id}</small></td>
                    <td>{renderCodeCell(item.material_code)}</td>
                    <td><strong>{item.name}</strong></td>
                    <td>{item.default_unit ?? "미지정"}</td>
                    <td>
                      <span className={item.active ? "status-text active" : "status-text inactive"}>
                        {item.active ? "사용" : "미사용"}
                      </span>
                    </td>
                    <td>{item.lock_version}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="stage-content" aria-labelledby="models-title">
        <div className="section-heading">
          <div>
            <p className="eyebrow">03 / MATERIAL MODELS</p>
            <h2 id="models-title">자재 규격 모델 마스터</h2>
            <p>품목별 규격 모델 코드 및 매핑 정보입니다.</p>
          </div>
        </div>
        <div className="table-wrap" role="region" tabIndex={0} aria-label="자재 모델 마스터 표">
          <table>
            <thead>
              <tr>
                <th scope="col">식별자 (ID)</th>
                <th scope="col">모델 코드</th>
                <th scope="col">모델명</th>
                <th scope="col">연관 품목 ID</th>
                <th scope="col">버전</th>
              </tr>
            </thead>
            <tbody>
              {models.length === 0 ? (
                <tr>
                  <td colSpan={5}>등록된 모델이 없습니다.</td>
                </tr>
              ) : (
                models.map((item) => (
                  <tr key={item.id}>
                    <td><small>{item.id}</small></td>
                    <td>{renderCodeCell(item.model_code)}</td>
                    <td><strong>{item.name}</strong></td>
                    <td><small>{item.material_id}</small></td>
                    <td>{item.lock_version}</td>
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
