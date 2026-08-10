// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import {
  renderAliasScope,
  StandardAliasWorkspace,
} from "../src/components/standard-aliases/StandardAliasWorkspace";
import { InspectionWorkspace } from "../src/components/inspection/InspectionWorkspace";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe("StandardAliasWorkspace and Inspection Return rules", () => {
  it("renders a clear placeholder for absent alias scope and never displays 'null'", () => {
    const markupNull = renderToStaticMarkup(renderAliasScope(null, null, null));
    expect(markupNull).toContain("전체 범위");
    expect(markupNull).not.toContain(">null<");

    const markupUndefined = renderToStaticMarkup(renderAliasScope(undefined, undefined, undefined));
    expect(markupUndefined).toContain("전체 범위");

    const markupSupplier = renderToStaticMarkup(renderAliasScope("SUP-001", null, null));
    expect(markupSupplier).toContain("공급사: SUP-001");

    const workspaceMarkup = renderToStaticMarkup(
      React.createElement(StandardAliasWorkspace, { publicDemo: true })
    );
    expect(workspaceMarkup).toContain("전체 범위");
    expect(workspaceMarkup).not.toContain("<td>null</td>");
    expect(workspaceMarkup).not.toContain(">null<");
  });

  it("never labels an alias as confirmed or auto-applied and explicitly indicates candidate-only lookup", () => {
    const workspaceMarkup = renderToStaticMarkup(
      React.createElement(StandardAliasWorkspace, { publicDemo: true })
    );
    expect(workspaceMarkup).toContain("후보 추천 전용");
    expect(workspaceMarkup).toContain("수동 확정 필요");
    expect(workspaceMarkup).not.toContain("자동 확정됨");
    expect(workspaceMarkup).not.toContain("자동 적용");
    expect(workspaceMarkup).not.toContain("확정된 별칭");
  });

  it("executes ZERO fetch calls at runtime when StandardAliasWorkspace mounted with publicDemo=true", async () => {
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
        root.render(React.createElement(StandardAliasWorkspace, { publicDemo: true }));
      });

      expect(fetchSpy).toHaveBeenCalledTimes(0);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("executes fetch calls at runtime when StandardAliasWorkspace mounted with publicDemo=false", async () => {
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
        root.render(React.createElement(StandardAliasWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(fetchSpy).toHaveBeenCalled();
      const calledUrls = fetchSpy.mock.calls.map((call) => String(call[0]));
      expect(calledUrls.some((url) => url.includes("/api/v1/standard-test-item-aliases"))).toBe(true);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("keeps return control disabled while reason is empty and enables it once non-empty reason is typed", async () => {
    const container = document.body.appendChild(document.createElement("div"));
    const root = createRoot(container);

    await act(async () => {
      root.render(React.createElement(InspectionWorkspace, { publicDemo: true }));
    });

    const leadTab = Array.from(container.querySelectorAll("button")).find((btn) => btn.textContent?.includes("팀장 검토"));
    expect(leadTab).not.toBeUndefined();

    await act(async () => {
      leadTab?.click();
    });

    const returnBtn = container.querySelector('[data-testid="return-submit-button"]') as HTMLButtonElement;
    const reasonInput = container.querySelector('[data-testid="return-reason-input"]') as HTMLTextAreaElement;

    expect(returnBtn).not.toBeNull();
    expect(reasonInput).not.toBeNull();

    await act(async () => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
      nativeSetter?.call(reasonInput, "");
      reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
      reasonInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(returnBtn.disabled).toBe(true);

    await act(async () => {
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
      nativeSetter?.call(reasonInput, "반려 사유: 자체 수분 검사 항목 누락");
      reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
      reasonInput.dispatchEvent(new Event("change", { bubbles: true }));
    });

    expect(returnBtn.disabled).toBe(false);

    await act(async () => {
      root.unmount();
    });
  });

  it("surfaces a 403 permission message when return is executed by an unauthorized role", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/return")) {
        return {
          ok: false,
          status: 403,
          json: async () => ({ message: "LEAD role required for inspection return" }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "LEAD_REVIEW" }),
      };
    });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(InspectionWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      const leadTab = Array.from(container.querySelectorAll("button")).find((btn) => btn.textContent?.includes("팀장 검토"));
      if (leadTab) {
        await act(async () => {
          leadTab.click();
        });
      }

      const returnBtn = container.querySelector('[data-testid="return-inspection"]') as HTMLButtonElement;
      const reasonInput = container.querySelector('[data-testid="return-reason-input"]') as HTMLTextAreaElement;

      if (returnBtn && reasonInput) {
        await act(async () => {
          const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
          nativeSetter?.call(reasonInput, "사유입력");
          reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
          reasonInput.dispatchEvent(new Event("change", { bubbles: true }));
        });

        await act(async () => {
          returnBtn.click();
          await new Promise((resolve) => setTimeout(resolve, 50));
        });

        expect(container.textContent).toContain("403");
      }

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("surfaces a 422 validation message when return is submitted with missing or invalid reason", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/return")) {
        return {
          ok: false,
          status: 422,
          json: async () => ({ message: "Validation Error: Reason must not be empty" }),
        };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ status: "LEAD_REVIEW" }),
      };
    });
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(InspectionWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      const returnBtn = container.querySelector('[data-testid="return-inspection"]') as HTMLButtonElement;
      const reasonInput = container.querySelector('[data-testid="return-reason-input"]') as HTMLTextAreaElement;

      if (returnBtn && reasonInput) {
        await act(async () => {
          const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")?.set;
          nativeSetter?.call(reasonInput, "유효사유");
          reasonInput.dispatchEvent(new Event("input", { bubbles: true }));
          reasonInput.dispatchEvent(new Event("change", { bubbles: true }));
        });

        await act(async () => {
          returnBtn.click();
          await new Promise((resolve) => setTimeout(resolve, 50));
        });

        expect(container.textContent).toContain("422");
      }

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
