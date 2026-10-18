import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { FinancialAccount } from "./api/types";
import { AuthProvider } from "./auth/AuthProvider";

const account: FinancialAccount = {
  id: "account-1",
  name: "Everyday Checking",
  account_type: "checking",
  institution: "Northstar Community Bank",
  currency: "USD",
  opening_balance: "0.00",
  is_active: true,
  created_at: "2026-08-01T00:00:00Z",
  updated_at: "2026-08-01T00:00:00Z",
};

const batch = {
  id: "import-1",
  account: account.id,
  account_name: account.name,
  file_name: "statement.csv",
  file_hash: "synthetic-sha256",
  row_count: 1,
  created_at: "2026-10-18T00:00:00Z",
};

const importedTransaction = {
  id: "transaction-1",
  account: account.id,
  account_name: account.name,
  currency: "USD",
  category: null,
  category_name: null,
  transaction_date: "2026-10-01",
  description: "Campus Lunch",
  amount: "-12.35",
  status: "posted",
  notes: "Imported purchase",
  import_batch: batch.id,
  category_source: "uncategorized",
  matched_rule: null,
  matched_rule_name: null,
  created_at: "2026-10-18T00:00:00Z",
  updated_at: "2026-10-18T00:00:00Z",
};

function previewResponse(selectedAccount = account.id, fileName = "statement.csv") {
  return {
    account: selectedAccount,
    file_name: fileName,
    row_count: 1,
    valid_count: 1,
    error_count: 0,
    errors: [],
    errors_truncated: false,
    rows: [
      {
        row: 2,
        transaction_date: "2026-10-01",
        description: "Campus Lunch",
        amount: "-12.35",
        status: "posted",
        notes: "Imported purchase",
      },
    ],
    preview_truncated: false,
    preview_token: "server-issued-preview-token",
    already_imported: null,
    can_commit: true,
  };
}

type ImportState = {
  accounts: FinancialAccount[];
  imports: (typeof batch)[];
  transactions: Record<string, unknown>[];
};

type ImportRequest = {
  method: string;
  url: URL;
  body: RequestInit["body"];
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

function mockImports(
  initial: Partial<ImportState> = {},
  override?: (
    request: ImportRequest,
    state: ImportState,
  ) => Response | undefined | Promise<Response | undefined>,
) {
  const state: ImportState = {
    accounts: [{ ...account }],
    imports: [],
    transactions: [],
    ...initial,
  };
  const requests: ImportRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string | URL | Request, init?: RequestInit) => {
      const request = {
        method: init?.method ?? "GET",
        url: new URL(String(input)),
        body: init?.body,
      };
      requests.push(request);
      const overridden = await override?.(request, state);
      if (overridden) return overridden;
      const { method, url, body } = request;
      if (url.pathname.endsWith("/auth/me/")) {
        return jsonResponse({ id: "user-1", username: "new-user", email: "demo@local.invalid" });
      }
      if (url.pathname.endsWith("/auth/csrf/")) return jsonResponse({ csrfToken: "import-csrf" });
      if (method === "GET" && url.pathname.endsWith("/accounts/")) {
        return jsonResponse(paginated(state.accounts));
      }
      if (method === "GET" && url.pathname.endsWith("/categories/")) {
        return jsonResponse(paginated([]));
      }
      if (method === "GET" && url.pathname.endsWith("/transactions/")) {
        return jsonResponse(paginated(state.transactions));
      }
      if (method === "GET" && url.pathname.endsWith("/imports/")) {
        return jsonResponse(paginated(state.imports));
      }
      if (method === "POST" && url.pathname.endsWith("/imports/preview/")) {
        if (!(body instanceof FormData)) throw new Error("Preview upload must use FormData.");
        return jsonResponse(
          previewResponse(String(body.get("account")), (body.get("file") as File).name),
        );
      }
      if (method === "POST" && url.pathname.endsWith("/imports/commit/")) {
        if (!(body instanceof FormData)) throw new Error("Commit upload must use FormData.");
        const existing = state.imports.find((entry) => entry.account === body.get("account"));
        if (existing) return jsonResponse({ batch: existing, duplicate: true });
        const saved = {
          ...batch,
          account: String(body.get("account")),
          file_name: (body.get("file") as File).name,
        };
        state.imports.push(saved);
        state.transactions.push({ ...importedTransaction, account: saved.account });
        return jsonResponse({ batch: saved, duplicate: false }, 201);
      }
      throw new Error(`Unhandled request: ${method} ${url}`);
    }),
  );
  return {
    state,
    requests,
    uploads: (action: "preview" | "commit") =>
      requests.filter(
        (request) =>
          request.method === "POST" && request.url.pathname.endsWith(`/imports/${action}/`),
      ),
  };
}

async function openImports() {
  render(
    <AuthProvider>
      <App />
    </AuthProvider>,
  );
  fireEvent.click(await screen.findByRole("button", { name: "Imports" }));
  await screen.findByLabelText("Import account");
}

