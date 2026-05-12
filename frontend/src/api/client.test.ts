import { describe, expect, it } from "vitest";
import { api } from "./client";

describe("api", () => {
  it("exposes request helpers", () => {
    expect(api.get).toBeTypeOf("function");
    expect(api.post).toBeTypeOf("function");
  });
});
