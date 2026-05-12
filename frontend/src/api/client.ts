const BASE = "/api";

export interface ApiRequestInit extends RequestInit {
  skipAuthRedirect?: boolean;
}

type AuthRedirectHandler = (url: string) => void;

function defaultAuthRedirectHandler(url: string) {
  window.location.href = url;
}

let authRedirectHandler: AuthRedirectHandler = defaultAuthRedirectHandler;

export function setAuthRedirectHandler(handler: AuthRedirectHandler) {
  authRedirectHandler = handler;
}

export function resetAuthRedirectHandler() {
  authRedirectHandler = defaultAuthRedirectHandler;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function getToken(): string | null {
  return sessionStorage.getItem("tomorrowland_token");
}

function redirectToExpiredLogin() {
  const url = new URL("/login", window.location.href);
  url.searchParams.set("expired", "1");
  authRedirectHandler(url.toString());
}

async function request<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const { skipAuthRedirect = false, ...requestInit } = init;
  const token = getToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(requestInit.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, { ...requestInit, headers });

  if (res.status === 401 && !skipAuthRedirect) {
    // Clear stale token and redirect to login
    sessionStorage.removeItem("tomorrowland_token");
    redirectToExpiredLogin();
    throw new ApiError(401, "Session expired");
  }

  if (!res.ok) {
    let message = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // ignore parse failures
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, init?: ApiRequestInit) => request<T>(path, init),
  post: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "DELETE" }),
};
