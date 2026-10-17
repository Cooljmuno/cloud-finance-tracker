import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import { AuthProvider } from "./auth/AuthProvider";

const user = {
  id: "user-1",
  username: "portfolio-demo",
  email: "demo@local.invalid",
};

const account = {
  id: "account-1",
  name: "Everyday Checking",
  account_type: "checking",
  institution: "Northstar Community Bank",
  currency: "USD",
  opening_balance: "2840.00",
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const category = {
  id: "category-1",
  name: "Groceries",
  kind: "expense",
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const transaction = {
  id: "transaction-1",
  account: account.id,
  account_name: account.name,
  currency: "USD",
  category: category.id,
  category_name: category.name,
  transaction_date: "2026-08-29",
  description: "Juniper Market",
  amount: "-86.24",
  status: "posted",
  notes: "Synthetic portfolio demonstration data.",
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function paginated(results: unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

function authenticatedHandler(overrides?: (url: URL, init?: RequestInit) => Response | undefined) {
  return vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const url = new URL(String(input));
    const overridden = overrides?.(url, init);
    if (overridden) return overridden;
    if (url.pathname.endsWith("/auth/me/")) return jsonResponse(user);
    if (url.pathname.endsWith("/auth/csrf/")) return jsonResponse({ csrfToken: "test-csrf" });
    if (url.pathname.endsWith("/accounts/")) return jsonResponse(paginated([account]));
    if (url.pathname.endsWith("/categories/")) return jsonResponse(paginated([category]));
    if (url.pathname.endsWith("/transactions/")) return jsonResponse(paginated([transaction]));
    throw new Error(`Unhandled request: ${url}`);
  });
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Cloud Finance Tracker", () => {
  it("shows local sign-in when there is no session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "Unauthenticated" }, 401)));

    renderApp();

    expect(await screen.findByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
    expect(screen.getByText("Local session + CSRF")).toBeInTheDocument();
  });

  it("loads the authenticated synthetic transaction ledger", async () => {
    vi.stubGlobal("fetch", authenticatedHandler());

    renderApp();

    expect(await screen.findByRole("heading", { name: "Transaction ledger" })).toBeInTheDocument();
    expect(await screen.findByText("Juniper Market")).toBeInTheDocument();
    expect(screen.getByText("-$86.24")).toBeInTheDocument();
    expect(screen.getByText("Synthetic demo data")).toBeInTheDocument();
  });

  it("signs in through CSRF-protected session endpoints", async () => {
    let authenticated = false;
    const fetchMock = authenticatedHandler((url, init) => {
      if (url.pathname.endsWith("/auth/me/") && !authenticated) {
        return jsonResponse({ detail: "Unauthenticated" }, 401);
      }
      if (url.pathname.endsWith("/auth/login/") && init?.method === "POST") {
        authenticated = true;
        return jsonResponse(user);
      }
      return undefined;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "portfolio-demo" },
    });
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "not-logged-or-committed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByRole("heading", { name: "Transaction ledger" })).toBeInTheDocument();
    const loginCall = fetchMock.mock.calls.find(([input]) => String(input).includes("/auth/login/"));
    expect(loginCall?.[1]).toMatchObject({ method: "POST", credentials: "include" });
    expect(new Headers(loginCall?.[1]?.headers).get("X-CSRFToken")).toBe("test-csrf");
  });

  it("applies account and status filters on the server", async () => {
    const fetchMock = authenticatedHandler();
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await screen.findByRole("heading", { name: "Transaction ledger" });
    await screen.findByRole("option", { name: "Everyday Checking" });

    fireEvent.change(screen.getByLabelText("Account"), { target: { value: account.id } });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "posted" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply filters" }));

    await waitFor(() => {
      const filteredCall = fetchMock.mock.calls.find(([input]) => {
        const url = new URL(String(input));
        return url.pathname.endsWith("/transactions/") && url.searchParams.has("account");
      });
      expect(filteredCall).toBeDefined();
      const url = new URL(String(filteredCall?.[0]));
      expect(url.searchParams.get("account")).toBe(account.id);
      expect(url.searchParams.get("status")).toBe("posted");
    });
  });

  it("creates a signed-decimal transaction and refreshes the ledger", async () => {
    let submittedBody: Record<string, unknown> | null = null;
    const fetchMock = authenticatedHandler((url, init) => {
      if (url.pathname.endsWith("/transactions/") && init?.method === "POST") {
        submittedBody = JSON.parse(String(init.body)) as Record<string, unknown>;
        return jsonResponse({ ...transaction, id: "transaction-2", description: "Metro Fuel" }, 201);
      }
      return undefined;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    await screen.findByRole("heading", { name: "Transaction ledger" });

    const addButton = screen.getByRole("button", { name: /add transaction/i });
    await waitFor(() => expect(addButton).toBeEnabled());
    fireEvent.click(addButton);
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Metro Fuel" } });
    fireEvent.change(screen.getByLabelText(/^Amount/), { target: { value: "-42.18" } });
    fireEvent.click(screen.getByRole("button", { name: "Save transaction" }));

    expect(await screen.findByText("Transaction created successfully.")).toBeInTheDocument();
    expect(submittedBody).toMatchObject({
      account: account.id,
      category: null,
      description: "Metro Fuel",
      amount: "-42.18",
      status: "posted",
    });
  });
});
