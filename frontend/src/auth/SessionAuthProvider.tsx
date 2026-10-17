import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, type AuthTransport } from "../api/client";
import { getCurrentUser, loginWithSession, logoutSession } from "../api/auth";
import type { CurrentUser } from "../api/types";
import { AuthContext, type AuthState } from "./AuthContext";

const transport: AuthTransport = { mode: "session" };

export function SessionAuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>("loading");
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setState("loading");
    setError(null);

    getCurrentUser(transport, controller.signal)
      .then((currentUser) => {
        setUser(currentUser);
        setState("authenticated");
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          setUser(null);
          setState("anonymous");
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Unable to reach the API.");
        setState("error");
      });

    return () => controller.abort();
  }, [attempt]);

  const signIn = useCallback(async (credentials?: { username: string; password: string }) => {
    if (!credentials) {
      throw new Error("Username and password are required for local sign-in.");
    }
    const currentUser = await loginWithSession(credentials.username, credentials.password);
    setUser(currentUser);
    setError(null);
    setState("authenticated");
  }, []);

  const invalidate = useCallback(async () => {
    setUser(null);
    setState("anonymous");
  }, []);

  const signOut = useCallback(async () => {
    await logoutSession();
    await invalidate();
  }, [invalidate]);

  const value = useMemo(
    () => ({
      state,
      mode: "session" as const,
      user,
      transport: state === "authenticated" ? transport : null,
      error,
      signIn,
      signOut,
      retry: () => setAttempt((current) => current + 1),
      invalidate,
    }),
    [error, invalidate, signIn, signOut, state, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
