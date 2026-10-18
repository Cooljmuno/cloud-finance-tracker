import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type {
  CategorizationRule,
  Category,
  FinanceTransaction,
  FinancialAccount,
  MonthlyBudget,
  MonthlyReport,
} from "./api/types";
import { AuthProvider } from "./auth/AuthProvider";

const timestamp = "2026-10-01T00:00:00Z";
const account: FinancialAccount = {
  id: "account-1",
  name: "Campus Checking",
  account_type: "checking",
  institution: "Synthetic Bank",
  currency: "USD",
  opening_balance: "500.00",
  is_active: true,
  created_at: timestamp,
  updated_at: timestamp,
};
const groceries: Category = {
  id: "category-1",
  name: "Groceries",
  kind: "expense",
  is_active: true,
  created_at: timestamp,
  updated_at: timestamp,
};
const dining: Category = { ...groceries, id: "category-2", name: "Dining" };
const income: Category = { ...groceries, id: "category-3", name: "Salary", kind: "income" };
const rule: CategorizationRule = {
  id: "rule-1",
  name: "Market purchases",
  match_text: "market",
  priority: 100,
  category: groceries.id,
  category_name: groceries.name,
  is_active: true,
  created_at: timestamp,
  updated_at: timestamp,
};
const transaction: FinanceTransaction = {
  id: "transaction-1",
  account: account.id,
  account_name: account.name,
  currency: "USD",
  category: groceries.id,
  category_name: groceries.name,
  category_source: "rule",
  matched_rule: rule.id,
  matched_rule_name: rule.name,
  import_batch: null,
  transaction_date: "2026-10-08",
  description: "Juniper Market",
  amount: "-35.50",
  status: "posted",
  notes: "Synthetic purchase",
  created_at: timestamp,
  updated_at: timestamp,
};

