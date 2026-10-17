import { useAuth, AuthProvider as OidcAuthProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

import { getCurrentUser } from "../api/auth";
import { ApiError, type AuthTransport } from "../api/client";
import type { CurrentUser } from "../api/types";
import { getCognitoConfig, type CognitoConfig } from "../config";
import { AuthContext, type AuthState } from "./AuthContext";

function CognitoBridge({ children, config }: { children: ReactNode; config: CognitoConfig }) {
  const oidc = useAuth();
  const [apiUser, setApiUser] = useState<CurrentUser | null>(null);
  const [apiError, setApiError] = useState<string | null>(null);

  const accessToken = oidc.user?.access_token ?? null;
  const transport = useMemo<AuthTransport | null>(
    () => (accessToken ? { mode: "cognito", accessToken } : null),
    [accessToken],
  );

  useEffect(() => {
    if (!oidc.isAuthenticated || !transport) {
      setApiUser(null);
      return;
    }

    const controller = new AbortController();
    setApiError(null);
    getCurrentUser(transport, controller.signal)
      .then(setApiUser)
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof ApiError && error.status === 401) {
          void oidc.removeUser();
          return;
        }
        setApiError(error instanceof Error ? error.message : "Unable to verify Cognito session.");
      });
    return () => controller.abort();
  }, [oidc.isAuthenticated, transport]);

  const invalidate = useCallback(async () => {
    setApiUser(null);
    await oidc.removeUser();
  }, [oidc]);

  const signIn = useCallback(async () => {
    await oidc.signinRedirect();
  }, [oidc]);

  const signOut = useCallback(async () => {
    await oidc.removeUser();
    const query = new URLSearchParams({
      client_id: config.clientId,
      logout_uri: config.logoutUri,
    });
    window.location.assign(`${config.domain}/logout?${query.toString()}`);
  }, [config, oidc]);

  let state: AuthState;
  if (oidc.isLoading || (oidc.isAuthenticated && !apiUser && !apiError)) {
    state = "loading";
  } else if (oidc.error || apiError) {
    state = "error";
  } else if (oidc.isAuthenticated && apiUser && transport) {
    state = "authenticated";
  } else {
    state = "anonymous";
  }

  const value = useMemo(
    () => ({
      state,
      mode: "cognito" as const,
      user: apiUser,
      transport: state === "authenticated" ? transport : null,
      error: oidc.error?.message ?? apiError,
      signIn,
      signOut,
      retry: () => window.location.reload(),
      invalidate,
    }),
    [apiError, apiUser, invalidate, oidc.error?.message, signIn, signOut, state, transport],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function CognitoAuthProvider({ children }: { children: ReactNode }) {
  const result = useMemo(() => {
    try {
      return { config: getCognitoConfig(), error: null };
    } catch (error: unknown) {
      return {
        config: null,
        error: error instanceof Error ? error.message : "Invalid Cognito configuration.",
      };
    }
  }, []);

  if (!result.config) {
    const value = {
      state: "error" as const,
      mode: "cognito" as const,
      user: null,
      transport: null,
      error: result.error,
      signIn: async () => undefined,
      signOut: async () => undefined,
      retry: () => window.location.reload(),
      invalidate: async () => undefined,
    };
    return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
  }

  const oidcConfig = {
    authority: result.config.issuer,
    client_id: result.config.clientId,
    redirect_uri: result.config.redirectUri,
    response_type: "code",
    scope: "openid email profile",
    automaticSilentRenew: true,
    monitorSession: false,
    userStore: new WebStorageStateStore({ store: window.sessionStorage }),
    onSigninCallback: () => {
      window.history.replaceState({}, document.title, window.location.pathname);
    },
  };

  return (
    <OidcAuthProvider {...oidcConfig}>
      <CognitoBridge config={result.config}>{children}</CognitoBridge>
    </OidcAuthProvider>
  );
}
