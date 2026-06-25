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

function clearAllCookies() {
  for (const cookie of document.cookie.split(";")) {
    const name = cookie.split("=")[0]?.trim();
    if (name) document.cookie = `${name}=; Max-Age=0; path=/`;
  }
}

beforeEach(() => {
  clearAllCookies();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  resetAuthRedirectHandler();
  vi.unstubAllGlobals();
  clearAllCookies();
});

describe("api unauthorized handling", () => {
  it("honors skipAuthRedirect and leaves the CSRF cookie intact", async () => {
    const redirectSpy = vi.fn();
    setAuthRedirectHandler(redirectSpy);
    document.cookie = "tomorrowland_csrf=existing; path=/";
    fetchMock.mockResolvedValueOnce(apiResponse(401, "Rejected"));

    await expect(
      api.post("/auth/login", {}, { skipAuthRedirect: true }),
    ).rejects.toMatchObject({ status: 401, message: "Rejected" });

    expect(redirectSpy).not.toHaveBeenCalled();
    expect(document.cookie).toContain("tomorrowland_csrf=existing");
  });

  it("clears the CSRF cookie and redirects on the default expired path", async () => {
    const redirectSpy = vi.fn();
    setAuthRedirectHandler(redirectSpy);
    document.cookie = "tomorrowland_csrf=stale; path=/";
    fetchMock.mockResolvedValueOnce(apiResponse(401, "Rejected"));

    await expect(api.get("/auth/me")).rejects.toMatchObject({
      status: 401,
      message: "Session expired",
    });

    expect(document.cookie).not.toContain("tomorrowland_csrf");
    expect(redirectSpy).toHaveBeenCalledTimes(1);
    expect(redirectSpy.mock.calls[0]?.[0]).toContain("/login?expired=1");
  });

  it("attaches the CSRF header and credentials on unsafe requests", async () => {
    document.cookie = "tomorrowland_csrf=tok123; path=/";
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api.post("/things", { a: 1 });

    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((requestInit.headers as Record<string, string>)["X-CSRF-Token"]).toBe("tok123");
    expect(requestInit.credentials).toBe("same-origin");
  });

  it("does not send a CSRF header on GET requests", async () => {
    document.cookie = "tomorrowland_csrf=tok123; path=/";
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );

    await api.get("/things");

    const [, requestInit] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((requestInit.headers as Record<string, string>)["X-CSRF-Token"]).toBeUndefined();
  });
});
