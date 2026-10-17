import { createContext, useContext } from "react";

import type { AuthTransport } from "../api/client";
import type { CurrentUser } from "../api/types";
import type { AuthMode } from "../config";

export type AuthState = "loading" | "anonymous" | "authenticated" | "error";

export type AuthContextValue = {
  state: AuthState;
  mode: AuthMode;
  user: CurrentUser | null;
  transport: AuthTransport | null;
  error: string | null;
  signIn: (credentials?: { username: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
  retry: () => void;
  invalidate: () => Promise<void>;
};

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAppAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAppAuth must be used inside AuthProvider.");
  }
  return value;
}
