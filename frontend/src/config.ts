export type AuthMode = "session" | "cognito";

const rawAuthMode = import.meta.env.VITE_AUTH_MODE ?? "session";

if (rawAuthMode !== "session" && rawAuthMode !== "cognito") {
  throw new Error("VITE_AUTH_MODE must be either session or cognito.");
}

export const appConfig = {
  apiBaseUrl: (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/v1").replace(
    /\/$/,
    "",
  ),
  authMode: rawAuthMode as AuthMode,
};

export type CognitoConfig = {
  issuer: string;
  clientId: string;
  domain: string;
  redirectUri: string;
  logoutUri: string;
};

export function getCognitoConfig(): CognitoConfig {
  const config = {
    issuer: import.meta.env.VITE_COGNITO_ISSUER,
    clientId: import.meta.env.VITE_COGNITO_CLIENT_ID,
    domain: import.meta.env.VITE_COGNITO_DOMAIN,
    redirectUri: import.meta.env.VITE_COGNITO_REDIRECT_URI,
    logoutUri: import.meta.env.VITE_COGNITO_LOGOUT_URI,
  };
  const missing = Object.entries(config)
    .filter(([, value]) => !value)
    .map(([key]) => key);

  if (missing.length > 0) {
    throw new Error(`Cognito mode is missing configuration: ${missing.join(", ")}.`);
  }

  return {
    ...config,
    domain: config.domain.replace(/\/$/, ""),
  } as CognitoConfig;
}
