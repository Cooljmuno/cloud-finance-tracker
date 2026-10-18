import { useEffect, useState } from "react";

import { ApiError, type AuthTransport } from "../../api/client";
import {
  createAccount,
  createCategory,
  createTransaction,
  deleteAccount,
  deleteCategory,
  deleteTransaction,
  getAccounts,
  getCategories,
  getTransactions,
  updateAccount,
  updateCategory,
  updateTransaction,
} from "../../api/finance";
import type {
  AccountInput,
  Category,
  CategoryInput,
  CreateTransaction,
  FinanceTransaction,
  FinancialAccount,
  Paginated,
  TransactionFilters as Filters,
} from "../../api/types";
import { useAppAuth } from "../../auth/AuthContext";
import { AccountManager } from "../resources/AccountManager";
import { CategoryManager } from "../resources/CategoryManager";
import { TransactionFilters } from "./TransactionFilters";
import { TransactionForm } from "./TransactionForm";
import { TransactionTable } from "./TransactionTable";

const emptyFilters: Filters = {
  account: "",
  category: "",
  status: "",
  dateFrom: "",
  dateTo: "",
};

type WorkspaceView = "Transactions" | "Accounts" | "Categories";

export function DashboardPage() {
  const { user, transport, signOut, invalidate } = useAppAuth();
  const [view, setView] = useState<WorkspaceView>("Transactions");
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [resourcesReady, setResourcesReady] = useState(false);
  const [resourceError, setResourceError] = useState<string | null>(null);
  const [resourceRetry, setResourceRetry] = useState(0);
  const [ledger, setLedger] = useState<Paginated<FinanceTransaction> | null>(null);
  const [ledgerLoading, setLedgerLoading] = useState(true);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [draftFilters, setDraftFilters] = useState<Filters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(emptyFilters);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [editor, setEditor] = useState<FinanceTransaction | "new" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<FinanceTransaction | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [mutationBusy, setMutationBusy] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  useEffect(() => {
    if (!transport) return;
    const controller = new AbortController();
    let active = true;
    setResourceError(null);
    Promise.all([
      getAccounts(transport, controller.signal),
      getCategories(transport, controller.signal),
    ])
      .then(([accountResults, categoryResults]) => {
        if (!active) return;
        setAccounts(accountResults);
        setCategories(categoryResults);
        setResourcesReady(true);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          void invalidate();
          return;
        }
        setResourceError(error instanceof Error ? error.message : "Unable to load your workspace.");
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [invalidate, resourceRetry, transport]);

  useEffect(() => {
    if (!transport) return;
    const controller = new AbortController();
    let active = true;
    setLedgerLoading(true);
    setLedgerError(null);
    getTransactions(transport, appliedFilters, page, controller.signal)
      .then((result) => {
        if (active) setLedger(result);
      })
      .catch((error: unknown) => {
        if (!active) return;
        if (error instanceof ApiError && error.status === 401) {
          void invalidate();
          return;
        }
        if (error instanceof ApiError && error.status === 404 && page > 1) {
          setPage(1);
          return;
        }
        setLedgerError(error instanceof Error ? error.message : "Unable to load transactions.");
      })
      .finally(() => {
        if (active) setLedgerLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [appliedFilters, invalidate, page, refresh, transport]);

  const activeAccounts = accounts.filter((account) => account.is_active);
  const activeCategories = categories.filter((category) => category.is_active);

  async function withTransport<T>(operation: (current: AuthTransport) => Promise<T>): Promise<T> {
    if (!transport) throw new Error("Your session has expired. Sign in again.");
    setMutationBusy(true);
    try {
      return await operation(transport);
    } catch (error: unknown) {
      if (error instanceof ApiError && error.status === 401) await invalidate();
      throw error;
    } finally {
      setMutationBusy(false);
    }
  }

  function refreshLedger(message: string) {
    setLedgerLoading(true);
    setRefresh((current) => current + 1);
    setAnnouncement(message);
  }

  async function saveAccount(payload: AccountInput) {
    const saved = await withTransport((current) => createAccount(current, payload));
    setAccounts((current) => [...current, saved]);
    refreshLedger("Account created.");
  }

  async function changeAccount(
    id: string,
    payload: Partial<AccountInput & { is_active: boolean }>,
  ) {
    const saved = await withTransport((current) => updateAccount(current, id, payload));
    setAccounts((current) => current.map((account) => (account.id === id ? saved : account)));
    refreshLedger("Account updated.");
  }

  async function removeAccount(id: string) {
    await withTransport((current) => deleteAccount(current, id));
    setAccounts((current) => current.filter((account) => account.id !== id));
    setDraftFilters((current) => ({
      ...current,
      account: current.account === id ? "" : current.account,
    }));
    setAppliedFilters((current) => ({
      ...current,
      account: current.account === id ? "" : current.account,
    }));
    setPage(1);
    refreshLedger("Account deleted.");
  }

  async function saveCategory(payload: CategoryInput) {
    const saved = await withTransport((current) => createCategory(current, payload));
    setCategories((current) => [...current, saved]);
    refreshLedger("Category created.");
  }

  async function changeCategory(
    id: string,
    payload: Partial<CategoryInput & { is_active: boolean }>,
  ) {
    const saved = await withTransport((current) => updateCategory(current, id, payload));
    setCategories((current) => current.map((category) => (category.id === id ? saved : category)));
    refreshLedger("Category updated.");
  }

  async function removeCategory(id: string) {
    await withTransport((current) => deleteCategory(current, id));
    setCategories((current) => current.filter((category) => category.id !== id));
    setDraftFilters((current) => ({
      ...current,
      category: current.category === id ? "" : current.category,
    }));
    setAppliedFilters((current) => ({
      ...current,
      category: current.category === id ? "" : current.category,
    }));
    setPage(1);
    refreshLedger("Category deleted.");
  }

  async function submitTransaction(payload: CreateTransaction) {
    await withTransport((current) =>
      editor && editor !== "new"
        ? updateTransaction(current, editor.id, payload)
        : createTransaction(current, payload),
    );
    setEditor(null);
    setPage(1);
    refreshLedger(
      editor === "new" ? "Transaction created successfully." : "Transaction saved successfully.",
    );
  }

  async function confirmDelete() {
    if (!deleteTarget || mutationBusy) return;
    setDeleteError(null);
    try {
      await withTransport((current) => deleteTransaction(current, deleteTarget.id));
      setDeleteTarget(null);
      if (page > 1 && ledger?.results.length === 1) setPage(page - 1);
      refreshLedger("Transaction deleted.");
    } catch (error: unknown) {
      setDeleteError(error instanceof Error ? error.message : "Unable to delete transaction.");
    }
  }

  function changeView(next: WorkspaceView) {
    setView(next);
    setEditor(null);
    setDeleteTarget(null);
    setDeleteError(null);
    setAnnouncement("");
  }

  function applyFilters() {
    if (
      draftFilters.dateFrom &&
      draftFilters.dateTo &&
      draftFilters.dateFrom > draftFilters.dateTo
    ) {
      setFilterError("The end date must be on or after the start date.");
      return;
    }
    setFilterError(null);
    setPage(1);
    setAppliedFilters({ ...draftFilters });
  }

  function resetFilters() {
    setDraftFilters(emptyFilters);
    setAppliedFilters(emptyFilters);
    setFilterError(null);
    setPage(1);
  }

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await signOut();
    } catch (error: unknown) {
      setSignOutError(error instanceof Error ? error.message : "Unable to sign out.");
      setSigningOut(false);
    }
  }

  return (
    <main className="dashboard-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Cloud Finance Tracker home">
          <span className="brand-mark brand-mark--small" aria-hidden="true">
            CF
          </span>
          <span>
            <strong>Cloud Finance</strong>
            <small>Tracker</small>
          </span>
        </a>
        <div className="user-menu">
          <span className="demo-badge">Synthetic demo data</span>
          <span className="user-copy">
            <strong>{user?.username}</strong>
            <small>{user?.email || "Authenticated user"}</small>
          </span>
          <button
            className="text-button"
            type="button"
            onClick={handleSignOut}
            disabled={signingOut || mutationBusy}
          >
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </header>

      <nav className="workspace-nav" aria-label="Workspace">
        {(["Transactions", "Accounts", "Categories"] as const).map((item) => (
          <button
            key={item}
            type="button"
            aria-current={view === item ? "page" : undefined}
            disabled={mutationBusy || signingOut}
            onClick={() => changeView(item)}
          >
            {item}
          </button>
        ))}
      </nav>

      <section className="dashboard-intro">
        <div>
          <p className="eyebrow">
            {view === "Transactions" ? "Transaction workspace" : "Workspace settings"}
          </p>
          <h1>
            {view === "Transactions"
              ? "Know where the money moves."
              : view === "Accounts"
                ? "Accounts that fit your life."
                : "Give every entry context."}
          </h1>
          <p>
            {view === "Transactions"
              ? "Review, organize, and update your transaction history."
              : view === "Accounts"
                ? "Create accounts, edit their details, and archive the ones you no longer use."
                : "Organize expenses, income, and transfers with categories you control."}
          </p>
        </div>
        {view === "Transactions" ? (
          <button
            className="primary-button"
            type="button"
            disabled={!resourcesReady || activeAccounts.length === 0 || mutationBusy}
            onClick={() => {
              setEditor("new");
              setDeleteTarget(null);
              setAnnouncement("");
            }}
          >
            <span aria-hidden="true">＋</span> Add transaction
          </button>
        ) : null}
      </section>

      {resourceError ? (
        <div className="error-banner workspace-error" role="alert">
          <strong>Unable to complete the request.</strong>
          <span>{resourceError}</span>
          <button
            className="text-button"
            type="button"
            onClick={() => setResourceRetry((current) => current + 1)}
          >
            Retry
          </button>
        </div>
      ) : null}
      {announcement ? (
        <p className="success-banner" role="status">
          {announcement}
        </p>
      ) : null}

      {signOutError ? (
        <div className="error-banner workspace-error" role="alert">
          <strong>Unable to sign out.</strong>
          <span>{signOutError}</span>
          <button
            className="text-button"
            type="button"
            disabled={signingOut || mutationBusy}
            onClick={() => void handleSignOut()}
          >
            Retry sign out
          </button>
        </div>
      ) : null}

      {resourcesReady && accounts.length === 0 && view === "Transactions" ? (
        <section className="onboarding-card" aria-labelledby="onboarding-heading">
          <p className="card-kicker">Your first steps</p>
          <h2 id="onboarding-heading">Set up your workspace</h2>
          <p>
            Create an account to start recording transactions. Add categories whenever you are
            ready.
          </p>
          <button className="primary-button" type="button" onClick={() => changeView("Accounts")}>
            Create account
          </button>
        </section>
      ) : resourcesReady && activeAccounts.length === 0 && view === "Transactions" ? (
        <section className="onboarding-card" aria-labelledby="archived-heading">
          <h2 id="archived-heading">Your accounts are archived</h2>
          <p>
            Your transaction history is still available. Restore an account or create one to add a
            transaction.
          </p>
          <button className="secondary-button" type="button" onClick={() => changeView("Accounts")}>
            Manage accounts
          </button>
        </section>
      ) : null}

      {view === "Accounts" && resourcesReady ? (
        <AccountManager
          accounts={accounts}
          onCreate={saveAccount}
          onUpdate={changeAccount}
          onDelete={removeAccount}
        />
      ) : view === "Categories" && resourcesReady ? (
        <CategoryManager
          categories={categories}
          onCreate={saveCategory}
          onUpdate={changeCategory}
          onDelete={removeCategory}
        />
      ) : view !== "Transactions" && !resourceError ? (
        <p className="loading-state">Loading your workspace…</p>
      ) : null}

      {view === "Transactions" ? (
        <>
          <section className="summary-grid" aria-label="Ledger summary">
            <article>
              <span>Matching entries</span>
              <strong>{ledger?.count ?? "—"}</strong>
              <small>Across the current filters</small>
            </article>
            <article>
              <span>Active accounts</span>
              <strong>{resourcesReady ? activeAccounts.length : "—"}</strong>
              <small>Available for new transactions</small>
            </article>
            <article>
              <span>Active categories</span>
              <strong>{resourcesReady ? activeCategories.length : "—"}</strong>
              <small>Expense, income, and transfer labels</small>
            </article>
          </section>

          {editor ? (
            <TransactionForm
              key={editor === "new" ? "new" : editor.id}
              accounts={accounts}
              categories={categories}
              transaction={editor === "new" ? undefined : editor}
              onCancel={() => setEditor(null)}
              onSubmit={submitTransaction}
            />
          ) : null}

          {deleteTarget ? (
            <section className="confirm-panel" aria-label="Delete transaction">
              <h2>Delete transaction?</h2>
              <p>
                Delete “{deleteTarget.description}”? This removes the entry from your ledger
                permanently.
              </p>
              {deleteError ? (
                <p className="form-error" role="alert">
                  {deleteError}
                </p>
              ) : null}
              <div className="form-actions">
                <button
                  className="text-button"
                  type="button"
                  disabled={mutationBusy}
                  onClick={() => {
                    setDeleteTarget(null);
                    setDeleteError(null);
                  }}
                >
                  Cancel
                </button>
                <button
                  className="danger-button"
                  type="button"
                  disabled={mutationBusy}
                  onClick={() => void confirmDelete()}
                >
                  {mutationBusy ? "Deleting…" : "Confirm delete"}
                </button>
              </div>
            </section>
          ) : null}

          <section
            className="ledger-card"
            aria-labelledby="ledger-heading"
            aria-busy={ledgerLoading}
          >
            <div className="ledger-heading">
              <div>
                <p className="card-kicker">Newest first</p>
                <h2 id="ledger-heading">Transaction ledger</h2>
              </div>
              <span>{ledger?.count ?? 0} {ledger?.count === 1 ? "result" : "results"}</span>
            </div>
            <TransactionFilters
              accounts={accounts}
              categories={categories}
              value={draftFilters}
              error={filterError}
              onChange={setDraftFilters}
              onApply={applyFilters}
              onReset={resetFilters}
            />
            {ledgerError ? (
              <div className="error-banner" role="alert">
                <strong>Unable to load transactions.</strong>
                <span>{ledgerError}</span>
                <button
                  className="text-button"
                  type="button"
                  onClick={() => setRefresh((current) => current + 1)}
                >
                  Retry
                </button>
              </div>
            ) : null}
            {ledgerLoading && !ledger ? (
              <div className="loading-state" aria-live="polite">
                Loading transactions…
              </div>
            ) : (
              <TransactionTable
                transactions={ledger?.results ?? []}
                disabled={mutationBusy || ledgerLoading || !resourcesReady || Boolean(editor)}
                onEdit={(transaction) => {
                  setEditor(transaction);
                  setDeleteTarget(null);
                  setAnnouncement("");
                }}
                onDelete={(transaction) => {
                  setDeleteTarget(transaction);
                  setDeleteError(null);
                  setEditor(null);
                  setAnnouncement("");
                }}
              />
            )}
            {ledger ? (
              <div className="pagination" aria-label="Transaction pages">
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!ledger.previous || ledgerLoading || mutationBusy}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                >
                  Previous
                </button>
                <span>Page {page}</span>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={!ledger.next || ledgerLoading || mutationBusy}
                  onClick={() => setPage((current) => current + 1)}
                >
                  Next
                </button>
              </div>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  );
}
