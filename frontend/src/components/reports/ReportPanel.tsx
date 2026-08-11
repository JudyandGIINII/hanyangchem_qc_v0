"use client";

import { useState } from "react";
import { canUseBackend } from "../../lib/public-demo";

export interface ReportPanelProps {
  publicDemo: boolean;
  caseId: string;
}

export function ReportPanel({ publicDemo, caseId }: ReportPanelProps) {
  const [loading, setLoading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobState, setJobState] = useState<string | null>(null);
  const [failureCode, setFailureCode] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const backendAvailable = canUseBackend(publicDemo);

  const formatFailureCode = (code: string): string => {
    if (code === "APPROVAL_SNAPSHOT_MISSING") {
      return "승인 스냅샷이 없어 보고서를 만들 수 없습니다.";
    }
    return code;
  };

  const handleGenerateReport = async () => {
    if (!backendAvailable) {
      setErrorMsg("공개 합성 데모 · 서버 연결 없음");
      return;
    }

    setLoading(true);
    setErrorMsg(null);
    setFailureCode(null);

    try {
      const res = await fetch("/api/v1/reports", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `report-${caseId}-${Date.now()}`,
        },
        body: JSON.stringify({
          kind: "INTEGRATED_INSPECTION",
          parameters: { inspection_case_id: caseId },
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        setErrorMsg(`오류 발생 (${res.status}): ${text}`);
        setLoading(false);
        return;
      }

      const data = await res.json();
      const currentJobId = data.job_id;
      setJobId(currentJobId);
      setJobState(data.state);

      if (data.state === "SUCCEEDED") {
        setLoading(false);
        return;
      }

      if (data.state === "FAILED") {
        setFailureCode(data.failure_code || null);
        setLoading(false);
        return;
      }

      await pollJobStatus(currentJobId);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  };

  const pollJobStatus = async (id: string) => {
    try {
      const res = await fetch(`/api/v1/reports/${id}`);
      if (!res.ok) {
        setErrorMsg(`상태 조회 실패 (${res.status})`);
        setLoading(false);
        return;
      }
      const data = await res.json();
      setJobState(data.state);

      if (data.state === "SUCCEEDED") {
        setLoading(false);
        return;
      }

      if (data.state === "FAILED") {
        setFailureCode(data.failure_code || null);
        setLoading(false);
        return;
      }

      setTimeout(() => {
        void pollJobStatus(id);
      }, 500);
    } catch (err: unknown) {
      setErrorMsg(err instanceof Error ? err.message : String(err));
      setLoading(false);
    }
  };

  return (
    <div className="report-panel p-4 border rounded shadow-sm">
      <h3 className="text-lg font-bold mb-2">통합 검사보고서</h3>
      {!backendAvailable ? (
        <div className="text-sm text-gray-600 mb-2">
          공개 합성 데모 · 서버 연결 없음
        </div>
      ) : null}

      <div className="flex flex-col gap-2">
        <button
          type="button"
          disabled={loading}
          onClick={handleGenerateReport}
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "보고서 생성 중..." : "보고서 생성"}
        </button>

        {failureCode ? (
          <div className="text-red-600 font-medium mt-2">
            {formatFailureCode(failureCode)}
          </div>
        ) : null}

        {errorMsg ? (
          <div className="text-red-600 text-sm mt-2">{errorMsg}</div>
        ) : null}

        {jobState === "SUCCEEDED" && jobId ? (
          <div className="mt-2">
            <a
              href={`/api/v1/reports/${jobId}/download`}
              className="inline-block px-4 py-2 bg-green-600 text-white rounded hover:bg-green-700"
              download
            >
              보고서 다운로드
            </a>
          </div>
        ) : null}
      </div>
    </div>
  );
}
