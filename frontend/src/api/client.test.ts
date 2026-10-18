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
    expect(new Headers(init.headers).get("Content-Type")).toBe("application/json");
  });

  it("leaves the multipart boundary to the browser while preserving session CSRF protection", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ csrfToken: "upload-csrf-token" }))
      .mockResolvedValueOnce(jsonResponse({ can_commit: true }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    const file = new File(["transaction_date,description,amount\n"], "statement.csv", {
      type: "text/csv",
    });
    form.append("account", "account-1");
    form.append("file", file);

    await requestJson("imports/preview/", { method: "POST", body: form }, { mode: "session" });

    const init = fetchMock.mock.calls[1][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.body).toBe(form);
    expect((init.body as FormData).get("file")).toBe(file);
    expect(init.credentials).toBe("include");
    expect(headers.get("X-CSRFToken")).toBe("upload-csrf-token");
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.get("Accept")).toBe("application/json");
  });

  it("sends multipart uploads with Cognito authentication and no cookies", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ can_commit: true }));
    vi.stubGlobal("fetch", fetchMock);
    const form = new FormData();
    form.append("account", "account-1");
    form.append("file", new File(["transaction_date,description,amount\n"], "statement.csv"));

    await requestJson(
      "imports/preview/",
      { method: "POST", body: form },
      { mode: "cognito", accessToken: "upload-access-token" },
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.body).toBe(form);
    expect(init.credentials).toBe("omit");
    expect(headers.get("Authorization")).toBe("Bearer upload-access-token");
    expect(headers.has("Content-Type")).toBe(false);
    expect(headers.has("X-CSRFToken")).toBe(false);
  });

  it("refuses to forward authentication to another origin", async () => {
    vi.stubGlobal("fetch", vi.fn());

    await expect(
      requestJson(
        "https://attacker.invalid/api/v1/transactions/",
        {},
        {
          mode: "cognito",
          accessToken: "secret",
        },
      ),
    ).rejects.toThrow("outside the configured API");
    expect(fetch).not.toHaveBeenCalled();
  });
});
