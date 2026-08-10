// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { MasterDataWorkspace, renderCodeCell } from "../src/components/master-data/MasterDataWorkspace";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe("MasterDataWorkspace client & UI boundary", () => {
  it("renders a clear placeholder for null or empty master codes without displaying null or empty text", () => {
    const markupNull = renderToStaticMarkup(renderCodeCell(null));
    expect(markupNull).toContain("코드 미할당");
    expect(markupNull).not.toContain(">null<");

    const markupUndefined = renderToStaticMarkup(renderCodeCell(undefined));
    expect(markupUndefined).toContain("코드 미할당");

    const markupEmpty = renderToStaticMarkup(renderCodeCell("   "));
    expect(markupEmpty).toContain("코드 미할당");

    const markupValid = renderToStaticMarkup(renderCodeCell("SUP-001"));
    expect(markupValid).toContain("SUP-001");
    expect(markupValid).not.toContain("코드 미할당");

    const workspaceMarkup = renderToStaticMarkup(
      React.createElement(MasterDataWorkspace, { publicDemo: true })
    );
    expect(workspaceMarkup).toContain("코드 미할당");
    expect(workspaceMarkup).not.toContain(">null<");
    expect(workspaceMarkup).not.toContain("<td>null</td>");
  });

  it("surfaces a 409 conflict message rather than crashing when API returns a 409 error", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: false,
      status: 409,
      json: async () => ({ message: "Version lock conflict or duplicate master code" }),
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(MasterDataWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(container.textContent).toContain("API 409");
      expect(container.textContent).toContain("Version lock conflict or duplicate master code");

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
        root.render(React.createElement(MasterDataWorkspace, { publicDemo: true }));
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
        root.render(React.createElement(MasterDataWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      expect(fetchSpy).toHaveBeenCalled();
      const calledUrls = fetchSpy.mock.calls.map((call) => String(call[0]));
      expect(calledUrls.some((url) => url.includes("/api/v1/suppliers"))).toBe(true);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
