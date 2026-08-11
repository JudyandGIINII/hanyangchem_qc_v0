"use client";

import { useEffect, useState } from "react";
import { canUseBackend } from "../../lib/public-demo";

interface MonthlyStatistic {
  month: string;
  receipt_count: number;
  inspection_count: number;
}

interface DecisionStatistic {
  decision: string;
  count: number;
}

interface DefectRateStatistic {
  supplier_name?: string;
  material_name?: string;
  inspected: number;
  defective: number;
  defect_rate: string;
}

interface QualityStatistics {
  period_start: string;
  period_end: string;
  observed_at: string;
  population: {
    approved_case_count: number;
    excluded_cancelled_count: number;
  };
  monthly: MonthlyStatistic[];
  by_decision: DecisionStatistic[];
  by_supplier: DefectRateStatistic[];
  by_material: DefectRateStatistic[];
  coa_missing_count: number;
  ocr_review_rate: string;
  internal_test_pending_count: number;
  average_handling_days: string;
  open_nonconformance_count: number;
}

export interface StatisticsPanelProps {
  publicDemo: boolean;
  periodStart: string;
  periodEnd: string;
}

function EmptyRow({ colSpan }: { colSpan: number }) {
  return (
    <tr>
      <td colSpan={colSpan}>표시할 데이터가 없습니다.</td>
    </tr>
  );
}

export function StatisticsPanel({ publicDemo, periodStart, periodEnd }: StatisticsPanelProps) {
  const [statistics, setStatistics] = useState<QualityStatistics | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const backendAvailable = canUseBackend(publicDemo);

  useEffect(() => {
    if (!backendAvailable) return;

    let mounted = true;
    async function loadStatistics() {
      try {
        setErrorMessage(null);
        const query = new URLSearchParams({
          period_start: periodStart,
          period_end: periodEnd,
        });
        const response = await fetch(`/api/v1/statistics/quality?${query.toString()}`);
        if (!response.ok) {
          if (mounted) {
            setErrorMessage(`통계 조회에 실패했습니다 (${response.status}).`);
          }
          return;
        }
        const data: QualityStatistics = await response.json();
        if (mounted) {
          setStatistics(data);
        }
      } catch (error: unknown) {
        if (mounted) {
          setErrorMessage(
            `통계 조회 중 오류가 발생했습니다: ${error instanceof Error ? error.message : String(error)}`,
          );
        }
      }
    }

    void loadStatistics();
    return () => {
      mounted = false;
    };
  }, [backendAvailable, periodEnd, periodStart]);

  return (
    <section className="statistics-panel p-4 border rounded shadow-sm" aria-labelledby="statistics-title">
      <h3 id="statistics-title" className="text-lg font-bold mb-2">품질 통계</h3>
      {!backendAvailable ? (
        <div className="text-sm text-gray-600 mb-2" data-testid="statistics-public-demo-notice">
          공개 합성 데모 · 서버 연결 없음 · 품질 통계는 로컬 API 연결에서만 조회합니다.
        </div>
      ) : null}
      {errorMessage ? (
        <div className="text-red-600 text-sm mt-2" role="alert" data-testid="statistics-error">
          {errorMessage}
        </div>
      ) : null}
      {statistics ? (
        <div className="flex flex-col gap-4" data-testid="statistics-content">
          <p className="text-sm text-gray-600">
            조회 기간: {statistics.period_start} ~ {statistics.period_end} · 조회 시점: {statistics.observed_at}
          </p>
          <p className="text-sm font-medium" data-testid="statistics-population-note">
            집계 대상은 승인 완료 검사 건만이며, 취소 건은 제외합니다. 승인 완료 {statistics.population.approved_case_count}건 · 취소 제외 {statistics.population.excluded_cancelled_count}건
          </p>

          <section aria-labelledby="monthly-title">
            <h4 id="monthly-title">월별 입고·검사 건수</h4>
            <table>
              <thead><tr><th>월</th><th>입고 건수</th><th>검사 건수</th></tr></thead>
              <tbody>
                {statistics.monthly.length === 0 ? <EmptyRow colSpan={3} /> : statistics.monthly.map((item) => (
                  <tr key={item.month}><td>{item.month}</td><td>{item.receipt_count}</td><td>{item.inspection_count}</td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <section aria-labelledby="decision-title">
            <h4 id="decision-title">판정별 건수</h4>
            <table>
              <thead><tr><th>판정</th><th>건수</th></tr></thead>
              <tbody>
                {statistics.by_decision.length === 0 ? <EmptyRow colSpan={2} /> : statistics.by_decision.map((item) => (
                  <tr key={item.decision}><td>{item.decision}</td><td>{item.count}</td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <section aria-labelledby="supplier-title">
            <h4 id="supplier-title">공급업체별 부적합률</h4>
            <table>
              <thead><tr><th>공급업체</th><th>검사 건수</th><th>부적합 건수</th><th>부적합률</th></tr></thead>
              <tbody>
                {statistics.by_supplier.length === 0 ? <EmptyRow colSpan={4} /> : statistics.by_supplier.map((item) => (
                  <tr key={item.supplier_name}><td>{item.supplier_name}</td><td>{item.inspected}</td><td>{item.defective}</td><td>{item.defect_rate}</td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <section aria-labelledby="material-title">
            <h4 id="material-title">품목별 부적합률</h4>
            <table>
              <thead><tr><th>품목</th><th>검사 건수</th><th>부적합 건수</th><th>부적합률</th></tr></thead>
              <tbody>
                {statistics.by_material.length === 0 ? <EmptyRow colSpan={4} /> : statistics.by_material.map((item) => (
                  <tr key={item.material_name}><td>{item.material_name}</td><td>{item.inspected}</td><td>{item.defective}</td><td>{item.defect_rate}</td></tr>
                ))}
              </tbody>
            </table>
          </section>

          <dl>
            <div><dt>COA 누락 건수</dt><dd>{statistics.coa_missing_count}</dd></div>
            <div><dt>OCR 수동 검토율</dt><dd>{statistics.ocr_review_rate}</dd></div>
            <div><dt>자체검사 대기 건수</dt><dd>{statistics.internal_test_pending_count}</dd></div>
            <div><dt>평균 검사 처리시간</dt><dd>{statistics.average_handling_days}</dd></div>
            <div><dt>미완료 부적합 조치</dt><dd>{statistics.open_nonconformance_count}</dd></div>
          </dl>
        </div>
      ) : null}
    </section>
  );
}
