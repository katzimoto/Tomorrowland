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

const CSRF_COOKIE = "tomorrowland_csrf";
const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

function readCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

/** The double-submit CSRF token for hand-rolled fetches (e.g. streaming). */
export function csrfToken(): string | null {
  return readCookie(CSRF_COOKIE);
}

function clearCsrfCookie() {
  document.cookie = `${CSRF_COOKIE}=; Max-Age=0; path=/`;
}

function redirectToExpiredLogin() {
  const url = new URL("/login", window.location.href);
  url.searchParams.set("expired", "1");
  authRedirectHandler(url.toString());
}

function buildHeaders(requestInit: ApiRequestInit): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(requestInit.headers as Record<string, string>),
  };
  // Auth travels via the HttpOnly cookie sent automatically with credentials.
  // Unsafe methods carry the double-submit CSRF token read from its cookie.
  const method = (requestInit.method ?? "GET").toUpperCase();
  if (!SAFE_METHODS.has(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  return headers;
}

async function requestText(path: string, init: ApiRequestInit = {}): Promise<string> {
  const { skipAuthRedirect = false, ...requestInit } = init;
  const headers = buildHeaders(requestInit);
  delete headers["Content-Type"];
  const res = await fetch(`${BASE}${path}`, {
    ...requestInit,
    headers,
    credentials: "same-origin",
  });
  if (res.status === 401 && !skipAuthRedirect) {
    clearCsrfCookie();
    redirectToExpiredLogin();
    throw new ApiError(401, "Session expired");
  }
  if (!res.ok) {
    throw new ApiError(res.status, res.statusText);
  }
  return res.text();
}

async function request<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const { skipAuthRedirect = false, ...requestInit } = init;
  const headers = buildHeaders(requestInit);

  const res = await fetch(`${BASE}${path}`, {
    ...requestInit,
    headers,
    credentials: "same-origin",
  });

  if (res.status === 401 && !skipAuthRedirect) {
    // Clear the stale CSRF cookie so the route guard redirects, then redirect.
    clearCsrfCookie();
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
  getText: (path: string, init?: ApiRequestInit) => requestText(path, init),
  post: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "PATCH", body: JSON.stringify(body) }),
  put: <T>(path: string, body: unknown, init: ApiRequestInit = {}) =>
    request<T>(path, { ...init, method: "PUT", body: JSON.stringify(body) }),
  delete: <T>(path: string, init?: ApiRequestInit) =>
    request<T>(path, { ...init, method: "DELETE" }),
};
