// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  NonconformanceWorkspace,
  renderDispositionFromSnapshot,
  renderSeverity,
} from "../src/components/nonconformance/NonconformanceWorkspace";
import type { Nonconformance } from "../src/lib/api/nonconformance";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

const mockRecordNullSeverity: Nonconformance = {
  id: "test-01",
  ncr_number: "NCR-TEST-001",
  inspection_case_id: "case-01",
  severity: null,
  quantity: "100.00",
  disposition_id: "disp-01",
  disposition_snapshot: { id: "disp-01", name: "원래 스냅샷 처리방안" },
  target_completion_date: "2026-08-20",
  completion_date: null,
  status: "SUBMITTED",
  lock_version: 1,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
  cause: null,
  description: null,
  retest_case_id: null,
  spec_item_id: null,
};

const mockApprovedRecord: Nonconformance = {
  ...mockRecordNullSeverity,
  id: "test-approved",
  ncr_number: "NCR-TEST-APPROVED",
  status: "APPROVED",
  lock_version: 2,
};

describe("NonconformanceWorkspace product rules & boundary", () => {
  it("renders a clear placeholder for absent severity and never displays 'null'", () => {
    const markupNull = renderToStaticMarkup(renderSeverity(null));
    expect(markupNull).toContain("심각도 미지정");
    expect(markupNull).not.toContain(">null<");

    const markupUndefined = renderToStaticMarkup(renderSeverity(undefined));
    expect(markupUndefined).toContain("심각도 미지정");

    const markupMajor = renderToStaticMarkup(renderSeverity("MAJOR"));
    expect(markupMajor).toContain("MAJOR");

    const workspaceMarkup = renderToStaticMarkup(
      React.createElement(NonconformanceWorkspace, { publicDemo: true })
    );
    expect(workspaceMarkup).toContain("심각도 미지정");
    expect(workspaceMarkup).not.toContain("<td>null</td>");
  });

  it("renders disposition label from disposition_snapshot rather than live master list when they differ", () => {
    const markupSnapshot = renderToStaticMarkup(renderDispositionFromSnapshot(mockRecordNullSeverity));
    expect(markupSnapshot).toContain("원래 스냅샷 처리방안");

    const mockRecordCodeOnly: Nonconformance = {
      ...mockRecordNullSeverity,
      disposition_snapshot: { id: "disp-01", code: "SNAPSHOT_CODE_ONLY" },
    };
    const markupCode = renderToStaticMarkup(renderDispositionFromSnapshot(mockRecordCodeOnly));
    expect(markupCode).toContain("SNAPSHOT_CODE_ONLY");

    const mockRecordNoSnapshot: Nonconformance = {
      ...mockRecordNullSeverity,
      disposition_snapshot: null,
    };
    const markupEmpty = renderToStaticMarkup(renderDispositionFromSnapshot(mockRecordNoSnapshot));
    expect(markupEmpty).toContain("처리방안 미지정");
  });

  it("disables edit and action controls when status is APPROVED", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => [mockApprovedRecord],
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(NonconformanceWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      const updateBtn = container.querySelector('[data-testid="edit-update-button"]') as HTMLButtonElement;
      const approveBtn = container.querySelector('[data-testid="approve-ncr-button"]') as HTMLButtonElement;
      const rejectBtn = container.querySelector('[data-testid="reject-ncr-button"]') as HTMLButtonElement;

      expect(updateBtn?.disabled).toBe(true);
      expect(approveBtn?.disabled).toBe(true);
      expect(rejectBtn?.disabled).toBe(true);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("surfaces a 403 permission error message when non-LEAD role attempts approval", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/approve")) {
        return {
          ok: false,
          status: 403,
          json: async () => ({ message: "LEAD role required for approval" }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => [mockRecordNullSeverity],
      };
    });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(NonconformanceWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      const approveBtn = container.querySelector('[data-testid="approve-ncr-button"]') as HTMLButtonElement;
      expect(approveBtn).not.toBeNull();

      await act(async () => {
        approveBtn.click();
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(container.textContent).toContain("403");
      expect(container.textContent).toContain("LEAD");

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("surfaces a 409 conflict message and does not crash when API returns a 409 error", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/approve") || url.includes("/nonconformances/test-01")) {
        return {
          ok: false,
          status: 409,
          json: async () => ({ message: "Version conflict or immutable record" }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => [mockRecordNullSeverity],
      };
    });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(NonconformanceWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      const approveBtn = container.querySelector('[data-testid="approve-ncr-button"]') as HTMLButtonElement;

      await act(async () => {
        approveBtn.click();
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(container.textContent).toContain("409");

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("executes ZERO fetch calls at runtime when mounted with publicDemo=true", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(NonconformanceWorkspace, { publicDemo: true }));
      });

      expect(fetchSpy).toHaveBeenCalledTimes(0);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("executes fetch calls at runtime when mounted with publicDemo=false", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(NonconformanceWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(fetchSpy).toHaveBeenCalled();
      const calledUrls = fetchSpy.mock.calls.map((call) => String(call[0]));
      expect(calledUrls.some((url) => url.includes("/api/v1/nonconformances"))).toBe(true);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
