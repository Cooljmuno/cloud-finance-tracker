import type { AuthTransport } from "./client";
import { requestJson } from "./client";
import type { CurrentUser } from "./types";

const sessionTransport: AuthTransport = { mode: "session" };

export function getCurrentUser(transport: AuthTransport, signal?: AbortSignal) {
  return requestJson<CurrentUser>("auth/me/", { signal }, transport);
}

export function loginWithSession(username: string, password: string) {
  return requestJson<CurrentUser>(
    "auth/login/",
    {
      method: "POST",
      body: JSON.stringify({ username, password }),
    },
    sessionTransport,
  );
}

export function logoutSession() {
  return requestJson<void>("auth/logout/", { method: "POST" }, sessionTransport);
}
