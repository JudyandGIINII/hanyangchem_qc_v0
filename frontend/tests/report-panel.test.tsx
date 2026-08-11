// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

import { ReportPanel } from "../src/components/reports/ReportPanel";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe("ReportPanel", () => {
  it("public demo issues zero fetches", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn();
    globalThis.fetch = fetchSpy as any;

    const container = document.body.appendChild(document.createElement("div"));
    const root = createRoot(container);

    try {
      await act(async () => {
        root.render(React.createElement(ReportPanel, { publicDemo: true, caseId: "case-1" }));
      });

      const button = container.querySelector("button");
      if (!button) {
        throw new Error("Missing selector: button");
      }

      await act(async () => {
        button.click();
      });

      expect(container.textContent).toContain("공개 합성 데모");
      expect(fetchSpy).not.toHaveBeenCalled();

      await act(async () => {
        root.unmount();
      });
    } finally {
      container.remove();
      globalThis.fetch = originalFetch;
    }
  });

  it("local mode does fetch — the positive control", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 202,
      json: async () => ({ job_id: "j1", state: "SUCCEEDED" }),
    }));
    globalThis.fetch = fetchSpy as any;

    const container = document.body.appendChild(document.createElement("div"));
    const root = createRoot(container);

    try {
      await act(async () => {
        root.render(React.createElement(ReportPanel, { publicDemo: false, caseId: "case-1" }));
      });

      const button = container.querySelector("button");
      if (!button) {
        throw new Error("Missing selector: button");
      }

      await act(async () => {
        button.click();
      });

      expect(fetchSpy).toHaveBeenCalled();
      const calledUrl = String(fetchSpy.mock.calls[0][0]);
      expect(calledUrl).toContain("/api/v1/reports");

      await act(async () => {
        root.unmount();
      });
    } finally {
      container.remove();
      globalThis.fetch = originalFetch;
    }
  });

  it("shows a readable message when the job fails with APPROVAL_SNAPSHOT_MISSING", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi
      .fn()
      .mockImplementationOnce(async () => ({
        ok: true,
        status: 202,
        json: async () => ({ job_id: "j1", state: "QUEUED" }),
      }))
      .mockImplementation(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          job_id: "j1",
          state: "FAILED",
          failure_code: "APPROVAL_SNAPSHOT_MISSING",
        }),
      }));
    globalThis.fetch = fetchSpy as any;

    const container = document.body.appendChild(document.createElement("div"));
    const root = createRoot(container);

    try {
      await act(async () => {
        root.render(React.createElement(ReportPanel, { publicDemo: false, caseId: "case-1" }));
      });

      const button = container.querySelector("button");
      if (!button) {
        throw new Error("Missing selector: button");
      }

      await act(async () => {
        button.click();
      });

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(container.textContent).toContain("승인 스냅샷이 없어 보고서를 만들 수 없습니다");

      await act(async () => {
        root.unmount();
      });
    } finally {
      container.remove();
      globalThis.fetch = originalFetch;
    }
  });

  it("displays raw failure_code for unmapped error codes", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi
      .fn()
      .mockImplementationOnce(async () => ({
        ok: true,
        status: 202,
        json: async () => ({ job_id: "j2", state: "QUEUED" }),
      }))
      .mockImplementation(async () => ({
        ok: true,
        status: 200,
        json: async () => ({
          job_id: "j2",
          state: "FAILED",
          failure_code: "UNKNOWN_CUSTOM_ERROR",
        }),
      }));
    globalThis.fetch = fetchSpy as any;

    const container = document.body.appendChild(document.createElement("div"));
    const root = createRoot(container);

    try {
      await act(async () => {
        root.render(React.createElement(ReportPanel, { publicDemo: false, caseId: "case-2" }));
      });

      const button = container.querySelector("button");
      if (!button) {
        throw new Error("Missing selector: button");
      }

      await act(async () => {
        button.click();
      });

      await act(async () => {
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(container.textContent).toContain("UNKNOWN_CUSTOM_ERROR");

      await act(async () => {
        root.unmount();
      });
    } finally {
      container.remove();
      globalThis.fetch = originalFetch;
    }
  });
});
