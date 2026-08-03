import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import * as React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { InspectionWorkspace } from "../src/components/inspection/InspectionWorkspace";
import { canUseBackend, isPublicDemoFlag } from "../src/lib/public-demo";

(globalThis as typeof globalThis & { React: typeof React }).React = React;

describe("public synthetic demo boundary", () => {
  it("enables only the exact build-time flag and denies backend use", () => {
    expect(isPublicDemoFlag("1")).toBe(true);
    for (const value of [undefined, "", "0", "true", "yes"]) {
      expect(isPublicDemoFlag(value)).toBe(false);
    }
    expect(canUseBackend(true)).toBe(false);
    expect(canUseBackend(false)).toBe(true);
  });

  it("renders the public boundary without API controls or failed-fetch copy", () => {
    const markup = renderToStaticMarkup(React.createElement(InspectionWorkspace, { publicDemo: true }));

    expect(markup).toContain("공개 합성 데모");
    expect(markup).toContain("서버 연결 없음");
    expect(markup).toContain("local reducer");
    expect(markup).toContain("실제 문서");
    expect(markup).toContain("서버에 저장하지 않습니다");
    expect(markup).toContain("공개 합성 데모 경계");
    expect(markup).not.toContain("P3 API 실행 제어");
    expect(markup).not.toContain("현재 역할로 API 승인");
    expect(markup).not.toContain("Failed to fetch");
    for (const stage of ["목록", "입고/LOT", "문서 검토", "매칭", "자체검사", "제출", "팀장 검토", "LOT 추적"]) {
      expect(markup).toContain(stage);
    }
  });

  it("keeps the local P3 API mode available by default", () => {
    const markup = renderToStaticMarkup(React.createElement(InspectionWorkspace, { publicDemo: false }));

    expect(markup).toContain("P3 API 실행 제어");
    expect(markup).toContain("P3 fixture API session 준비 중");
    expect(markup).toContain("8. 현재 역할 승인 시도");
    expect(markup).not.toContain("공개 합성 데모 경계");
  });

  it("guards bootstrap, every API action, and public role switching before network calls", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    const publicDemoModule = readFileSync(resolve(process.cwd(), "src/lib/public-demo.ts"), "utf8");
    const effectStart = workspace.indexOf("  useEffect(() =>");
    const runApi = workspace.slice(workspace.indexOf("const runApi"), effectStart);
    const bootstrap = workspace.slice(effectStart, workspace.indexOf("const switchFixtureRole"));
    const roleSwitch = workspace.slice(workspace.indexOf("const switchFixtureRole"), workspace.indexOf("const finishField"));

    expect(runApi.indexOf("!canUseBackend(publicDemo)")).toBeGreaterThanOrEqual(0);
    expect(runApi.indexOf("!canUseBackend(publicDemo)")).toBeLessThan(runApi.indexOf("await action()"));
    expect(bootstrap.indexOf("!canUseBackend(publicDemo)")).toBeGreaterThanOrEqual(0);
    expect(bootstrap.indexOf("!canUseBackend(publicDemo)")).toBeLessThan(bootstrap.indexOf('fixtureSession("INSPECTOR")'));
    expect(roleSwitch.indexOf("!canUseBackend(publicDemo)")).toBeGreaterThanOrEqual(0);
    expect(roleSwitch.indexOf('dispatch({ type: "setRole", role })')).toBeLessThan(roleSwitch.indexOf("fixtureSession(role)"));
    expect(workspace).toContain('dispatch({ type: "approve", reason: reviewReason })');
    expect(workspace).toContain("합성 로컬 승인 (서버 저장 없음)");
    expect(publicDemoModule).toContain("PUBLIC_DEMO_MODE = isPublicDemoFlag(process.env.NEXT_PUBLIC_HYC_PUBLIC_DEMO)");
  });
});
