import { expect, test } from "@playwright/test";

test("server hold blocks submit until persisted internal result clears it", async ({ page }) => {
  await page.addInitScript((base) => window.localStorage.setItem("P3_API_BASE", base), process.env.P3_API_BASE_URL ?? "http://127.0.0.1:18000");
  await page.goto("/");
  await expect(page.getByTestId("create-intake")).toBeEnabled();
  await page.getByTestId("create-intake").click();
  await page.getByTestId("document-upload").setInputFiles({ name: "hold-synthetic.txt", mimeType: "text/plain", buffer: Buffer.from("P3 SYNTHETIC HOLD COA") });
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
  await expect(page.getByTestId("server-status")).toHaveText("INTERNAL_TEST_PENDING");
  await page.getByTestId("submit-held-probe").click();
  await expect(page.getByTestId("api-message")).toContainText("API 422");
  await page.getByTestId("internal-result").click();
  await expect(page.getByTestId("server-status")).toHaveText("READY_FOR_REVIEW");
  await page.getByTestId("submit-inspection").click();
  await expect(page.getByTestId("server-status")).toHaveText("LEAD_REVIEW");
});
