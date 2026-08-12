"use client";

import { useCallback, useEffect, useState } from "react";
import { canUseBackend } from "../../lib/public-demo";

export interface NonconformanceAction {
  id: string;
  nonconformance_id: string;
  action_type: string;
  description: string;
  result: string | null;
  performed_by_id: string;
  actor_role: string;
  performed_at: string;
  created_at: string;
}

export interface ActionTimelineProps {
  publicDemo: boolean;
  nonconformanceId: string;
  role: string;
}

const ACTION_TYPE_LABELS: Record<string, string> = {
  CORRECTIVE: "시정조치",
  PREVENTIVE: "예방조치",
  VERIFICATION: "검증",
  COMPLETION: "종결",
};

/** 종결 권한은 LEAD에게만 있다. 목록에서 감추는 것과 권한이 있는 것은 다르므로
 *  서버의 403도 그대로 읽을 수 있게 노출한다. */
const SELECTABLE_TYPES = ["CORRECTIVE", "PREVENTIVE", "VERIFICATION"] as const;

export function ActionTimeline({ publicDemo, nonconformanceId, role }: ActionTimelineProps) {
  const [actions, setActions] = useState<NonconformanceAction[]>([]);
  const [actionType, setActionType] = useState<string>("CORRECTIVE");
  const [description, setDescription] = useState("");
  const [result, setResult] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const backendAvailable = canUseBackend(publicDemo);
  const path = `/api/v1/nonconformances/${nonconformanceId}/actions`;
  const availableTypes = role === "LEAD" ? [...SELECTABLE_TYPES, "COMPLETION"] : SELECTABLE_TYPES;

  const load = useCallback(async () => {
    if (!backendAvailable) return;
    try {
      const res = await fetch(path);
      if (!res.ok) {
        setErrorMsg(`후속조치 조회에 실패했습니다 (${res.status}).`);
        return;
      }
      setActions((await res.json()) as NonconformanceAction[]);
      setErrorMsg(null);
    } catch (error) {
      setErrorMsg(`후속조치 조회에 실패했습니다: ${String(error)}`);
    } finally {
      setLoaded(true);
    }
  }, [backendAvailable, path]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = async () => {
    if (!backendAvailable) {
      setErrorMsg("공개 합성 데모 · 서버 연결 없음");
      return;
    }
    try {
      const res = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action_type: actionType,
          description,
          result: result.trim() ? result : null,
          performed_at: new Date().toISOString(),
        }),
      });
      if (!res.ok) {
        setErrorMsg(
          res.status === 403
            ? "종결은 품질팀장만 기록할 수 있습니다 (403)."
            : `후속조치 기록에 실패했습니다 (${res.status}).`,
        );
        return;
      }
      setDescription("");
      setResult("");
      setErrorMsg(null);
      await load();
    } catch (error) {
      setErrorMsg(`후속조치 기록에 실패했습니다: ${String(error)}`);
    }
  };

  if (publicDemo) {
    return (
      <section className="form-card" aria-label="부적합 후속조치">
        <p className="eyebrow">NONCONFORMANCE FOLLOW-UP</p>
        <h3>부적합 후속조치</h3>
        <p data-testid="action-timeline-public-notice">
          공개 합성 데모 · 서버 연결 없음. 후속조치 이력은 사내망에서만 조회·기록됩니다.
        </p>
      </section>
    );
  }

  return (
    <section className="form-card" aria-label="부적합 후속조치">
      <p className="eyebrow">NONCONFORMANCE FOLLOW-UP</p>
      <h3>부적합 후속조치</h3>
      <p data-testid="action-timeline-append-only-note">
        후속조치는 추가만 가능한 이력입니다. 기록된 항목은 수정·삭제되지 않으며 승인된 부적합
        기록 자체를 바꾸지 않습니다.
      </p>

      {errorMsg ? (
        <p role="alert" data-testid="action-timeline-error">
          {errorMsg}
        </p>
      ) : null}

      <div className="table-wrap" role="region" tabIndex={0} aria-label="후속조치 이력 표">
        <table>
          <thead>
            <tr>
              <th scope="col">유형</th>
              <th scope="col">내용</th>
              <th scope="col">결과</th>
              <th scope="col">수행자 역할</th>
              <th scope="col">수행 시각</th>
            </tr>
          </thead>
          <tbody data-testid="action-timeline-rows">
            {actions.length === 0 ? (
              <tr>
                <td colSpan={5}>
                  {loaded ? "기록된 후속조치가 없습니다." : "후속조치를 불러오는 중입니다."}
                </td>
              </tr>
            ) : (
              actions.map((action) => (
                <tr key={action.id}>
                  <td>{ACTION_TYPE_LABELS[action.action_type] ?? action.action_type}</td>
                  <td>{action.description}</td>
                  <td>{action.result ?? "—"}</td>
                  <td>{action.actor_role}</td>
                  <td>{action.performed_at}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="form-grid">
        <div className="field">
          <label className="field-label" htmlFor="action-type">
            조치 유형
          </label>
          <select
            id="action-type"
            value={actionType}
            onChange={(event) => setActionType(event.target.value)}
          >
            {availableTypes.map((type) => (
              <option key={type} value={type}>
                {ACTION_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label className="field-label" htmlFor="action-description">
            조치 내용 <span aria-label="필수"> *</span>
          </label>
          <input
            id="action-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </div>
        <div className="field">
          <label className="field-label" htmlFor="action-result">
            결과
          </label>
          <input
            id="action-result"
            value={result}
            onChange={(event) => setResult(event.target.value)}
          />
        </div>
      </div>

      <button
        className="primary-button"
        type="button"
        data-testid="action-submit"
        disabled={!description.trim()}
        onClick={() => void submit()}
      >
        후속조치 기록
      </button>
    </section>
  );
}
