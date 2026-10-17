import { expect, test, type Page } from "@playwright/test";

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

const initialTransaction = {
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

function pageOf(results: unknown[]) {
  return { count: results.length, next: null, previous: null, results };
}

async function mockAuthenticatedApi(page: Page) {
  const transactions = [initialTransaction];
  await page.route("http://localhost:8000/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (url.pathname.endsWith("/auth/me/")) {
      await route.fulfill({ json: user });
    } else if (url.pathname.endsWith("/auth/csrf/")) {
      await route.fulfill({ json: { csrfToken: "browser-test-csrf" } });
    } else if (url.pathname.endsWith("/accounts/")) {
      await route.fulfill({ json: pageOf([account]) });
    } else if (url.pathname.endsWith("/categories/")) {
      await route.fulfill({ json: pageOf([category]) });
    } else if (url.pathname.endsWith("/transactions/") && request.method() === "POST") {
      const body = request.postDataJSON();
      const created = {
        ...initialTransaction,
        ...body,
        id: "transaction-2",
        account_name: account.name,
        currency: "USD",
        category_name: null,
      };
      transactions.unshift(created);
      await route.fulfill({ status: 201, json: created });
    } else if (url.pathname.endsWith("/transactions/")) {
      await route.fulfill({ json: pageOf(transactions) });
    } else {
      await route.abort("failed");
    }
  });
}

test("reviews and creates a synthetic ledger entry", async ({ page }) => {
  await mockAuthenticatedApi(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Transaction ledger" })).toBeVisible();
  await expect(page.getByText("Juniper Market")).toBeVisible();

  await page.getByRole("button", { name: /add transaction/i }).click();
  await page.getByLabel("Description").fill("Metro Fuel");
  await page.getByLabel(/^Amount/).fill("-42.18");
  await page.getByRole("button", { name: "Save transaction" }).click();

  await expect(page.getByText("Transaction created successfully.")).toBeAttached();
  await expect(page.getByText("Metro Fuel")).toBeVisible();
});

test("renders the finance workflow on a mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockAuthenticatedApi(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: "Know where the money moves." })).toBeVisible();
  await expect(page.getByRole("button", { name: /add transaction/i })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
});
