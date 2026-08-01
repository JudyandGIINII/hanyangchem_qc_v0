import os from "node:os";
import path from "node:path";

import { defineConfig } from "@playwright/test";

const artifacts = path.join(os.tmpdir(), `hyc-p3-playwright-${process.pid}`);

export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  reporter: [["line"]],
  outputDir: artifacts,
  use: {
    baseURL: process.env.P3_WEB_BASE_URL ?? "http://127.0.0.1:13000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
