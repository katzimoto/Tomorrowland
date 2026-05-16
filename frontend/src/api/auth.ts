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

export const authStorage = {
  setToken(token: string) {
    sessionStorage.setItem("tomorrowland_token", token);
  },
  clearToken() {
    sessionStorage.removeItem("tomorrowland_token");
  },
  hasToken(): boolean {
    return !!sessionStorage.getItem("tomorrowland_token");
  },
};

export async function login(email: string, password: string): Promise<void> {
  const res = await api.post<LoginResponse>(
    "/auth/login",
    { email, password },
    { skipAuthRedirect: true },
  );
  authStorage.setToken(res.access_token);
}

export async function signUp(
  email: string,
  password: string,
  displayName?: string,
): Promise<void> {
  const res = await api.post<LoginResponse>(
    "/auth/signup",
    { email, password, display_name: displayName },
    { skipAuthRedirect: true },
  );
  authStorage.setToken(res.access_token);
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
