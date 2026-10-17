import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAppAuth } from "./AuthContext";
import { CognitoAuthProvider } from "./CognitoAuthProvider";

const mocks = vi.hoisted(() => ({
  providerProps: {} as Record<string, unknown>,
  oidc: {
    isLoading: false,
    isAuthenticated: false,
    user: null as { access_token: string; id_token?: string } | null,
    error: null as Error | null,
    signinRedirect: vi.fn(async () => undefined),
    removeUser: vi.fn(async () => undefined),
  },
}));

vi.mock("react-oidc-context", () => ({
  AuthProvider: ({ children, ...props }: { children: ReactNode }) => {
    mocks.providerProps = props;
    return children;
  },
  useAuth: () => mocks.oidc,
}));

vi.mock("../config", () => ({
  appConfig: {
    apiBaseUrl: "http://localhost:8000/api/v1",
    authMode: "cognito",
  },
  getCognitoConfig: () => ({
    issuer: "https://cognito-idp.us-east-1.amazonaws.com/us-east-1_example",
    clientId: "public-client-id",
    domain: "https://portfolio.auth.us-east-1.amazoncognito.com",
    redirectUri: "https://app.example.com",
    logoutUri: "https://app.example.com",
  }),
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function Probe() {
  const auth = useAppAuth();
  return (
    <div>
      <span>{auth.state}</span>
      <span>{auth.user?.username}</span>
      <button type="button" onClick={() => void auth.signIn()}>
        Start sign-in
      </button>
    </div>
  );
}

beforeEach(() => {
  mocks.providerProps = {};
  mocks.oidc.isLoading = false;
  mocks.oidc.isAuthenticated = false;
  mocks.oidc.user = null;
  mocks.oidc.error = null;
  mocks.oidc.signinRedirect.mockClear();
  mocks.oidc.removeUser.mockClear();
  vi.unstubAllGlobals();
});

describe("Cognito authentication provider", () => {
  it("uses OAuth code flow and starts a PKCE-capable redirect", async () => {
    render(
      <CognitoAuthProvider>
        <Probe />
      </CognitoAuthProvider>,
    );

    expect(screen.getByText("anonymous")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start sign-in" }));

    await waitFor(() => expect(mocks.oidc.signinRedirect).toHaveBeenCalledOnce());
    expect(mocks.providerProps.response_type).toBe("code");
    expect(mocks.providerProps.scope).toBe("openid email profile");
    expect(mocks.providerProps.client_id).toBe("public-client-id");
  });

  it("verifies the session with the access token instead of the ID token", async () => {
    mocks.oidc.isAuthenticated = true;
    mocks.oidc.user = { access_token: "cognito-access-token", id_token: "do-not-send-this" };
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        id: "local-user-id",
        username: "cognito-user",
        email: "verified@example.com",
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(
      <CognitoAuthProvider>
        <Probe />
      </CognitoAuthProvider>,
    );

    expect(await screen.findByText("cognito-user")).toBeInTheDocument();
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).get("Authorization")).toBe(
      "Bearer cognito-access-token",
    );
    expect(new Headers(request.headers).get("Authorization")).not.toContain("do-not-send-this");
    expect(request.credentials).toBe("omit");
  });

  it("removes a Cognito session rejected by the API", async () => {
    mocks.oidc.isAuthenticated = true;
    mocks.oidc.user = { access_token: "expired-access-token" };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Invalid" }, 401)));

    render(
      <CognitoAuthProvider>
        <Probe />
      </CognitoAuthProvider>,
    );

    await waitFor(() => expect(mocks.oidc.removeUser).toHaveBeenCalledOnce());
  });
});