function uploadStatement(name = "statement.csv") {
  const file = new File(
    [
      "transaction_date,description,amount,status,notes\n2026-10-01,Campus Lunch,-12.35,posted,Imported purchase\n",
    ],
    name,
    { type: "text/csv" },
  );
  fireEvent.change(screen.getByLabelText("CSV file"), { target: { files: [file] } });
  return file;
}

async function previewStatement() {
  const file = uploadStatement();
  fireEvent.click(screen.getByRole("button", { name: "Preview import" }));
  const preview = await screen.findByRole("region", { name: "Import preview" });
  return { file, preview };
}

afterEach(() => vi.unstubAllGlobals());

describe("CSV import workflows", () => {
  it("previews multipart data without saving and imports transactions only after confirmation", async () => {
    const api = mockImports();
    await openImports();
    const { file, preview } = await previewStatement();

    expect(within(preview).getByText("Campus Lunch")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Import transactions" })).toBeEnabled();
    expect(api.uploads("preview")).toHaveLength(1);
    const body = api.uploads("preview")[0].body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("account")).toBe(account.id);
    expect(body.get("file")).toBe(file);
    expect(body.get("preview_token")).toBeNull();
    expect(api.uploads("commit")).toHaveLength(0);
    expect(api.state.transactions).toHaveLength(0);
    expect(api.state.imports).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Import transactions" }));
    await screen.findByRole("heading", { name: "Import complete" });
    expect(api.uploads("commit")).toHaveLength(1);
    const committedBody = api.uploads("commit")[0].body as FormData;
    expect(committedBody.get("account")).toBe(account.id);
    expect(committedBody.get("file")).toBe(file);
    expect(committedBody.get("preview_token")).toBe("server-issued-preview-token");
    expect(api.state.transactions).toHaveLength(1);
    expect(api.state.imports).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    await screen.findByText("Campus Lunch");
  });

  it("displays backend row errors and blocks committing an invalid preview", async () => {
    const api = mockImports({}, ({ url }) => {
      if (url.pathname.endsWith("/imports/preview/")) {
        return jsonResponse({
          ...previewResponse(),
          valid_count: 0,
          error_count: 1,
          errors: [
            {
              row: 2,
              field: "amount",
              message: "Use a nonzero amount with at most two decimal places.",
            },
          ],
          rows: [],
          preview_token: null,
          can_commit: false,
        });
      }
      return undefined;
    });
    await openImports();
    const { preview } = await previewStatement();

    expect(
      within(preview).getByText("Use a nonzero amount with at most two decimal places."),
    ).toBeInTheDocument();
    const errorTable = within(preview)
      .getByRole("columnheader", { name: "Error" })
      .closest("table");
    expect(errorTable).not.toBeNull();
    expect(within(errorTable!).getByRole("cell", { name: "2" })).toBeInTheDocument();
    expect(within(errorTable!).getByRole("cell", { name: "amount" })).toBeInTheDocument();
    const commit = screen.queryByRole("button", { name: "Import transactions" });
    if (commit) {
      expect(commit).toBeDisabled();
      fireEvent.click(commit);
    }
    expect(api.uploads("commit")).toHaveLength(0);
    expect(api.state.transactions).toHaveLength(0);
  });

  it("clears a prior preview when the file or destination account changes", async () => {
    const api = mockImports({
      accounts: [{ ...account }, { ...account, id: "account-2", name: "Savings" }],
    });
    await openImports();
    await previewStatement();
    uploadStatement("revised-statement.csv");
    expect(screen.queryByRole("region", { name: "Import preview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import transactions" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Preview import" }));
    await screen.findByRole("region", { name: "Import preview" });
    fireEvent.change(screen.getByLabelText("Import account"), { target: { value: "account-2" } });

    expect(screen.queryByRole("region", { name: "Import preview" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import transactions" })).not.toBeInTheDocument();
    expect(api.uploads("preview")).toHaveLength(2);
    expect((api.uploads("preview")[1].body as FormData).get("account")).toBe(account.id);
    expect(api.uploads("commit")).toHaveLength(0);
  });

  it("retries an uncertain commit with the same file and token and accepts the server duplicate receipt", async () => {
    let firstCommit = true;
    const api = mockImports({}, ({ method, url }, state) => {
      if (method === "POST" && url.pathname.endsWith("/imports/commit/") && firstCommit) {
        firstCommit = false;
        state.imports.push({ ...batch });
        state.transactions.push({ ...importedTransaction });
        throw new TypeError("Network connection interrupted.");
      }
      return undefined;
    });
    await openImports();
    const { file } = await previewStatement();
    const ledgerReadsBeforeCommit = api.requests.filter((request) =>
      request.url.pathname.endsWith("/transactions/"),
    ).length;
    fireEvent.click(screen.getByRole("button", { name: "Import transactions" }));
    await screen.findByText(/Network connection interrupted\./);

    expect(screen.getByRole("region", { name: "Import preview" })).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Import transactions" })).toBeEnabled(),
    );
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/transactions/")),
    ).toHaveLength(ledgerReadsBeforeCommit);
    fireEvent.click(screen.getByRole("button", { name: "Import transactions" }));
    await screen.findByRole("heading", { name: "File already imported" });
    expect(screen.getByText("No transactions added.")).toBeInTheDocument();
    expect(api.uploads("preview")).toHaveLength(1);
    expect(api.uploads("commit")).toHaveLength(2);
    for (const request of api.uploads("commit")) {
      const body = request.body as FormData;
      expect(body.get("file")).toBe(file);
      expect(body.get("account")).toBe(account.id);
      expect(body.get("preview_token")).toBe("server-issued-preview-token");
    }
    expect(api.state.imports).toHaveLength(1);
    expect(api.state.transactions).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    await screen.findByText("Campus Lunch");
  });

  it("retries failed import history without submitting an upload", async () => {
    let historyUnavailable = true;
    const api = mockImports({ imports: [{ ...batch }] }, ({ method, url }) => {
      if (method === "GET" && url.pathname.endsWith("/imports/") && historyUnavailable) {
        return jsonResponse({ detail: "Import history is temporarily unavailable." }, 503);
      }
      return undefined;
    });
    await openImports();
    const history = await screen.findByRole("region", { name: "Import history" });
    await within(history).findByText("Import history is temporarily unavailable.");
    historyUnavailable = false;
    fireEvent.click(within(history).getByRole("button", { name: "Retry history" }));

    await within(history).findByText("statement.csv");
    expect(within(history).queryByRole("alert")).not.toBeInTheDocument();
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/imports/")),
    ).toHaveLength(2);
    expect(api.uploads("preview")).toHaveLength(0);
    expect(api.uploads("commit")).toHaveLength(0);
  });

  it("refreshes history and the cached ledger when re-preview confirms an uncertain import already completed", async () => {
    const api = mockImports({}, ({ method, url }, state) => {
      if (method === "POST" && url.pathname.endsWith("/imports/commit/")) {
        state.imports.push({ ...batch });
        state.transactions.push({ ...importedTransaction });
        throw new TypeError("Import response was interrupted.");
      }
      if (
        method === "POST" &&
        url.pathname.endsWith("/imports/preview/") &&
        state.imports.length > 0
      ) {
        return jsonResponse({
          ...previewResponse(),
          already_imported: state.imports[0],
          can_commit: false,
        });
      }
      return undefined;
    });
    await openImports();
    const history = await screen.findByRole("region", { name: "Import history" });
    await within(history).findByText("No completed imports yet.");
    const { file } = await previewStatement();
    const ledgerReadsBeforeCommit = api.requests.filter((request) =>
      request.url.pathname.endsWith("/transactions/"),
    ).length;
    fireEvent.click(screen.getByRole("button", { name: "Import transactions" }));
    await screen.findByText(/Import response was interrupted\./);
    expect(
      api.requests.filter((request) => request.url.pathname.endsWith("/transactions/")),
    ).toHaveLength(ledgerReadsBeforeCommit);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Preview import" })).toBeEnabled(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Preview import" }));
    await screen.findByRole("heading", { name: "File already imported" });
    await within(history).findByRole("cell", { name: "statement.csv" });
    expect(screen.getByRole("button", { name: "Import transactions" })).toBeDisabled();
    await waitFor(() =>
      expect(
        api.requests.filter((request) => request.url.pathname.endsWith("/transactions/")).length,
      ).toBeGreaterThan(ledgerReadsBeforeCommit),
    );
    expect(api.uploads("preview")).toHaveLength(2);
    expect((api.uploads("preview")[1].body as FormData).get("file")).toBe(file);
    expect(api.uploads("commit")).toHaveLength(1);
    expect(api.state.imports).toHaveLength(1);
    expect(api.state.transactions).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Transactions" }));
    await screen.findByText("Campus Lunch");
  });

  it("requires an active account before previewing a file", async () => {
    const api = mockImports({ accounts: [{ ...account, is_active: false }] });
    await openImports();
    await screen.findByText(
      "Create or restore an account in Accounts before importing transactions.",
    );
    expect(screen.getByRole("button", { name: "Preview import" })).toBeDisabled();
    expect(screen.queryByRole("option", { name: account.name })).not.toBeInTheDocument();
    expect(api.uploads("preview")).toHaveLength(0);
    expect(api.uploads("commit")).toHaveLength(0);
  });

  it("returns to sign-in when a commit discovers an expired session", async () => {
    const api = mockImports({}, ({ method, url }) => {
      if (method === "POST" && url.pathname.endsWith("/imports/commit/")) {
        return jsonResponse({ detail: "Authentication credentials were not provided." }, 401);
      }
      return undefined;
    });
    await openImports();
    await previewStatement();
    fireEvent.click(screen.getByRole("button", { name: "Import transactions" }));

    await screen.findByRole("heading", { name: "Welcome back" });
    expect(screen.queryByRole("region", { name: "Import preview" })).not.toBeInTheDocument();
    expect(api.state.imports).toHaveLength(0);
    expect(api.state.transactions).toHaveLength(0);
  });
});
