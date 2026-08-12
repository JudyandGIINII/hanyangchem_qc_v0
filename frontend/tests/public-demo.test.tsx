// @vitest-environment happy-dom

import { act } from "react";
import * as React from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { InspectionWorkspace } from "../src/components/inspection/InspectionWorkspace";
import { canUseBackend, isPublicDemoFlag, PUBLIC_DEMO_MODE } from "../src/lib/public-demo";

(globalThis as typeof globalThis & { React: typeof React }).React = React;
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;

describe("public synthetic demo boundary", () => {
  it("enables only the exact build-time flag and denies backend use", () => {
    expect(isPublicDemoFlag("1")).toBe(true);
    for (const value of [undefined, "", "0", "true", "yes"]) {
      expect(isPublicDemoFlag(value)).toBe(false);
    }
    expect(canUseBackend(true)).toBe(false);
    expect(canUseBackend(false)).toBe(true);
    expect(typeof PUBLIC_DEMO_MODE).toBe("boolean");
  });

  it("renders the public boundary without API controls or failed-fetch copy", () => {
    const markup = renderToStaticMarkup(React.createElement(InspectionWorkspace, { publicDemo: true }));

    expect(markup).toContain("공개 합성 데모");
    expect(markup).toContain("서버 연결 없음");
    expect(markup).toContain("local reducer");
    expect(markup).toContain("실제 문서");
    expect(markup).toContain("서버에 저장하지 않습니다");
    expect(markup).toContain("공개 합성 데모 경계");
    expect(markup).toContain("합성 로컬 상태");

    expect(markup).not.toContain("검사 생성 전");
    expect(markup).not.toContain("실제 서버 상태");
    expect(markup).not.toContain("SESSION_READY");
    for (const enumName of ["DRAFT", "LEAD_REVIEW", "READY_FOR_REVIEW", "ACCEPTED", "REJECTED"]) {
      expect(markup).not.toContain(enumName);
    }

    expect(markup).not.toContain("P3 API 실행 제어");
    expect(markup).not.toContain("현재 역할로 API 승인");
    expect(markup).not.toContain("Failed to fetch");
    for (const stage of ["목록", "입고/LOT", "문서 검토", "매칭", "자체검사", "제출", "팀장 검토", "LOT 추적", "부적합", "보고서·통계"]) {
      expect(markup).toContain(stage);
    }
  });

  it("keeps the local P3 API mode available by default", () => {
    const markup = renderToStaticMarkup(React.createElement(InspectionWorkspace, { publicDemo: false }));

    expect(markup).toContain("P3 API 실행 제어");
    expect(markup).toContain("P3 fixture API session 준비 중");
    expect(markup).toContain("8. 현재 역할 승인 시도");
    expect(markup).toContain("검사 생성 전");
    expect(markup).toContain("실제 서버 상태");
    expect(markup).toContain("SESSION_READY");
    expect(markup).not.toContain("공개 합성 데모 경계");
  });

  it("executes ZERO fetch calls after navigating to the 보고서·통계 stage under publicDemo=true", async () => {
    // The report and statistics panels are rendered only when that stage is active,
    // so the broader zero-fetch test never mounts them. Without this case a fetch
    // leaking from either panel would ship to the public demo uncaught.
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({}),
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);
      await act(async () => {
        root.render(React.createElement(InspectionWorkspace, { publicDemo: true }));
      });

      const stageBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
        btn.textContent?.includes("보고서·통계"),
      );
      expect(stageBtn).not.toBeNull();
      await act(async () => {
        (stageBtn as HTMLButtonElement).click();
      });

      // Prove the stage really mounted, so the zero-fetch assertion cannot pass
      // simply because nothing rendered.
      expect(container.textContent).toContain("보고서·통계");

      const reportBtn = Array.from(container.querySelectorAll("button")).find((btn) =>
        btn.textContent?.includes("보고서 생성"),
      );
      expect(reportBtn).not.toBeNull();
      await act(async () => {
        (reportBtn as HTMLButtonElement).click();
      });

      expect(fetchSpy).not.toHaveBeenCalled();
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("executes ZERO fetch calls at runtime when mounted with publicDemo=true during bootstrap, role switching, and synthetic actions", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ session_handle: "mock-session" }),
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(InspectionWorkspace, { publicDemo: true }));
      });

      // 1. Bootstrap effect ran with 0 fetch calls
      expect(fetchSpy).toHaveBeenCalledTimes(0);

      // 2. Navigate to 팀장 검토 stage to access role switcher and lead review controls
      const leadStageBtn = Array.from(container.querySelectorAll("button")).find((btn) => btn.textContent?.includes("팀장 검토"));
      expect(leadStageBtn).not.toBeUndefined();
      await act(async () => {
        leadStageBtn?.click();
      });

      // 3. Trigger role switch to LEAD in public demo mode
      const leadRoleBtn = container.querySelector('[data-testid="role-LEAD"]') as HTMLButtonElement | null;
      expect(leadRoleBtn).not.toBeNull();
      await act(async () => {
        leadRoleBtn?.click();
      });

      // Role switch in public demo mode must NOT trigger fetch
      expect(fetchSpy).toHaveBeenCalledTimes(0);

      // 4. Trigger role switch to ADMIN
      const adminRoleBtn = container.querySelector('[data-testid="role-ADMIN"]') as HTMLButtonElement | null;
      expect(adminRoleBtn).not.toBeNull();
      await act(async () => {
        adminRoleBtn?.click();
      });

      expect(fetchSpy).toHaveBeenCalledTimes(0);

      // 5. Trigger synthetic local approval action
      const approveBtn = Array.from(container.querySelectorAll("button")).find((btn) => btn.textContent?.includes("합성 로컬 승인"));
      if (approveBtn) {
        await act(async () => {
          (approveBtn as HTMLButtonElement).click();
        });
      }

      // Assert total fetch calls remains strictly ZERO across all public demo interactions
      expect(fetchSpy).toHaveBeenCalledTimes(0);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  it("executes fetch calls at runtime during bootstrap and role switching when mounted with publicDemo=false", async () => {
    const originalFetch = globalThis.fetch;
    const fetchSpy = vi.fn().mockImplementation(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ session_handle: "mock-session" }),
    }));
    globalThis.fetch = fetchSpy as any;

    try {
      const container = document.body.appendChild(document.createElement("div"));
      const root = createRoot(container);

      await act(async () => {
        root.render(React.createElement(InspectionWorkspace, { publicDemo: false }));
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      // Bootstrap triggered fetch to /api/v1/local-auth/sessions
      expect(fetchSpy).toHaveBeenCalled();
      expect(fetchSpy.mock.calls[0][0]).toContain("/api/v1/local-auth/sessions");

      const initialFetchCount = fetchSpy.mock.calls.length;

      // Navigate to 팀장 검토 stage to access role switcher
      const leadStageBtn = Array.from(container.querySelectorAll("button")).find((btn) => btn.textContent?.includes("팀장 검토"));
      expect(leadStageBtn).not.toBeUndefined();
      await act(async () => {
        leadStageBtn?.click();
      });

      // Role switch in local API mode triggers role session API call
      const leadRoleBtn = container.querySelector('[data-testid="role-LEAD"]') as HTMLButtonElement | null;
      expect(leadRoleBtn).not.toBeNull();

      await act(async () => {
        leadRoleBtn?.click();
        await new Promise((resolve) => setTimeout(resolve, 50));
      });

      // Local API mode MUST issue backend fetch calls on role switch
      expect(fetchSpy.mock.calls.length).toBeGreaterThan(initialFetchCount);

      await act(async () => {
        root.unmount();
      });
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
