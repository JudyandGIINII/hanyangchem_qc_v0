import { expect, test } from "@playwright/test";

async function reachInspection(page: import("@playwright/test").Page) {
  await page.addInitScript((base) => window.localStorage.setItem("P3_API_BASE", base), process.env.P3_API_BASE_URL ?? "http://127.0.0.1:18000");
  await page.goto("/");
  await expect(page.getByTestId("create-intake")).toBeEnabled();
  await page.getByTestId("create-intake").click();
  await expect(page.getByTestId("api-message")).toContainText("intake 완료");
  await page.getByTestId("document-upload").setInputFiles({
    name: "calcium-chloride-bead-synthetic.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("P3 SYNTHETIC CALCIUM CHLORIDE BEAD COA"),
  });
  await expect(page.getByTestId("api-message")).toContainText("document 완료");
  await page.getByTestId("extract-document").click();
  await expect(page.getByTestId("api-message")).toContainText("extraction 완료");
  await page.getByTestId("confirm-review").click();
  await expect(page.getByTestId("api-message")).toContainText("review/match 완료");
  await page.getByTestId("create-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("INTERNAL_TEST_PENDING");
}

test("intake through LEAD approval and PostgreSQL LOT trace", async ({ page }) => {
  await reachInspection(page);
  await page.getByTestId("internal-result").click();
  await expect(page.getByTestId("server-status")).toHaveText("READY_FOR_REVIEW");
  await page.getByTestId("submit-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("LEAD_REVIEW");
  await page.getByRole("button", { name: "팀장 검토" }).first().click();
  await page.getByTestId("role-LEAD").click();
  await expect(page.getByTestId("api-message")).toContainText("role LEAD 완료");
  await page.getByTestId("approve-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("ACCEPTED");
  await expect(page.getByTestId("workflow-status-badge")).toHaveText("승인 완료 · ACCEPTED");
  await expect(page.getByTestId("workflow-status-live")).toContainText("승인 완료 · ACCEPTED");
  await expect(page.getByTestId("workflow-status-live")).not.toContainText("검토 필요");
  await page.getByTestId("load-trace").click();
  await expect(page.getByTestId("trace-summary")).toContainText("documents 1");
  await expect(page.getByTestId("trace-summary")).toContainText("inspections 1");
  await expect(page.getByTestId("workflow-status-badge")).toHaveText("승인 완료 · ACCEPTED");
  await expect(page.getByTestId("workflow-status-badge")).not.toContainText("검토 필요");
  await expect(page.getByTestId("workflow-status-live")).toContainText("승인 완료 · ACCEPTED");
  await expect(page.getByTestId("workflow-status-live")).toHaveAttribute("aria-live", "polite");
  await page.setViewportSize({ width: 375, height: 812 });
  await expect(page.getByTestId("workflow-status-badge")).toBeVisible();
  await expect(page.getByTestId("load-trace")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await page.getByTestId("create-revision").click();
  await expect(page.getByText(/round 1 \/ revision 2/)).toBeVisible();
  await page.getByTestId("create-retest").click();
  await expect(page.getByText(/round 2 \/ revision 1/)).toBeVisible();
});
