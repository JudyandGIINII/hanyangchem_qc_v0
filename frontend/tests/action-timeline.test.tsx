// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActionTimeline } from "../src/components/nonconformance/ActionTimeline";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const NCR_ID = "11111111-1111-4111-8111-111111111111";
const ACTIONS_PATH = `/api/v1/nonconformances/${NCR_ID}/actions`;

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body };
}

async function mount(props: { publicDemo: boolean; role: string }) {
  const container = document.body.appendChild(document.createElement("div"));
  const root = createRoot(container);
  await act(async () => {
    root.render(
      React.createElement(ActionTimeline, {
        publicDemo: props.publicDemo,
        nonconformanceId: NCR_ID,
        role: props.role,
      }),
    );
  });
  return container;
}

describe("ActionTimeline", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("issues zero fetch calls under publicDemo=true", async () => {
    const spy = vi.spyOn(globalThis, "fetch");
    const container = await mount({ publicDemo: true, role: "LEAD" });

    const notice = container.querySelector('[data-testid="action-timeline-public-notice"]');
    expect(notice).not.toBeNull();
    expect(notice?.textContent).toContain("서버 연결 없음");
    expect(spy).not.toHaveBeenCalled();
  });

  it("does fetch the actions path under publicDemo=false — the positive control", async () => {
    // Without this the zero-fetch assertion above would also hold if the
    // component simply failed to mount.
    const spy = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse([]) as unknown as Response);
    await mount({ publicDemo: false, role: "LEAD" });

    expect(spy).toHaveBeenCalled();
    expect(String(spy.mock.calls[0][0])).toBe(ACTIONS_PATH);
  });

  it("renders a readable placeholder for an empty timeline", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]) as unknown as Response);
    const container = await mount({ publicDemo: false, role: "LEAD" });

    const rows = container.querySelector('[data-testid="action-timeline-rows"]');
    expect(rows).not.toBeNull();
    expect(rows?.textContent).toContain("기록된 후속조치가 없습니다.");
  });

  it("states that the history is append-only and leaves the record untouched", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]) as unknown as Response);
    const container = await mount({ publicDemo: false, role: "LEAD" });

    const note = container.querySelector('[data-testid="action-timeline-append-only-note"]');
    expect(note).not.toBeNull();
    expect(note?.textContent).toContain("추가만 가능한 이력");
  });

  it("disables submission while the description is empty", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]) as unknown as Response);
    const container = await mount({ publicDemo: false, role: "LEAD" });

    const button = container.querySelector('[data-testid="action-submit"]') as HTMLButtonElement | null;
    expect(button).not.toBeNull();
    expect(button?.disabled).toBe(true);
  });

  it("offers 종결 to a LEAD but not to an INSPECTOR", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(jsonResponse([]) as unknown as Response);

    const leadOptions = Array.from(
      (await mount({ publicDemo: false, role: "LEAD" })).querySelectorAll("option"),
    ).map((option) => option.value);
    expect(leadOptions).toContain("COMPLETION");

    const inspectorOptions = Array.from(
      (await mount({ publicDemo: false, role: "INSPECTOR" })).querySelectorAll("option"),
    ).map((option) => option.value);
    expect(inspectorOptions).not.toContain("COMPLETION");
  });

  it("surfaces a 403 rather than a blank panel, because hiding an option is not authorisation", async () => {
    vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(jsonResponse([]) as unknown as Response)
      .mockResolvedValueOnce(jsonResponse({ detail: "denied" }, 403) as unknown as Response);
    const container = await mount({ publicDemo: false, role: "LEAD" });

    const input = container.querySelector("#action-description") as HTMLInputElement | null;
    expect(input).not.toBeNull();
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLInputElement.prototype,
        "value",
      )?.set;
      setter?.call(input, "종결 시도");
      input?.dispatchEvent(new Event("input", { bubbles: true }));
    });

    const button = container.querySelector('[data-testid="action-submit"]') as HTMLButtonElement | null;
    expect(button).not.toBeNull();
    expect(button?.disabled).toBe(false);
    await act(async () => {
      button?.click();
    });

    const error = container.querySelector('[data-testid="action-timeline-error"]');
    expect(error).not.toBeNull();
    expect(error?.textContent).toContain("403");
  });

  it("renders a readable Korean error when the list request fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse({ detail: "boom" }, 503) as unknown as Response,
    );
    const container = await mount({ publicDemo: false, role: "LEAD" });

    const error = container.querySelector('[data-testid="action-timeline-error"]');
    expect(error).not.toBeNull();
    expect(error?.textContent).toContain("후속조치 조회에 실패했습니다 (503).");
  });
});
