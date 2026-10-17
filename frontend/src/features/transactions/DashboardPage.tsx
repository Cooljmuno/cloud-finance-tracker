import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../../api/client";
import {
  createTransaction,
  getAccounts,
  getCategories,
  getTransactions,
} from "../../api/finance";
import type {
  Category,
  CreateTransaction,
  FinanceTransaction,
  FinancialAccount,
  Paginated,
  TransactionFilters as Filters,
} from "../../api/types";
import { useAppAuth } from "../../auth/AuthContext";
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

export function DashboardPage() {
  const { user, transport, mode, signOut, invalidate } = useAppAuth();
  const [accounts, setAccounts] = useState<FinancialAccount[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [resourcesLoading, setResourcesLoading] = useState(true);
  const [ledger, setLedger] = useState<Paginated<FinanceTransaction> | null>(null);
  const [ledgerLoading, setLedgerLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [draftFilters, setDraftFilters] = useState<Filters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(emptyFilters);
  const [filterError, setFilterError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [refresh, setRefresh] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [signingOut, setSigningOut] = useState(false);

  useEffect(() => {
    if (!transport) return;
    const controller = new AbortController();
    setResourcesLoading(true);

    Promise.all([
      getAccounts(transport, controller.signal),
      getCategories(transport, controller.signal),
    ])
      .then(([accountResults, categoryResults]) => {
        setAccounts(accountResults);
        setCategories(categoryResults);
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          void invalidate();
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Unable to load resources.");
      })
      .finally(() => setResourcesLoading(false));

    return () => controller.abort();
  }, [invalidate, refresh, transport]);

  useEffect(() => {
    if (!transport) return;
    const controller = new AbortController();
    setLedgerLoading(true);
    setError(null);

    getTransactions(transport, appliedFilters, page, controller.signal)
      .then(setLedger)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          void invalidate();
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Unable to load transactions.");
      })
      .finally(() => setLedgerLoading(false));

    return () => controller.abort();
  }, [appliedFilters, invalidate, page, refresh, transport]);

  const activeAccounts = useMemo(() => accounts.filter((account) => account.is_active), [accounts]);
  const activeCategories = useMemo(
    () => categories.filter((category) => category.is_active),
    [categories],
  );

  function applyFilters() {
    if (draftFilters.dateFrom && draftFilters.dateTo && draftFilters.dateFrom > draftFilters.dateTo) {
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

  async function submitTransaction(payload: CreateTransaction) {
    if (!transport) return;
    try {
      await createTransaction(transport, payload);
      setShowForm(false);
      setPage(1);
      setRefresh((current) => current + 1);
      setAnnouncement("Transaction created successfully.");
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        await invalidate();
      }
      throw requestError;
    }
  }

  async function handleSignOut() {
    setSigningOut(true);
    setError(null);
    try {
      await signOut();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Unable to sign out.");
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
          <button className="text-button" type="button" onClick={handleSignOut} disabled={signingOut}>
            {signingOut ? "Signing out…" : "Sign out"}
          </button>
        </div>
      </header>

      <section className="dashboard-intro">
        <div>
          <p className="eyebrow">Transaction workspace</p>
          <h1>Know where the money moves.</h1>
          <p>Review, filter, and add validated ledger entries without exposing real financial data.</p>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => setShowForm(true)}
          disabled={resourcesLoading || activeAccounts.length === 0}
        >
          <span aria-hidden="true">＋</span> Add transaction
        </button>
      </section>

      {activeAccounts.length === 0 && !resourcesLoading ? (
        <p className="notice" role="status">
          {mode === "session"
            ? "No active account is available. Run the documented demo-data command before creating a transaction."
            : "Your workspace has no active account. Account onboarding will be enabled before the AWS deployment."}
        </p>
      ) : null}

      <section className="summary-grid" aria-label="Ledger summary">
        <article>
          <span>Matching entries</span>
          <strong>{ledger?.count ?? "—"}</strong>
          <small>Across the current server-side filters</small>
        </article>
        <article>
          <span>Active accounts</span>
          <strong>{resourcesLoading ? "—" : activeAccounts.length}</strong>
          <small>Available for new transactions</small>
        </article>
        <article>
          <span>Active categories</span>
          <strong>{resourcesLoading ? "—" : activeCategories.length}</strong>
          <small>Expense, income, and transfer labels</small>
        </article>
      </section>

      {showForm ? (
        <TransactionForm
          accounts={activeAccounts}
          categories={activeCategories}
          onCancel={() => setShowForm(false)}
          onSubmit={submitTransaction}
        />
      ) : null}

      <section className="ledger-card" aria-labelledby="ledger-heading">
        <div className="ledger-heading">
          <div>
            <p className="card-kicker">Newest first</p>
            <h2 id="ledger-heading">Transaction ledger</h2>
          </div>
          <span>{ledger?.count ?? 0} results</span>
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

        {error ? (
          <div className="error-banner" role="alert">
            <strong>Something went wrong.</strong>
            <span>{error}</span>
            <button className="text-button" type="button" onClick={() => setRefresh((value) => value + 1)}>
              Retry
            </button>
          </div>
        ) : null}

        {ledgerLoading && !ledger ? (
          <div className="loading-state" aria-live="polite">
            Loading transactions…
          </div>
        ) : (
          <TransactionTable transactions={ledger?.results ?? []} />
        )}

        {ledger ? (
          <div className="pagination" aria-label="Transaction pages">
            <button
              className="secondary-button"
              type="button"
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={!ledger.previous || ledgerLoading}
            >
              Previous
            </button>
            <span>Page {page}</span>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setPage((current) => current + 1)}
              disabled={!ledger.next || ledgerLoading}
            >
              Next
            </button>
          </div>
        ) : null}
      </section>

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </main>
  );
}