type RequestRecord = { method: string; url: URL; body: Record<string, unknown> };
type State = {
  accounts: FinancialAccount[];
  categories: Category[];
  transactions: FinanceTransaction[];
  rules: CategorizationRule[];
  budgets: MonthlyBudget[];
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function page(results: unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

function monthlyReport(
  month: string,
  currency: string,
  budgets: MonthlyBudget[] = [],
): MonthlyReport {
  const budget = budgets.find((entry) => entry.month === month && entry.currency === currency);
  return {
    month,
    currency,
    transaction_count: 1,
    pending_count: 1,
    totals: {
      income: "1200.00",
      spending: "35.50",
      net: "1164.50",
      uncategorized_spending: "0.00",
    },
    categories: [
      {
        category: groceries.id,
        category_name: groceries.name,
        spending: "35.50",
        budget: budget?.amount ?? null,
        remaining: budget ? (Number(budget.amount) - 35.5).toFixed(2) : null,
        budget_id: budget?.id ?? null,
      },
    ],
    trend: Array.from({ length: 6 }, (_, index) => {
      const [year, calendarMonth] = month.split("-").map(Number);
      const date = new Date(year, calendarMonth - 6 + index, 1);
      return {
        month: `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`,
        income: index === 5 ? "1200.00" : "0.00",
        spending: index === 5 ? "35.50" : "0.00",
      };
    }),
  };
}

function mockPlanning(
  initial: Partial<State> = {},
  override?: (
    request: RequestRecord,
    state: State,
  ) => Response | undefined | Promise<Response | undefined>,
) {
  const state: State = {
    accounts: [{ ...account }],
    categories: [{ ...groceries }, { ...dining }, { ...income }],
    transactions: [{ ...transaction }],
    rules: [{ ...rule }],
    budgets: [],
    ...initial,
  };
  const requests: RequestRecord[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const request: RequestRecord = {
        method: init?.method ?? "GET",
        url: new URL(String(input)),
        body: init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {},
      };
      requests.push(request);
      const overridden = await override?.(request, state);
      if (overridden) return overridden;
      const { method, url, body } = request;
      if (url.pathname.endsWith("/auth/me/"))
        return json({ id: "user-1", username: "planning-user", email: "qa@local.invalid" });
      if (url.pathname.endsWith("/auth/csrf/")) return json({ csrfToken: "planning-csrf" });
      if (url.pathname.endsWith("/reports/monthly/")) {
        return json(
          monthlyReport(
            url.searchParams.get("month")!,
            url.searchParams.get("currency")!,
            state.budgets,
          ),
        );
      }
      if (url.pathname.endsWith("/rules/apply/") && method === "POST")
        return json({ updated: 0, examined: 1 });
      const match = url.pathname.match(
        /\/(accounts|categories|transactions|rules|budgets)\/(?:([^/]+)\/)?$/,
      );
      if (!match) throw new Error(`Unhandled request: ${method} ${url}`);
      const resource = match[1] as keyof State;
      const id = match[2];
      if (method === "GET" && !id) {
        const results =
          resource === "budgets"
            ? state.budgets.filter(
                (entry) =>
                  entry.month === url.searchParams.get("month") &&
                  entry.currency === url.searchParams.get("currency"),
              )
            : state[resource];
        return json(page(results));
      }
      if (method === "POST" && !id) {
        if (resource === "rules") {
          const created = {
            ...rule,
            ...body,
            id: `rule-${state.rules.length + 1}`,
            category_name: state.categories.find((entry) => entry.id === body.category)?.name,
          } as CategorizationRule;
          state.rules.push(created);
          return json(created, 201);
        }
        if (resource === "budgets") {
          const created = {
            ...body,
            id: `budget-${state.budgets.length + 1}`,
            created_at: timestamp,
            updated_at: timestamp,
            category_name: state.categories.find((entry) => entry.id === body.category)?.name,
          } as MonthlyBudget;
          state.budgets.push(created);
          return json(created, 201);
        }
        if (resource === "transactions") {
          const automatic = body.category_mode === "automatic";
          const matched = automatic
            ? state.rules.find(
                (entry) =>
                  entry.is_active &&
                  String(body.description).toLowerCase().includes(entry.match_text),
              )
            : undefined;
          const category = matched?.category ?? body.category ?? null;
          const created = {
            ...transaction,
            ...body,
            id: `transaction-${state.transactions.length + 1}`,
            category,
            category_name: state.categories.find((entry) => entry.id === category)?.name ?? null,
            category_source: automatic ? (matched ? "rule" : "uncategorized") : "manual",
            matched_rule: matched?.id ?? null,
            matched_rule_name: matched?.name ?? null,
          } as FinanceTransaction;
          state.transactions.push(created);
          return json(created, 201);
        }
      }
      if (method === "PATCH" && id) {
        const existing = state[resource].find((entry) => entry.id === id);
        if (!existing) return json({ detail: "Not found." }, 404);
        Object.assign(existing, body);
        return json(existing);
      }
      if (method === "DELETE" && id) {
        if (resource === "rules") state.rules = state.rules.filter((entry) => entry.id !== id);
        if (resource === "budgets")
          state.budgets = state.budgets.filter((entry) => entry.id !== id);
        return new Response(null, { status: 204 });
      }
      throw new Error(`Unhandled request: ${method} ${url}`);
    }),
  );
  return {
    state,
    requests,
    mutations: (resource: string) =>
      requests.filter(
        (entry) => entry.method !== "GET" && entry.url.pathname.includes(`/${resource}/`),
      ),
    reads: (resource: string) =>
      requests.filter(
        (entry) => entry.method === "GET" && entry.url.pathname.includes(`/${resource}/`),
      ),
  };
}

function renderApp() {
  render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
}

async function openTab(name: "Rules" | "Planning") {
  renderApp();
  fireEvent.click(await screen.findByRole("button", { name }));
  await screen.findByRole("heading", {
    name: name === "Rules" ? "Categorization rules" : "Monthly spending",
  });
}

function change(label: string | RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

async function clickReady(name: string) {
  await waitFor(() => expect(screen.getByRole("button", { name })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name }));
}

async function addBudget(amount = "100.00") {
  await clickReady("Add budget");
  change("Budget category", groceries.id);
  change("Budget amount", amount);
}

afterEach(() => vi.unstubAllGlobals());

