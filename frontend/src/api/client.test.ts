import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, resetAuthRedirectHandler, setAuthRedirectHandler } from "./client";

const fetchMock = vi.fn();

function apiResponse(status: number, detail: string) {
  return new Response(JSON.stringify({ detail }), {
    status,
    statusText: "Unauthorized",
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  sessionStorage.clear();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  resetAuthRedirectHandler();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("api unauthorized handling", () => {
  it("honors skipAuthRedirect", async () => {
    const redirectSpy = vi.fn();
    setAuthRedirectHandler(redirectSpy);
    sessionStorage.setItem("tomorrowland_token", "existing");
    fetchMock.mockResolvedValueOnce(apiResponse(401, "Rejected"));

    await expect(
      api.post("/auth/login", {}, { skipAuthRedirect: true }),
    ).rejects.toMatchObject({ status: 401, message: "Rejected" });

    expect(redirectSpy).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("tomorrowland_token")).toBe("existing");
  });

  it("uses the global expired-session path by default", async () => {
    const redirectSpy = vi.fn();
    setAuthRedirectHandler(redirectSpy);
    sessionStorage.setItem("tomorrowland_token", "stale");
    fetchMock.mockResolvedValueOnce(apiResponse(401, "Rejected"));

    await expect(api.get("/auth/me")).rejects.toMatchObject({
      status: 401,
      message: "Session expired",
    });

    expect(sessionStorage.getItem("tomorrowland_token")).toBeNull();
    expect(redirectSpy).toHaveBeenCalledTimes(1);
    expect(redirectSpy.mock.calls[0]?.[0]).toContain("/login?expired=1");
  });
});
