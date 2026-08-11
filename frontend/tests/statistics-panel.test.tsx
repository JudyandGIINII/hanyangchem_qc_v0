// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatisticsPanel } from "../src/components/statistics/StatisticsPanel";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const response = {
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  observed_at: "2026-08-12T03:00:00Z",
  population: { approved_case_count: 8, excluded_cancelled_count: 2 },
  monthly: [{ month: "2026-08", receipt_count: 10, inspection_count: 8 }],
  by_decision: [{ decision: "ACCEPTED", count: 6 }],
  by_supplier: [{ supplier_name: "한양 공급사", inspected: 8, defective: 1, defect_rate: "12.50%" }],
  by_material: [{ material_name: "염화칼슘", inspected: 8, defective: 1, defect_rate: "12.50%" }],
  coa_missing_count: 1,
  ocr_review_rate: "25.00%",
  internal_test_pending_count: 2,
  average_handling_days: "1.25일",
  open_nonconformance_count: 3,
};

const mounted: Array<{ container: HTMLDivElement; root: ReturnType<typeof createRoot> }> = [];

async function mountPanel(publicDemo: boolean) {
  const container = document.body.appendChild(document.createElement("div"));
  const root = createRoot(container);
  mounted.push({ container, root });
  await act(async () => {
    root.render(React.createElement(StatisticsPanel, {
      publicDemo,
      periodStart: "2026-08-01",
      periodEnd: "2026-08-31",
    }));
    await new Promise((resolve) => setTimeout(resolve, 10));
  });
  return container;
}

afterEach(async () => {
  while (mounted.length > 0) {
    const item = mounted.pop();
    if (!item) {
      throw new Error("Missing mounted panel");
    }
    await act(async () => {
      item.root.unmount();
    });
    item.container.remove();
  }
});

describe("StatisticsPanel", () => {
  it("public demo renders the boundary notice and issues zero fetches", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as any;

    try {
      const container = await mountPanel(true);
      const notice = container.querySelector("[data-testid='statistics-public-demo-notice']");
      if (!notice) {
        throw new Error("Missing selector: statistics public-demo notice");
      }
      expect(notice.textContent).toContain("공개 합성 데모");
      expect(fetchSpy).toHaveBeenCalledTimes(0);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("local mode fetches the quality-statistics path and renders backend-formatted rates", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => response });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = await mountPanel(false);
      expect(fetchSpy).toHaveBeenCalledTimes(1);
      expect(String(fetchSpy.mock.calls[0][0])).toBe(
        "/api/v1/statistics/quality?period_start=2026-08-01&period_end=2026-08-31",
      );
      const content = container.querySelector("[data-testid='statistics-content']");
      if (!content) {
        throw new Error("Missing selector: statistics content");
      }
      const population = container.querySelector("[data-testid='statistics-population-note']");
      if (!population) {
        throw new Error("Missing selector: statistics population note");
      }
      expect(population.textContent).toContain("승인 완료 검사 건만");
      expect(population.textContent).toContain("취소 건은 제외");
      expect(content.textContent).toContain("12.50%");
      expect(content.textContent).toContain("1.25일");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("renders empty statistics tables without crashing", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...response, monthly: [], by_decision: [], by_supplier: [], by_material: [] }),
    });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = await mountPanel(false);
      const content = container.querySelector("[data-testid='statistics-content']");
      if (!content) {
        throw new Error("Missing selector: statistics content for empty response");
      }
      expect(content.textContent).toContain("표시할 데이터가 없습니다.");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("renders a readable Korean error for a non-ok response", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockResolvedValue({ ok: false, status: 503 });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = await mountPanel(false);
      const error = container.querySelector("[data-testid='statistics-error']");
      if (!error) {
        throw new Error("Missing selector: statistics error");
      }
      expect(error.textContent).toContain("통계 조회에 실패했습니다 (503).");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