describe("Rules and monthly planning workflows", () => {
  it("saves an ordered literal rule, retains failed edits, and confirms deletion", async () => {
    let failEdit = true;
    const api = mockPlanning({ rules: [] }, ({ method, url }) => {
      if (method === "PATCH" && url.pathname.includes("/rules/") && failEdit) {
        return json({ name: ["A rule with this name already exists."] }, 400);
      }
      return undefined;
    });
    await openTab("Rules");
    await clickReady("Add rule");
    change("Rule name", "Campus meals");
    change("Description contains", "campus cafe");
    change("Rule priority", "5");
    change("Rule category", dining.id);
    fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
    await clickReady("Edit rule Campus meals");
    expect(api.mutations("rules")[0].body).toMatchObject({
      name: "Campus meals",
      match_text: "campus cafe",
      priority: 5,
      category: dining.id,
      is_active: true,
    });
    expect(api.mutations("rules").some((entry) => entry.url.pathname.endsWith("/apply/"))).toBe(
      false,
    );
    change("Rule name", "Meals");
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await screen.findByText("A rule with this name already exists.");
    expect(screen.getByLabelText("Rule name")).toHaveValue("Meals");
    expect(api.state.rules[0].name).toBe("Campus meals");
    failEdit = false;
    fireEvent.click(screen.getByRole("button", { name: "Save rule" }));
    await clickReady("Delete rule Meals");
    expect(api.state.rules).toHaveLength(1);
    expect(api.mutations("rules").filter((entry) => entry.method === "DELETE")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    await waitFor(() => expect(api.state.rules).toHaveLength(0));
  });

  it("applies rules only after explicit confirmation and refreshes the ledger without changing manual choices", async () => {
    const unassigned = {
      ...transaction,
      category: null,
      category_name: null,
      category_source: "uncategorized" as const,
      matched_rule: null,
      matched_rule_name: null,
    };
    const manual = {
      ...unassigned,
      id: "transaction-2",
      description: "Manual market choice",
      category_source: "manual" as const,
    };
    const api = mockPlanning({ transactions: [unassigned, manual] }, ({ method, url }, state) => {
      if (method === "POST" && url.pathname.endsWith("/rules/apply/")) {
        state.transactions[0] = {
          ...state.transactions[0],
          category: groceries.id,
          category_name: groceries.name,
          category_source: "rule",
          matched_rule: rule.id,
          matched_rule_name: rule.name,
        };
        return json({ updated: 1, examined: 1 });
      }
      return undefined;
    });
    await openTab("Rules");
    await clickReady("Apply rules");
    await screen.findByRole("group", { name: "Confirm applying rules" });
    expect(api.mutations("rules")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm apply" }));
    await waitFor(() => expect(api.mutations("rules")).toHaveLength(1));
    await waitFor(() => expect(screen.getByRole("button", { name: "Transactions" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    const row = (await screen.findByText("Juniper Market")).closest("tr")!;
    expect(within(row).getByText(groceries.name)).toBeInTheDocument();
    const manualRow = screen.getByText("Manual market choice").closest("tr")!;
    expect(within(manualRow).getByText("Uncategorized")).toBeInTheDocument();
    expect(api.state.transactions[1].category_source).toBe("manual");
    expect(api.reads("transactions").length).toBeGreaterThan(1);
  });

  it("preserves a rule-assigned transaction's provenance when editing only its notes", async () => {
    const api = mockPlanning();
    renderApp();
    await clickReady("Edit transaction Juniper Market");
    const form = await screen.findByRole("region", { name: "Edit transaction" });
    expect(within(form).getByLabelText(/^Category/)).toHaveValue("__automatic");
    fireEvent.change(within(form).getByLabelText(/^Notes/), {
      target: { value: "Receipt checked" },
    });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(api.mutations("transactions")).toHaveLength(1));
    const payload = api.mutations("transactions")[0].body;
    expect(payload).toMatchObject({ notes: "Receipt checked" });
    expect(payload).not.toHaveProperty("category");
    expect(payload).not.toHaveProperty("category_mode");
    expect(payload).not.toHaveProperty("matched_rule");
    expect(api.state.transactions[0]).toMatchObject({
      category_source: "rule",
      matched_rule: rule.id,
    });
  });

  it("creates automatic transactions by default and sends an explicit manual null choice", async () => {
    const api = mockPlanning({ transactions: [] });
    renderApp();
    await clickReady("Add transaction");
    let form = await screen.findByRole("region", { name: "Add transaction" });
    expect(within(form).getByLabelText(/^Category/)).toHaveValue("__automatic");
    fireEvent.change(within(form).getByLabelText(/^Description/), {
      target: { value: "Evening market" },
    });
    fireEvent.change(within(form).getByLabelText(/^Amount/), { target: { value: "-18.50" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save transaction" }));
    await screen.findByText("Evening market");
    expect(api.mutations("transactions")[0].body).toMatchObject({ category_mode: "automatic" });
    expect(api.mutations("transactions")[0].body.category ?? null).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Add transaction" }));
    form = await screen.findByRole("region", { name: "Add transaction" });
    fireEvent.change(within(form).getByLabelText(/^Category/), { target: { value: "" } });
    fireEvent.change(within(form).getByLabelText(/^Description/), {
      target: { value: "Keep market unassigned" },
    });
    fireEvent.change(within(form).getByLabelText(/^Amount/), { target: { value: "-6.25" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save transaction" }));
    await screen.findByText("Keep market unassigned");
    expect(api.mutations("transactions")[1].body).toMatchObject({
      category_mode: "manual",
      category: null,
    });
    expect(api.state.transactions[1]).toMatchObject({
      category: null,
      category_source: "manual",
      matched_rule: null,
    });
  });

  it("creates and edits a budget, refreshes actuals after each save, and confirms deletion", async () => {
    const api = mockPlanning();
    await openTab("Planning");
    await addBudget();
    const selectedMonth = (screen.getByLabelText("Budget month") as HTMLInputElement).value;
    const reportReads = api.reads("reports").length;
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    await clickReady("Edit budget for Groceries");
    expect(api.mutations("budgets")[0].body).toEqual({
      category: groceries.id,
      month: selectedMonth,
      currency: "USD",
      amount: "100.00",
    });
    await waitFor(() => expect(api.reads("reports").length).toBeGreaterThan(reportReads));
    change("Budget amount", "125.00");
    fireEvent.click(screen.getByRole("button", { name: "Save budget" }));
    await clickReady("Delete budget for Groceries");
    expect(api.state.budgets[0].amount).toBe("125.00");
    expect(api.mutations("budgets").filter((entry) => entry.method === "DELETE")).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete budget" }));
    await waitFor(() => expect(api.state.budgets).toHaveLength(0));
    await waitFor(() => expect(api.reads("reports").length).toBeGreaterThan(reportReads + 1));
    expect(
      screen.queryByRole("button", { name: "Edit budget for Groceries" }),
    ).not.toBeInTheDocument();
  });

  it("rejects an invalid budget locally and preserves the form after a duplicate response", async () => {
    let duplicate = true;
    const api = mockPlanning({}, ({ method, url }) => {
      if (method === "POST" && url.pathname.endsWith("/budgets/") && duplicate) {
        return json(
          { non_field_errors: ["A budget already exists for this category, month, and currency."] },
          400,
        );
      }
      return undefined;
    });
    await openTab("Planning");
    await addBudget("-5.00");
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    expect(api.mutations("budgets")).toHaveLength(0);
    expect(screen.getByLabelText("Budget amount")).toHaveValue("-5.00");
    change("Budget amount", "100.00");
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    await screen.findByText("A budget already exists for this category, month, and currency.");
    expect(screen.getByLabelText("Budget amount")).toHaveValue("100.00");
    expect(screen.getByLabelText("Budget category")).toHaveValue(groceries.id);
    expect(api.state.budgets).toHaveLength(0);
    duplicate = false;
    change("Budget category", dining.id);
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    await screen.findByRole("button", { name: "Edit budget for Dining" });
    expect(api.state.budgets[0]).toMatchObject({ category: dining.id, amount: "100.00" });
  });

  it("retains a budget after a failed delete and succeeds on retry", async () => {
    let unavailable = true;
    const api = mockPlanning({}, ({ method, url }) => {
      if (method === "DELETE" && url.pathname.includes("/budgets/") && unavailable)
        return json({ detail: "Budget delete is temporarily unavailable." }, 503);
      return undefined;
    });
    await openTab("Planning");
    await addBudget();
    fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
    await clickReady("Delete budget for Groceries");
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete budget" }));
    await screen.findByText("Budget delete is temporarily unavailable.");
    expect(api.state.budgets).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Edit budget for Groceries" })).toBeInTheDocument();
    unavailable = false;
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete budget" }));
    await waitFor(() => expect(api.state.budgets).toHaveLength(0));
  });

  it("requests the selected month and currency and ignores an older report that arrives late", async () => {
    let releaseOld: ((response: Response) => void) | undefined;
    let slowMonth = "";
    const api = mockPlanning(
      {
        accounts: [
          { ...account },
          { ...account, id: "euro-account", name: "Euro Savings", currency: "EUR" },
        ],
      },
      ({ url }) => {
        if (url.pathname.endsWith("/reports/monthly/") && !slowMonth) {
          slowMonth = url.searchParams.get("month")!;
          return new Promise<Response>((resolve) => {
            releaseOld = resolve;
          });
        }
        if (url.pathname.endsWith("/reports/monthly/")) {
          const report = monthlyReport(
            url.searchParams.get("month")!,
            url.searchParams.get("currency")!,
          );
          return json({ ...report, totals: { ...report.totals, spending: "77.25" } });
        }
        return undefined;
      },
    );
    await openTab("Planning");
    await waitFor(() => expect(releaseOld).toBeDefined());
    const selected = slowMonth === "2026-09" ? "2026-08" : "2026-09";
    change("Budget month", selected);
    change("Report currency", "EUR");
    await waitFor(() =>
      expect(api.reads("reports").at(-1)?.url.searchParams.get("currency")).toBe("EUR"),
    );
    await screen.findAllByText(/77\.25/);
    await act(async () => {
      releaseOld!(
        json({
          ...monthlyReport(slowMonth, "USD"),
          totals: {
            income: "999.99",
            spending: "999.99",
            net: "0.00",
            uncategorized_spending: "0.00",
          },
        }),
      );
    });
    expect(screen.queryByText(/999\.99/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Budget month")).toHaveValue(selected);
    expect(screen.getByLabelText("Report currency")).toHaveValue("EUR");
    expect(api.reads("budgets").at(-1)?.url.searchParams.get("month")).toBe(selected);
    expect(api.reads("budgets").at(-1)?.url.searchParams.get("currency")).toBe("EUR");
  });

  it("shows a report failure instead of zero totals and retries the selected report", async () => {
    let unavailable = true;
    const api = mockPlanning({}, ({ url }) => {
      if (url.pathname.endsWith("/reports/monthly/") && unavailable)
        return json({ detail: "Monthly totals are temporarily unavailable." }, 503);
      return undefined;
    });
    await openTab("Planning");
    await screen.findByText("Monthly totals are temporarily unavailable.");
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /category spending/i })).not.toBeInTheDocument();
    const reads = api.reads("reports").length;
    unavailable = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry report" }));
    await screen.findAllByText("$35.50");
    expect(
      screen.queryByText("Monthly totals are temporarily unavailable."),
    ).not.toBeInTheDocument();
    expect(api.reads("reports")).toHaveLength(reads + 1);
    const first = api.reads("reports")[0].url.searchParams;
    expect(api.reads("reports").at(-1)?.url.searchParams.toString()).toBe(first.toString());
  });

  it("keeps report results available while separately retrying failed budget history", async () => {
    let unavailable = true;
    const api = mockPlanning({}, ({ url }) => {
      if (url.pathname.endsWith("/budgets/") && unavailable)
        return json({ detail: "Budgets are temporarily unavailable." }, 503);
      return undefined;
    });
    await openTab("Planning");
    await screen.findByText("Budgets are temporarily unavailable.");
    expect((await screen.findAllByText("$35.50")).length).toBeGreaterThan(0);
    const reportReads = api.reads("reports").length;
    unavailable = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry budgets" }));
    await waitFor(() =>
      expect(screen.queryByText("Budgets are temporarily unavailable.")).not.toBeInTheDocument(),
    );
    expect(api.reads("budgets")).toHaveLength(2);
    expect(api.reads("reports")).toHaveLength(reportReads);
  });

  it("guides users to create an expense category before budgeting and excludes income categories", async () => {
    const api = mockPlanning({ categories: [{ ...income }] });
    await openTab("Planning");
    await screen.findByText(/create.*expense category|expense category.*Categories/i);
    const add = screen.queryByRole("button", { name: "Add budget" });
    if (add) expect(add).toBeDisabled();
    expect(screen.queryByRole("option", { name: income.name })).not.toBeInTheDocument();
    expect(api.mutations("budgets")).toHaveLength(0);
  });

  it.each(["rules", "budgets"])(
    "returns to sign-in when a %s mutation discovers an expired session",
    async (resource) => {
      const api = mockPlanning({}, ({ method, url }) => {
        if (method === "POST" && url.pathname.endsWith(`/${resource}/`))
          return json({ detail: "Authentication credentials were not provided." }, 401);
        return undefined;
      });
      await openTab(resource === "rules" ? "Rules" : "Planning");
      if (resource === "rules") {
        await clickReady("Add rule");
        change("Rule name", "New rule");
        change("Description contains", "coffee");
        change("Rule category", groceries.id);
        fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
      } else {
        await addBudget();
        fireEvent.click(screen.getByRole("button", { name: "Create budget" }));
      }
      await screen.findByRole("heading", { name: "Welcome back" });
      expect(api.mutations(resource)).toHaveLength(1);
      expect(api.state.budgets).toHaveLength(0);
      expect(api.state.rules).toHaveLength(1);
    },
  );
});
