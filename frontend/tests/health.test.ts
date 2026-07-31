import { describe, expect, it } from "vitest";

import { GET } from "../src/app/api/health/route";

describe("web health", () => {
  it("returns a ready status", async () => {
    expect(await (await GET()).json()).toEqual({ status: "ready" });
  });
});
