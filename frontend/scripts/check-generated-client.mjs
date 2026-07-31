import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const frontendDirectory = fileURLToPath(new URL("../", import.meta.url));
const openapiTypescript = fileURLToPath(new URL("../node_modules/.bin/openapi-typescript", import.meta.url));
const temporaryDirectory = await mkdtemp(join(tmpdir(), "hyc-openapi-"));
const generated = join(temporaryDirectory, "generated.ts");
let exitCode = 0;

try {
  const run = spawnSync(openapiTypescript, ["../contracts/openapi.json", "-o", generated], {
    cwd: frontendDirectory,
    stdio: "inherit"
  });
  if (run.error) {
    console.error(`unable to run project-local openapi-typescript: ${run.error.message}`);
    exitCode = 1;
  } else if (run.status !== 0) {
    exitCode = run.status ?? 1;
  } else {
    const [actual, expected] = await Promise.all([
      readFile(generated),
      readFile(join(frontendDirectory, "src/lib/api/generated.ts"))
    ]);
    if (!actual.equals(expected)) {
      console.error("generated TypeScript client is stale; run pnpm generate:client");
      exitCode = 1;
    }
  }
} finally {
  await rm(temporaryDirectory, { recursive: true, force: true });
}

if (exitCode !== 0) process.exit(exitCode);
