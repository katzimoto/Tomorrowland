import { api } from "./client";

export interface CurrentUser {
  user_id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
  groups: string[];
}

interface LoginResponse {
  access_token: string;
  token_type: string;
}

// The access token now lives in an HttpOnly cookie that JS cannot read. The
// server pairs it with a readable CSRF cookie, whose presence we use as the
// synchronous "is logged in" signal for route guards. Both cookies are shared
// across tabs, so opening a document in a new tab keeps the session.
const CSRF_COOKIE = "tomorrowland_csrf";

export const authStorage = {
  clearToken() {
    document.cookie = `${CSRF_COOKIE}=; Max-Age=0; path=/`;
  },
  hasToken(): boolean {
    return new RegExp(`(?:^|; )${CSRF_COOKIE}=`).test(document.cookie);
  },
};

export async function login(email: string, password: string): Promise<void> {
  await api.post<LoginResponse>("/auth/login", { email, password }, { skipAuthRedirect: true });
}

export async function signUp(
  email: string,
  password: string,
  displayName?: string,
): Promise<void> {
  await api.post<LoginResponse>(
    "/auth/signup",
    { email, password, display_name: displayName },
    { skipAuthRedirect: true },
  );
}

export async function logout(): Promise<void> {
  try {
    await api.post<void>("/auth/logout", {});
  } finally {
    authStorage.clearToken();
  }
}

export function getCurrentUser(): Promise<CurrentUser> {
  return api.get<CurrentUser>("/auth/me");
}
