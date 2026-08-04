import { expect, test } from "@playwright/test";

test("INSPECTOR and ADMIN receive 403 while LEAD succeeds", async ({ page }) => {
  await page.addInitScript((base) => window.localStorage.setItem("P3_API_BASE", base), process.env.P3_API_BASE_URL ?? "http://127.0.0.1:18000");
  await page.goto("/");
  await expect(page.getByTestId("create-intake")).toBeEnabled();
  await page.getByTestId("create-intake").click();
  await page.getByTestId("document-upload").setInputFiles({ name: "rbac-synthetic.txt", mimeType: "text/plain", buffer: Buffer.from("P3 SYNTHETIC RBAC COA") });
  await expect(page.getByTestId("extract-document")).toBeEnabled();
  await page.getByTestId("extract-document").click();
  await page.getByRole("button", { name: "문서 검토" }).first().click();
  const reviewReasons = page.getByPlaceholder("명시적 검토 사유");
  await expect(reviewReasons.first()).toBeVisible();
  const reviewReasonCount = await reviewReasons.count();
  expect(reviewReasonCount).toBeGreaterThan(0);
  await expect(page.getByTestId("confirm-review")).toBeDisabled();
  await expect(page.getByTestId("create-inspection")).toBeDisabled();
  for (let index = 0; index < reviewReasonCount; index += 1) {
    await reviewReasons.nth(index).fill("합성 fixture 추출값을 명시적으로 검토함");
  }
  await expect(page.getByTestId("confirm-review")).toBeEnabled();
  await page.getByTestId("confirm-review").click();
  await expect(page.getByTestId("create-inspection")).toBeEnabled();
  await page.getByTestId("create-inspection").click();
  await page.getByTestId("internal-result").click();
  await page.getByTestId("submit-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("LEAD_REVIEW");

  await page.getByTestId("approve-inspection").click();
  await expect(page.getByTestId("api-message")).toContainText("API 403");
  await page.getByRole("button", { name: "팀장 검토" }).first().click();
  await page.getByTestId("role-ADMIN").click();
  await expect(page.getByTestId("api-message")).toContainText("role ADMIN 완료");
  await page.getByTestId("approve-inspection").click();
  await expect(page.getByTestId("api-message")).toContainText("API 403");
  await page.getByTestId("role-LEAD").click();
  await expect(page.getByTestId("api-message")).toContainText("role LEAD 완료");
  await page.getByTestId("approve-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("ACCEPTED");
});
