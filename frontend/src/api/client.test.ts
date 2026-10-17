import { afterEach, describe, expect, it, vi } from "vitest";

import { requestJson } from "./client";

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  document.cookie = "csrftoken=; Max-Age=0; path=/";
});

describe("API authentication transport", () => {
  it("sends a Cognito access token without browser credentials", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ ok: true }));
    vi.stubGlobal("fetch", fetchMock);

    await requestJson("transactions/", {}, { mode: "cognito", accessToken: "access-token" });

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe("omit");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer access-token");
  });

  it("bootstraps CSRF and includes cookies for unsafe session requests", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: "fresh-csrf-token" }))
      .mockResolvedValueOnce(jsonResponse({ id: "transaction-1" }));
    vi.stubGlobal("fetch", fetchMock);

    await requestJson(
      "transactions/",
      { method: "POST", body: JSON.stringify({ amount: "-10.25" }) },
      { mode: "session" },
    );

    const init = fetchMock.mock.calls[1][1] as RequestInit;
    expect(init.credentials).toBe("include");
    expect(new Headers(init.headers).get("X-CSRFToken")).toBe("fresh-csrf-token");
  });

  it("refuses to forward authentication to another origin", async () => {
    vi.stubGlobal("fetch", vi.fn());

    await expect(
      requestJson("https://attacker.invalid/api/v1/transactions/", {}, {
        mode: "cognito",
        accessToken: "secret",
      }),
    ).rejects.toThrow("outside the configured API");
    expect(fetch).not.toHaveBeenCalled();
  });
});
