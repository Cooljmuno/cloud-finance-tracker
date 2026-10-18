import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { Category, FinanceTransaction, FinancialAccount } from "./api/types";
import { AuthProvider } from "./auth/AuthProvider";

const account: FinancialAccount = {
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

const category: Category = {
  id: "category-1",
  name: "Groceries",
  kind: "expense",
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const transaction: FinanceTransaction = {
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
  notes: "Synthetic purchase",
  created_at: "2026-08-29T00:00:00Z",
  updated_at: "2026-08-29T00:00:00Z",
};

type ApiState = {
  accounts: FinancialAccount[];
  categories: Category[];
  transactions: FinanceTransaction[];
};

type ApiRequest = {
  method: string;
  url: URL;
  body: Record<string, unknown>;
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function paginated(results: unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

function mockApi(
  initial: Partial<ApiState> = {},
  override?: (request: ApiRequest) => Response | undefined | Promise<Response | undefined>,
  options: { transactionPageSize?: number } = {},
) {
  const state: ApiState = {
    accounts: [{ ...account }],
    categories: [{ ...category }],
    transactions: [{ ...transaction }],
    ...initial,
  };
  const requests: ApiRequest[] = [];
  const fetchMock = vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
    const request = {
      method: init?.method ?? "GET",
      url: new URL(String(input)),
      body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {},
    };
    requests.push(request);
    const overridden = await override?.(request);
    if (overridden) return overridden;
    const { method, url, body } = request;
    if (url.pathname.endsWith("/auth/me/")) {
      return jsonResponse({ id: "user-1", username: "new-user", email: "demo@local.invalid" });
    }
    if (url.pathname.endsWith("/auth/csrf/")) {
      return jsonResponse({ csrfToken: "test-csrf" });
    }

    const match = url.pathname.match(/\/(accounts|categories|transactions)\/(?:([^/]+)\/)?$/);
    if (!match) throw new Error(`Unhandled request: ${method} ${url}`);
    const resource = match[1] as keyof ApiState;
    const id = match[2];
    if (method === "GET" && !id) {
      if (resource === "transactions") {
        const transactions = state.transactions.map((entry) => ({
          ...entry,
          account_name:
            state.accounts.find((item) => item.id === entry.account)?.name ?? entry.account_name,
          category_name: state.categories.find((item) => item.id === entry.category)?.name ?? null,
        }));
        const page = Number(url.searchParams.get("page") ?? "1");
        const pageSize = options.transactionPageSize ?? Math.max(1, transactions.length);
        const offset = (page - 1) * pageSize;
        if (page > 1 && offset >= transactions.length) {
          return jsonResponse({ detail: "Invalid page." }, 404);
        }
        const pageUrl = (nextPage: number) => {
          const result = new URL(url);
          result.searchParams.set("page", String(nextPage));
          return result.toString();
        };
        return jsonResponse({
          count: transactions.length,
          next: offset + pageSize < transactions.length ? pageUrl(page + 1) : null,
          previous: page > 1 ? pageUrl(page - 1) : null,
          results: transactions.slice(offset, offset + pageSize),
        });
      }
      return jsonResponse(paginated(state[resource]));
    }
    if (method === "POST" && !id) {
      if (resource === "accounts") {
        const created = {
          ...account,
          ...body,
          id: `account-${state.accounts.length + 1}`,
        } as FinancialAccount;
        state.accounts.push(created);
        return jsonResponse(created, 201);
      }
      if (resource === "categories") {
        const created = {
          ...category,
          ...body,
          id: `category-${state.categories.length + 1}`,
        } as Category;
        state.categories.push(created);
        return jsonResponse(created, 201);
      }
      const created = {
        ...transaction,
        ...body,
        id: `transaction-${state.transactions.length + 1}`,
      } as FinanceTransaction;
      state.transactions.push(created);
      return jsonResponse(created, 201);
    }
    if (method === "PATCH" && id) {
      const existing = state[resource].find((entry) => entry.id === id);
      if (!existing) return jsonResponse({ detail: "Not found." }, 404);
      Object.assign(existing, body);
      return jsonResponse(existing);
    }
    if (method === "DELETE" && id) {
      if (resource === "accounts")
        state.accounts = state.accounts.filter((entry) => entry.id !== id);
      if (resource === "categories")
        state.categories = state.categories.filter((entry) => entry.id !== id);
      if (resource === "transactions")
        state.transactions = state.transactions.filter((entry) => entry.id !== id);
      return new Response(null, { status: 204 });
    }
    throw new Error(`Unhandled request: ${method} ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  return {
    state,
    requests,
    mutations: () =>
      requests.filter((request) => ["POST", "PATCH", "DELETE"].includes(request.method)),
  };
}

function renderApp() {
  return render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

function changeField(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

afterEach(() => vi.unstubAllGlobals());

describe("Finance workspace workflows", () => {
  it("creates an account, category, and first transaction from an empty workspace", async () => {
    const api = mockApi({ accounts: [], categories: [], transactions: [] });
    renderApp();

    await screen.findByRole("heading", { name: "Set up your workspace" });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    const accountForm = await screen.findByRole("form", { name: "Add account" });
    fireEvent.click(within(accountForm).getByRole("button", { name: "Create account" }));
    expect(api.mutations()).toHaveLength(0);
    expect(screen.getByText("Enter an account name.")).toBeInTheDocument();
    expect(screen.getByLabelText(/^Account name/)).toHaveAttribute("aria-invalid", "true");

    changeField(/^Account name/, "Campus Checking");
    changeField(/^Institution/, "Student Credit Union");
    changeField(/^Opening balance/, "125.50");
    fireEvent.click(within(accountForm).getByRole("button", { name: "Create account" }));
    await screen.findByRole("button", { name: "Edit account Campus Checking" });
    expect(api.state.accounts[0]).toMatchObject({
      name: "Campus Checking",
      opening_balance: "125.50",
      is_active: true,
    });

    fireEvent.click(screen.getByRole("button", { name: "Categories" }));
    const addCategory = screen.queryByRole("button", { name: "Add category" });
    if (addCategory) fireEvent.click(addCategory);
    const categoryForm = await screen.findByRole("form", { name: "Add category" });
    fireEvent.click(within(categoryForm).getByRole("button", { name: "Create category" }));
    expect(
      api.mutations().filter((request) => request.url.pathname.endsWith("/categories/")),
    ).toHaveLength(0);
    expect(screen.getByText("Enter a category name.")).toBeInTheDocument();
    changeField(/^Category name/, "Meals");
    fireEvent.click(within(categoryForm).getByRole("button", { name: "Create category" }));
    await screen.findByRole("button", { name: "Edit category Meals" });

    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    fireEvent.click(screen.getByRole("button", { name: /add transaction/i }));
    const form = await screen.findByRole("region", { name: "Add transaction" });
    fireEvent.change(within(form).getByLabelText(/^Description/), {
      target: { value: "Campus lunch" },
    });
    fireEvent.change(within(form).getByLabelText(/^Amount/), { target: { value: "-12.35" } });
    fireEvent.change(within(form).getByLabelText(/^Category/), {
      target: { value: api.state.categories[0].id },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Save transaction" }));

    await screen.findByText("Campus lunch");
    expect(api.state.transactions).toHaveLength(1);
    expect(api.state.transactions[0]).toMatchObject({
      account: api.state.accounts[0].id,
      category: api.state.categories[0].id,
      amount: "-12.35",
    });
    expect(
      screen.queryByRole("heading", { name: "Set up your workspace" }),
    ).not.toBeInTheDocument();
  });

  it("retains a category edit after a validation error and refreshes related ledger labels after retry", async () => {
    let rejected = false;
    const api = mockApi({}, ({ method, url }) => {
      if (method === "PATCH" && url.pathname.endsWith(`/categories/${category.id}/`) && !rejected) {
        rejected = true;
        return jsonResponse({ name: ["A category with this name already exists."] }, 400);
      }
      return undefined;
    });
    renderApp();
    await screen.findByText("Juniper Market");
    fireEvent.click(screen.getByRole("button", { name: "Categories" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit category Groceries" }));
    changeField(/^Category name/, "Food");
    fireEvent.click(screen.getByRole("button", { name: "Save category" }));

    await screen.findByText("A category with this name already exists.");
    expect(screen.getByLabelText(/^Category name/)).toHaveValue("Food");
    expect(api.state.categories[0].name).toBe("Groceries");
    changeField(/^Category name/, "Meals");
    fireEvent.click(screen.getByRole("button", { name: "Save category" }));
    await screen.findByRole("button", { name: "Edit category Meals" });
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    const row = (await screen.findByText("Juniper Market")).closest("tr");
    expect(row).not.toBeNull();
    expect(within(row!).getByText("Meals")).toBeInTheDocument();
  });

  it("edits a transaction without replacing its archived account or category", async () => {
    const api = mockApi({
      accounts: [
        { ...account, is_active: false },
        { ...account, id: "account-2", name: "Current Savings" },
      ],
      categories: [
        { ...category, is_active: false },
        { ...category, id: "category-2", name: "Transport" },
      ],
    });
    renderApp();
    fireEvent.click(await screen.findByRole("button", { name: "Edit transaction Juniper Market" }));
    const form = await screen.findByRole("region", { name: "Edit transaction" });
    expect(within(form).getByLabelText(/^Account/)).toHaveValue(account.id);
    expect(within(form).getByLabelText(/^Category/)).toHaveValue(category.id);
    fireEvent.change(within(form).getByLabelText(/^Description/), {
      target: { value: "Juniper Market corrected" },
    });
    fireEvent.change(within(form).getByLabelText(/^Amount/), { target: { value: "-80.25" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));

    await screen.findByText("Juniper Market corrected");
    expect(api.state.transactions[0]).toMatchObject({
      account: account.id,
      category: category.id,
      amount: "-80.25",
    });
    const request = api.mutations().find((item) => item.method === "PATCH");
    expect(request?.url.pathname).toContain(`/transactions/${transaction.id}/`);
    expect(request?.body).toMatchObject({ account: account.id, category: category.id });
  });

  it("cancels deletion, retains a transaction after failure, then removes it after a successful retry", async () => {
    let failDelete = true;
    const api = mockApi({}, ({ method, url }) => {
      if (
        method === "DELETE" &&
        url.pathname.endsWith(`/transactions/${transaction.id}/`) &&
        failDelete
      ) {
        return jsonResponse({ detail: "Unable to delete right now. Try again." }, 503);
      }
      return undefined;
    });
    renderApp();
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete transaction Juniper Market" }),
    );
    let confirmation = await screen.findByRole("region", { name: "Delete transaction" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Cancel" }));
    expect(api.mutations()).toHaveLength(0);
    expect(
      screen.getByRole("button", { name: "Delete transaction Juniper Market" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Delete transaction Juniper Market" }));
    confirmation = await screen.findByRole("region", { name: "Delete transaction" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Confirm delete" }));
    await screen.findByText("Unable to delete right now. Try again.");
    expect(api.state.transactions).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Edit transaction Juniper Market" }),
    ).toBeInTheDocument();

    failDelete = false;
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await screen.findByRole("heading", { name: "No matching transactions" });
    expect(api.state.transactions).toHaveLength(0);
    expect(api.mutations().filter((request) => request.method === "DELETE")).toHaveLength(2);
  });

  it("keeps an account with transaction history after a conflict and supports archive and restore", async () => {
    const api = mockApi({}, ({ method, url }) => {
      if (method === "DELETE" && url.pathname.endsWith(`/accounts/${account.id}/`)) {
        return jsonResponse(
          { detail: "This account has transactions. Archive it instead to preserve its history." },
          409,
        );
      }
      return undefined;
    });
    renderApp();
    await screen.findByText("Juniper Market");
    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "Delete account Everyday Checking" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await screen.findByText(
      /This account has transactions\. Archive it instead to preserve its history\./,
    );
    expect(api.state.accounts).toHaveLength(1);
    expect(
      screen.getByRole("button", { name: "Edit account Everyday Checking" }),
    ).toBeInTheDocument();
    const cancel = screen.queryByRole("button", { name: "Cancel" });
    if (cancel) fireEvent.click(cancel);

    fireEvent.click(screen.getByRole("button", { name: "Archive account Everyday Checking" }));
    const restoreButton = await screen.findByRole("button", {
      name: "Restore account Everyday Checking",
    });
    await waitFor(() => expect(restoreButton).toBeEnabled());
    expect(api.state.accounts[0].is_active).toBe(false);
    fireEvent.click(restoreButton);
    await screen.findByRole("button", { name: "Archive account Everyday Checking" });
    expect(api.state.accounts[0].is_active).toBe(true);
    expect(api.state.transactions).toHaveLength(1);
    expect(
      api
        .mutations()
        .filter((request) => request.method === "PATCH")
        .map((request) => request.body),
    ).toEqual([{ is_active: false }, { is_active: true }]);
  });

  it("returns to sign-in when an account save discovers an expired session", async () => {
    const api = mockApi({}, ({ method, url }) => {
      if (method === "PATCH" && url.pathname.endsWith(`/accounts/${account.id}/`)) {
        return jsonResponse({ detail: "Authentication credentials were not provided." }, 401);
      }
      return undefined;
    });
    renderApp();
    await screen.findByText("Juniper Market");
    fireEvent.click(screen.getByRole("button", { name: "Accounts" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit account Everyday Checking" }));
    changeField(/^Account name/, "Updated Checking");
    fireEvent.click(screen.getByRole("button", { name: "Save account" }));

    await screen.findByRole("heading", { name: "Welcome back" });
    expect(screen.queryByRole("heading", { name: "Transaction ledger" })).not.toBeInTheDocument();
    expect(api.state.accounts[0].name).toBe("Everyday Checking");
    await waitFor(() => expect(api.mutations()).toHaveLength(1));
  });

  it("returns to the previous page when deleting the only transaction on the last page", async () => {
    const lastTransaction = {
      ...transaction,
      id: "transaction-2",
      description: "Campus Fuel",
      amount: "-38.21",
    };
    const api = mockApi({ transactions: [{ ...transaction }, lastTransaction] }, undefined, {
      transactionPageSize: 1,
    });
    renderApp();
    await screen.findByText("Juniper Market");
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    const nextButton = screen.getByRole("button", { name: "Next" });
    await waitFor(() => expect(nextButton).toBeEnabled());
    fireEvent.click(nextButton);
    fireEvent.click(await screen.findByRole("button", { name: "Delete transaction Campus Fuel" }));
    expect(screen.getByText("Page 2")).toBeInTheDocument();
    const confirmation = await screen.findByRole("region", { name: "Delete transaction" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Confirm delete" }));

    await screen.findByText("Juniper Market");
    expect(screen.getByText("Page 1")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete transaction Campus Fuel" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    expect(api.state.transactions.map((entry) => entry.id)).toEqual([transaction.id]);
    expect(api.mutations()).toHaveLength(1);
    expect(api.mutations()[0]).toMatchObject({ method: "DELETE" });
    expect(api.mutations()[0].url.pathname).toContain(`/transactions/${lastTransaction.id}/`);
    const transactionRequests = api.requests.filter(
      (request) => request.method === "GET" && request.url.pathname.endsWith("/transactions/"),
    );
    expect(transactionRequests.at(-1)?.url.searchParams.get("page")).toBeNull();
  });

  it("shows a retryable resource error without treating a failed load as an empty workspace", async () => {
    let resourcesUnavailable = true;
    const api = mockApi({}, ({ method, url }) => {
      if (method === "GET" && url.pathname.endsWith("/accounts/") && resourcesUnavailable) {
        return jsonResponse({ detail: "Account service is temporarily unavailable." }, 503);
      }
      return undefined;
    });
    renderApp();
    const error = await screen.findByRole("alert");
    expect(
      within(error).getByText("Account service is temporarily unavailable."),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Set up your workspace" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add transaction/i })).toBeDisabled();

    resourcesUnavailable = false;
    fireEvent.click(within(error).getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /add transaction/i })).toBeEnabled(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Set up your workspace" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit transaction Juniper Market" })).toBeEnabled();
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/accounts/")),
    ).toHaveLength(2);
    expect(api.mutations()).toHaveLength(0);
  });

  it("disables stale row actions until the ledger refresh after a deletion completes", async () => {
    let deleted = false;
    let refreshPending = false;
    let releaseLedger: () => void = () => {
      throw new Error("The delayed ledger response is not ready.");
    };
    const heldLedger = new Promise<Response>((resolve) => {
      releaseLedger = () => resolve(jsonResponse(paginated([])));
    });
    const api = mockApi({}, ({ method, url }) => {
      if (method === "DELETE" && url.pathname.endsWith(`/transactions/${transaction.id}/`)) {
        deleted = true;
      }
      if (method === "GET" && url.pathname.endsWith("/transactions/") && deleted) {
        refreshPending = true;
        return heldLedger;
      }
      return undefined;
    });
    renderApp();
    const deleteButton = await screen.findByRole("button", {
      name: "Delete transaction Juniper Market",
    });
    await waitFor(() => expect(deleteButton).toBeEnabled());
    fireEvent.click(deleteButton);
    const confirmation = await screen.findByRole("region", { name: "Delete transaction" });
    fireEvent.click(within(confirmation).getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(refreshPending).toBe(true));
    expect(api.state.transactions).toHaveLength(0);
    expect(screen.queryByRole("region", { name: "Delete transaction" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit transaction Juniper Market" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Delete transaction Juniper Market" }),
    ).toBeDisabled();
    expect(screen.getByRole("region", { name: "Transaction ledger" })).toHaveAttribute(
      "aria-busy",
      "true",
    );

    releaseLedger();
    await screen.findByRole("heading", { name: "No matching transactions" });
    expect(
      screen.queryByRole("button", { name: "Edit transaction Juniper Market" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Transaction ledger" })).toHaveAttribute(
      "aria-busy",
      "false",
    );
    expect(api.mutations()).toHaveLength(1);
  });

  it("retries the failed logout request and reaches sign-in without reloading workspace resources", async () => {
    let logoutAttempts = 0;
    let signedOut = false;
    const api = mockApi({}, ({ method, url }) => {
      if (url.pathname.endsWith("/auth/me/") && signedOut) {
        return jsonResponse({ detail: "Unauthenticated" }, 401);
      }
      if (method === "POST" && url.pathname.endsWith("/auth/logout/")) {
        logoutAttempts += 1;
        if (logoutAttempts === 1) {
          return jsonResponse({ detail: "Unable to sign out right now." }, 500);
        }
        signedOut = true;
        return new Response(null, { status: 204 });
      }
      return undefined;
    });
    renderApp();
    await screen.findByText("Juniper Market");
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    await screen.findByText("Unable to sign out right now.");
    expect(logoutAttempts).toBe(1);
    expect(screen.queryByRole("heading", { name: "Welcome back" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Retry sign out" }));
    await screen.findByRole("heading", { name: "Welcome back" });
    expect(logoutAttempts).toBe(2);
    expect(api.mutations().map((request) => request.url.pathname)).toEqual([
      expect.stringMatching(/\/auth\/logout\/$/),
      expect.stringMatching(/\/auth\/logout\/$/),
    ]);
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/accounts/")),
    ).toHaveLength(1);
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/categories/")),
    ).toHaveLength(1);
  });
});
