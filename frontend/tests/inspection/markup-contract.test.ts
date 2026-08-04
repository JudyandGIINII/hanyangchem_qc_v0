import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const DYNAMIC_CLASS_TOKENS = [
  "notice",
  "notice-info",
  "notice-warn",
  "notice-warning",
  "notice-danger",
  "notice-success",
] as const;

function classTokensFromSource(source: string): string[] {
  const tokens = new Set<string>();
  const classNameValues = source.matchAll(/className=(?:"([^"]*)"|\{([^}]*)\})/g);

  for (const match of classNameValues) {
    const value = match[1] ?? match[2] ?? "";
    // In JSX expressions, take the string values assigned by a ternary, not
    // comparison operands such as `field.confidence === "HIGH"`.
    for (const quotedValue of value.matchAll(/(?:\?|:)\s*["']([^"']*)["']/g)) {
      for (const token of quotedValue[1].split(/\s+/)) {
        if (token && !token.includes("${")) tokens.add(token);
      }
    }
    if (match[1]) {
      for (const token of match[1].split(/\s+/)) if (token) tokens.add(token);
    }
  }

  return [...tokens];
}

function hasClassSelector(css: string, token: string): boolean {
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`\\.${escaped}(?=[\\s.:#>+~[,\\{]|$)`).test(css);
}

function cssRule(css: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = css.match(new RegExp(`${escaped}\\s*\\{([^}]*)\\}`));
  expect(match, `missing ${selector} rule`).not.toBeNull();
  return match?.[1] ?? "";
}

function inspectionSources(): string[] {
  const inspectionDirectory = resolve(process.cwd(), "src/components/inspection");
  return readdirSync(inspectionDirectory, { recursive: true })
    .filter((entry): entry is string => typeof entry === "string" && entry.endsWith(".tsx"))
    .map((entry) => readFileSync(resolve(inspectionDirectory, entry), "utf8"));
}

describe("inspection workspace source contract", () => {
  it("renders every Korean workflow stage and the fixture boundaries", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    for (const label of ["목록", "입고/LOT", "문서 검토", "매칭", "자체검사", "제출", "팀장 검토", "LOT 추적"]) {
      expect(workspace).toContain(label);
    }
    expect(workspace).toContain("LOCAL-ONLY OCR");
    expect(workspace).toContain("서버 저장 없음");
    expect(workspace).toContain("실제 문서 아님");
    expect(workspace).toContain("production LOT automatic ERP link is not enabled");
  });

  it("styles every literal inspection class and its documented dynamic notice tones", () => {
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");
    const classTokens = [...inspectionSources().flatMap(classTokensFromSource), ...DYNAMIC_CLASS_TOKENS];
    const missing = classTokens.filter((token) => !hasClassSelector(css, token));

    // Template fragments such as notice-${tone} cannot be statically enumerated;
    // the supported values above are the documented source-contract exception.
    expect(missing).toEqual([]);
    expect(css).not.toMatch(/\.hyc-shell(?=[\s.:#>+~,\x5b{]|$)/);
  });

  it("allows long fixture and trace identifiers to wrap without masking page overflow", () => {
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

    expect(cssRule(css, ".fixture-banner > span")).toMatch(/min-width:\s*0[\s\S]*overflow-wrap:\s*anywhere/);
    expect(cssRule(css, ".case-header > div")).toMatch(/min-width:\s*0/);
    expect(cssRule(css, ".case-header p")).toMatch(/overflow-wrap:\s*anywhere/);
    expect(cssRule(css, ".case-header strong")).toMatch(/overflow-wrap:\s*anywhere/);
    expect(cssRule(css, ".case-meta")).toMatch(/min-width:\s*0/);
    expect(cssRule(css, ".case-meta span")).toMatch(/min-width:\s*0[\s\S]*overflow-wrap:\s*anywhere/);
    expect(cssRule(css, ".relationship-strip strong")).toMatch(/min-width:\s*0[\s\S]*overflow-wrap:\s*anywhere/);
    expect(cssRule(css, ".timeline li > div")).toMatch(/min-width:\s*0/);
    expect(cssRule(css, ".timeline small")).toMatch(/overflow-wrap:\s*anywhere/);
    expect(css).not.toMatch(/body\s*\{[^}]*overflow-x\s*:/);
    expect(css).not.toMatch(/overflow-x:\s*hidden/);

    for (const scrollRegion of [".stage-nav", ".progress", ".table-wrap"]) {
      expect(cssRule(css, scrollRegion)).toMatch(/overflow-x:\s*auto/);
      expect(cssRule(css, scrollRegion)).toMatch(/overscroll-behavior-x:\s*contain/);
    }
  });

  it("keeps role, progress, live-status, focus, and placeholder accessibility contracts explicit", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

    expect(workspace).toContain('aria-pressed={state.selectedRole === role}');
    expect(workspace).toContain('aria-current={active === stage ? "step" : undefined}');
    expect(workspace).toContain("시뮬레이션 역할: {state.selectedRole}");
    expect(cssRule(css, "button:focus-visible,\ninput:focus-visible,\nselect:focus-visible,\ntextarea:focus-visible,\n.table-wrap:focus-visible")).toMatch(/outline:\s*3px solid var\(--teal-700\)/);
    expect(cssRule(css, "input::placeholder,\ntextarea::placeholder")).toMatch(/color:\s*var\(--slate-700\)/);
  });

  it("associates each visible label with a deterministic control id", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");

    expect(workspace).toContain("htmlFor: string");
    expect(workspace).not.toMatch(/<Label(?!\s+htmlFor)/);
    for (const id of ["queue-search", "queue-filter", "submit-reason", "review-reason"]) {
      expect(workspace).toContain(`htmlFor="${id}"`);
      expect(workspace).toContain(`id="${id}"`);
    }
    expect(workspace).toContain("htmlFor={`receipt-${field}`}");
    expect(workspace).toContain("id={`receipt-${field}`}");
    expect(workspace).toContain("htmlFor={`internal-sample-${item.id}-${index}`}");
    expect(workspace).toContain("id={`internal-sample-${item.id}-${index}`}");
  });

  it("distinguishes screen navigation from workflow completion and keeps submission copy status-aware", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");

    expect(workspace).toContain('className="progress" aria-label="워크플로 화면 단계"');
    expect(workspace).not.toContain('className="progress" aria-label="워크플로 진행 상태"');
    expect(workspace).toContain('aria-current={active === stage ? "step" : undefined}');
    expect(workspace).toContain("제출 후 팀장 검토 대기 — 입력 잠금");
    expect(workspace).toContain("이미 제출됨 — 팀장 검토 대기");
    expect(workspace).toContain("팀장 반려 후 보완 상태입니다. 내용을 수정한 뒤 재제출할 수 있습니다.");
    expect(workspace).toContain("보완 후 재제출 (서버 저장 없음)");
    expect(workspace).toContain("승인되어 동결되었습니다. 수정 또는 재제출할 수 없습니다.");
    expect(workspace).toContain("승인·동결됨");
    expect(workspace).toContain("제출 전 preflight가 완료되었습니다.");
  });

  it("marks table headers and scroll wrappers with explicit table semantics", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    const headers = workspace.match(/<th\b[^>]*>/g) ?? [];
    const tableRegions = workspace.match(/<div className="table-wrap" role="region" tabIndex=\{0\} aria-label="[^"]+">/g) ?? [];

    expect(headers).not.toEqual([]);
    expect(headers.every((header) => /scope="(?:col|row)"/.test(header))).toBe(true);
    expect(headers.some((header) => header.includes('scope="row"'))).toBe(true);
    expect(tableRegions).toHaveLength(4);
  });

  it("locks submitted mutations, persists document reasons, and exposes state-dependent internal completion copy", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");
    const css = readFileSync(resolve(process.cwd(), "src/app/globals.css"), "utf8");

    expect(workspace).toContain('const mutationLocked = state.workflowStatus === "SUBMITTED" || frozen;');
    expect(workspace).toContain("disabled={mutationLocked}");
    expect(workspace).toContain("const typedReason = reasons[id]?.trim();");
    expect(workspace).toContain("setReasons((current) => ({ ...current, [id]: reason }))");
    expect(workspace).toContain('type: "confirmInternalTest"');
    expect(workspace).toContain("입력값 확정");
    expect(workspace).toContain("aria-describedby={receiptErrors");
    expect(workspace).toContain("aria-describedby={invalid ? errorId : undefined}");
    expect(workspace).toContain('className={internalComplete ? "complete-mark" : "hold-badge"}');
    expect(workspace).toContain('{internalComplete ? "필수 자체검사 완료" : "INTERNAL_TEST_PENDING"}');
    expect(workspace).toContain('공급사 판정 {item.supplierDecision}');
    expect(workspace).not.toContain('공급사 후보 {item.supplierDecision}');
    expect(css).toMatch(/\.compact\s*\{\s*min-height:\s*36px/);
    expect(css).toMatch(/\.compact,\n\s*\.text-button\s*\{\s*min-height:\s*44px/);
  });

  it("derives a unique validation relationship for every invalid internal sample row", () => {
    const workspace = readFileSync(resolve(process.cwd(), "src/components/inspection/InspectionWorkspace.tsx"), "utf8");

    expect(workspace).toContain('const errorId = `internal-${item.id}-sample-${index}-error`;');
    expect(workspace).toContain('aria-describedby={invalid ? errorId : undefined}');
    expect(workspace).toContain('<small id={errorId} className="error-text">');
    const sampleErrorIds = ["FX-INTERNAL-MOISTURE-01", "FX-INTERNAL-APPEARANCE-01"].flatMap((itemId) =>
      [0, 1].map((index) => `internal-${itemId}-sample-${index}-error`),
    );
    expect(new Set(sampleErrorIds).size).toBe(sampleErrorIds.length);
  });
});
