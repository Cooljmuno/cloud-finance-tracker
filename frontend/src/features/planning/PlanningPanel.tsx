import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, fieldErrors } from "../../api/client";
import {
  createBudget,
  deleteBudget,
  getBudgets,
  getMonthlyReport,
  updateBudget,
} from "../../api/planning";
import type {
  BudgetInput,
  Category,
  FinancialAccount,
  MonthlyBudget,
  MonthlyReport,
} from "../../api/types";
import { useAppAuth } from "../../auth/AuthContext";
import { formatMoney, localToday } from "../../shared/format";

type Props = {
  accounts: FinancialAccount[];
  categories: Category[];
  onChanged: (message: string) => void;
  onBusyChange: (busy: boolean) => void;
};

type LoadState<T> = { key: string; data: T | null; error: string | null; loading: boolean };
type BudgetEditor = { id: string | null; category: string; amount: string };

function monthLabel(month: string) {
  const [year, number] = month.split("-").map(Number);
  const date = new Date(0);
  date.setUTCFullYear(year, number - 1, 1);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

function signedBar(amount: string, maximum: number) {
  const value = Number(amount);
  const width = maximum > 0 ? (Math.abs(value) / maximum) * 50 : 0;
  return {
    width: `${Math.min(50, width)}%`,
    left: "50%",
    transform: value < 0 ? "translateX(-100%)" : undefined,
  };
}

function SpendingCharts({ report }: { report: MonthlyReport }) {
  const categoryMaximum = Math.max(
    ...report.categories.map((row) => Math.abs(Number(row.spending))),
    0,
  );
  const trendMaximum = Math.max(
    ...report.trend.flatMap((row) => [
      Math.abs(Number(row.income)),
      Math.abs(Number(row.spending)),
    ]),
    0,
  );

  return (
    <div className="planning-grid">
      <section className="planning-card" aria-labelledby="category-spending-heading">
        <h3 id="category-spending-heading">Category spending</h3>
        <p className="planning-note">Posted expenses, with refunds deducted.</p>
        {report.categories.length === 0 ? (
          <p className="empty-state">No spending or budgets for this month and currency.</p>
        ) : (
          <>
            <div
              className="spending-chart"
              role="img"
              aria-label={`Category spending for ${monthLabel(report.month)} in ${report.currency}. Bars left of zero show net refunds.`}
            >
              {report.categories.map((row) => (
                <div className="spending-chart-row" key={row.category ?? "uncategorized"}>
                  <div className="spending-chart-label">
                    <span>{row.category_name}</span>
                    <strong>{formatMoney(row.spending, report.currency)}</strong>
                  </div>
                  <div className="spending-chart-track" aria-hidden="true">
                    <span
                      className={`spending-chart-fill${Number(row.spending) < 0 ? " is-refund" : ""}`}
                      style={signedBar(row.spending, categoryMaximum)}
                    />
                  </div>
                </div>
              ))}
            </div>
            <p className="planning-note">
              The center line is zero. Bars to the left show net refunds.
            </p>
            <details className="planning-values">
              <summary>View exact category amounts</summary>
              <div className="planning-table-wrap">
                <table>
                  <caption>Category amounts in {report.currency}</caption>
                  <thead>
                    <tr>
                      <th scope="col">Category</th>
                      <th scope="col">Spending</th>
                      <th scope="col">Budget</th>
                      <th scope="col">Remaining</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.categories.map((row) => (
                      <tr key={row.category ?? "uncategorized"}>
                        <th scope="row">{row.category_name}</th>
                        <td>{formatMoney(row.spending, report.currency)}</td>
                        <td>
                          {row.budget === null
                            ? "No budget"
                            : formatMoney(row.budget, report.currency)}
                        </td>
                        <td>
                          {row.remaining === null
                            ? "—"
                            : formatMoney(row.remaining, report.currency)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </details>
          </>
        )}
      </section>

      <section className="planning-card" aria-labelledby="spending-trend-heading">
        <h3 id="spending-trend-heading">Six-month trend</h3>
        <p className="planning-note">
          Income and spending in {report.currency}, through {monthLabel(report.month)}.
        </p>
        <div
          className="trend-chart"
          role="img"
          aria-label={`Six-month income and spending chart in ${report.currency}. Green represents income, brown represents spending. Negative adjustments extend left of zero.`}
        >
          {report.trend.map((row) => (
            <div className="trend-chart-month" key={row.month}>
              <strong>{monthLabel(row.month)}</strong>
              <div className="trend-chart-series">
                <div className="trend-chart-label">
                  <span>Income</span>
                  <span>{formatMoney(row.income, report.currency)}</span>
                </div>
                <div className="spending-chart-track" aria-hidden="true">
                  <span
                    className="spending-chart-fill trend-income"
                    style={signedBar(row.income, trendMaximum)}
                  />
                </div>
                <div className="trend-chart-label">
                  <span>Spending</span>
                  <span>{formatMoney(row.spending, report.currency)}</span>
                </div>
                <div className="spending-chart-track" aria-hidden="true">
                  <span
                    className="spending-chart-fill trend-spending"
                    style={signedBar(row.spending, trendMaximum)}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
        <details className="planning-values">
          <summary>View exact monthly amounts</summary>
          <div className="planning-table-wrap">
            <table>
              <caption>Monthly amounts in {report.currency}</caption>
              <thead>
                <tr>
                  <th scope="col">Month</th>
                  <th scope="col">Income</th>
                  <th scope="col">Spending</th>
                </tr>
              </thead>
              <tbody>
                {report.trend.map((row) => (
                  <tr key={row.month}>
                    <th scope="row">{monthLabel(row.month)}</th>
                    <td>{formatMoney(row.income, report.currency)}</td>
                    <td>{formatMoney(row.spending, report.currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </div>
  );
}

export function PlanningPanel({ accounts, categories, onChanged, onBusyChange }: Props) {
  const { transport, invalidate } = useAppAuth();
  const [month, setMonth] = useState(() => localToday().slice(0, 7));
  const [currency, setCurrency] = useState(() =>
    accounts.length === 0 || accounts.some((account) => account.currency === "USD")
      ? "USD"
      : accounts[0].currency,
  );
  const queryKey = `${month}/${currency}`;
  const [reportState, setReportState] = useState<LoadState<MonthlyReport>>({
    key: "",
    data: null,
    error: null,
    loading: true,
  });
  const [budgetsState, setBudgetsState] = useState<LoadState<MonthlyBudget[]>>({
    key: "",
    data: null,
    error: null,
    loading: true,
  });
  const [reportRefresh, setReportRefresh] = useState(0);
  const [budgetRefresh, setBudgetRefresh] = useState(0);
  const [editor, setEditor] = useState<BudgetEditor | null>(null);
  const [deleting, setDeleting] = useState<MonthlyBudget | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const editorOpen = editor !== null;
  const editingId = editor?.id;
  const inFlight = useRef(false);
  const mounted = useRef(true);
  const formRef = useRef<HTMLFormElement>(null);
  const reportRequest = useRef(0);
  const budgetRequest = useRef(0);
  const report = reportState.key === queryKey ? reportState.data : null;
  const reportError = reportState.key === queryKey ? reportState.error : null;
  const reportLoading = reportState.key !== queryKey || reportState.loading;
  const budgets = budgetsState.key === queryKey ? budgetsState.data : null;
  const budgetError = budgetsState.key === queryKey ? budgetsState.error : null;
  const budgetsLoading = budgetsState.key !== queryKey || budgetsState.loading;
  const activeExpenseCategories = categories.filter(
    (category) => category.kind === "expense" && category.is_active,
  );
  const formCategories = categories.filter(
    (category) =>
      category.kind === "expense" && (category.is_active || category.id === editor?.category),
  );
  const currencies = [
    ...new Set([
      "USD",
      ...accounts.map((account) => account.currency),
      ...(budgets ?? []).map((budget) => budget.currency),
      currency,
    ]),
  ].sort();
  const validMonth = /^\d{4}-(?:0[1-9]|1[0-2])$/.test(month) && month >= "0001-06";

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      inFlight.current = false;
      onBusyChange(false);
    };
  }, [onBusyChange]);

  useEffect(() => {
    if (!transport || !validMonth) {
      setReportState({
        key: queryKey,
        data: null,
        loading: false,
        error: validMonth
          ? "Your session has expired. Sign in again."
          : "Choose a month from June 0001 onward.",
      });
      return;
    }
    const controller = new AbortController();
    const generation = ++reportRequest.current;
    setReportState({ key: queryKey, data: null, error: null, loading: true });
    getMonthlyReport(transport, month, currency, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && reportRequest.current === generation) {
          setReportState({ key: queryKey, data, error: null, loading: false });
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || reportRequest.current !== generation) return;
        if (requestError instanceof ApiError && requestError.status === 401) void invalidate();
        setReportState({
          key: queryKey,
          data: null,
          loading: false,
          error:
            requestError instanceof Error
              ? requestError.message
              : "Unable to load monthly spending.",
        });
      });
    return () => controller.abort();
  }, [currency, invalidate, month, queryKey, reportRefresh, transport, validMonth]);

  useEffect(() => {
    if (!transport || !validMonth) {
      setBudgetsState({
        key: queryKey,
        data: null,
        loading: false,
        error: validMonth
          ? "Your session has expired. Sign in again."
          : "Choose a valid budget month.",
      });
      return;
    }
    const controller = new AbortController();
    const generation = ++budgetRequest.current;
    setBudgetsState({ key: queryKey, data: null, error: null, loading: true });
    getBudgets(transport, month, currency, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted && budgetRequest.current === generation) {
          setBudgetsState({ key: queryKey, data, error: null, loading: false });
        }
      })
      .catch((requestError: unknown) => {
        if (controller.signal.aborted || budgetRequest.current !== generation) return;
        if (requestError instanceof ApiError && requestError.status === 401) void invalidate();
        setBudgetsState({
          key: queryKey,
          data: null,
          loading: false,
          error: requestError instanceof Error ? requestError.message : "Unable to load budgets.",
        });
      });
    return () => controller.abort();
  }, [budgetRefresh, currency, invalidate, month, queryKey, transport, validMonth]);

  useEffect(() => {
    if (editorOpen) formRef.current?.focus();
  }, [editingId, editorOpen]);

  function clearEditor() {
    setEditor(null);
    setDeleting(null);
    setErrors({});
    setError(null);
  }

  function changeScope(nextMonth: string, nextCurrency: string) {
    if (inFlight.current) return;
    clearEditor();
    setMonth(nextMonth);
    setCurrency(nextCurrency);
  }

  function openEditor(budget?: MonthlyBudget) {
    if (inFlight.current) return;
    setEditor(
      budget
        ? { id: budget.id, category: budget.category, amount: budget.amount }
        : { id: null, category: activeExpenseCategories[0]?.id ?? "", amount: "" },
    );
    setDeleting(null);
    setErrors({});
    setError(null);
  }

  function beginMutation() {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    onBusyChange(true);
    setError(null);
    return true;
  }

  function finishMutation() {
    if (!mounted.current) return;
    inFlight.current = false;
    setBusy(false);
    onBusyChange(false);
  }

  function refreshData() {
    setReportRefresh((value) => value + 1);
    setBudgetRefresh((value) => value + 1);
  }

  async function saveBudget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || inFlight.current) return;
    if (!transport) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const nextErrors: Record<string, string> = {};
    const amount = editor.amount.trim();
    if (!formCategories.some((category) => category.id === editor.category))
      nextErrors.category = "Choose an expense category.";
    if (!/^(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(amount) || Number(amount) <= 0)
      nextErrors.amount =
        "Enter a positive amount with up to 12 whole-number digits and two decimal places.";
    if (!validMonth) nextErrors.month = "Choose a valid budget month.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Review the highlighted fields.");
      return;
    }
    if (!beginMutation()) return;
    const payload: BudgetInput = { category: editor.category, amount, month, currency };
    try {
      if (editor.id) await updateBudget(transport, editor.id, payload);
      else await createBudget(transport, payload);
      if (!mounted.current) return;
      setEditor(null);
      refreshData();
      onChanged(editor.id ? "Budget updated." : "Budget created.");
    } catch (requestError: unknown) {
      if (!mounted.current) return;
      if (requestError instanceof ApiError && requestError.status === 401) void invalidate();
      const nextErrors = fieldErrors(requestError);
      setErrors(nextErrors);
      setError(
        nextErrors.non_field_errors ??
          (["category", "amount", "month", "currency"].some((field) => Boolean(nextErrors[field]))
            ? "Review the highlighted fields."
            : requestError instanceof Error
              ? requestError.message
              : "Unable to save budget."),
      );
    } finally {
      finishMutation();
    }
  }

  async function removeBudget() {
    if (!deleting || !transport || !beginMutation()) return;
    try {
      await deleteBudget(transport, deleting.id);
      if (!mounted.current) return;
      setDeleting(null);
      refreshData();
      onChanged("Budget deleted.");
    } catch (requestError: unknown) {
      if (!mounted.current) return;
      if (requestError instanceof ApiError && requestError.status === 401) void invalidate();
      setError(requestError instanceof Error ? requestError.message : "Unable to delete budget.");
    } finally {
      finishMutation();
    }
  }

  return (
    <section
      className="transaction-panel planning-panel"
      aria-labelledby="planning-heading"
      aria-busy={busy}
    >
      <div className="panel-heading">
        <div>
          <p className="card-kicker">A monthly view</p>
          <h2 id="planning-heading">Monthly spending</h2>
        </div>
      </div>
      <div className="planning-filters form-grid">
        <label>
          Budget month
          <input
            type="month"
            aria-label="Budget month"
            min="0001-06"
            max="9999-12"
            value={month}
            onChange={(event) => changeScope(event.target.value, currency)}
            disabled={busy}
            aria-invalid={!validMonth}
          />
        </label>
        <label>
          Report currency
          <select
            aria-label="Report currency"
            value={currency}
            onChange={(event) => changeScope(month, event.target.value)}
            disabled={busy}
          >
            {currencies.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="planning-note">
        Currencies are shown separately. Posted transactions count toward totals; pending entries,
        transfers, and opening balances are excluded.
      </p>

      {reportLoading ? (
        <p className="empty-state">Loading monthly spending…</p>
      ) : reportError ? (
        <div className="error-banner" role="alert">
          <p>{reportError}</p>
          <button
            className="secondary-button"
            type="button"
            onClick={() => setReportRefresh((value) => value + 1)}
            disabled={busy || !validMonth}
          >
            Retry report
          </button>
        </div>
      ) : report ? (
        <>
          <dl className="planning-summary">
            <div className="planning-metric">
              <dt>Income</dt>
              <dd>{formatMoney(report.totals.income, currency)}</dd>
            </div>
            <div className="planning-metric">
              <dt>Spending</dt>
              <dd>{formatMoney(report.totals.spending, currency)}</dd>
            </div>
            <div className="planning-metric">
              <dt>Net</dt>
              <dd>{formatMoney(report.totals.net, currency)}</dd>
            </div>
          </dl>
          <p className="planning-note">
            {report.transaction_count} posted{" "}
            {report.transaction_count === 1 ? "transaction" : "transactions"}
            {report.pending_count ? ` · ${report.pending_count} pending excluded` : ""}.
            Uncategorized spending: {formatMoney(report.totals.uncategorized_spending, currency)}.
          </p>
          <SpendingCharts report={report} />
        </>
      ) : null}

      <section className="planning-budgets" aria-labelledby="budgets-heading">
        <div className="panel-heading">
          <div>
            <p className="card-kicker">Room to plan</p>
            <h3 id="budgets-heading">Monthly budgets</h3>
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => openEditor()}
            disabled={busy || budgetsLoading || !validMonth || activeExpenseCategories.length === 0}
          >
            Add budget
          </button>
        </div>
        <p className="planning-note">
          Set a spending limit for an expense category in{" "}
          {month ? monthLabel(validMonth ? month : localToday().slice(0, 7)) : "the selected month"}
          . Budgets use {currency} accounts only.
        </p>
        {activeExpenseCategories.length === 0 ? (
          <p className="empty-state">
            Create an expense category in Categories before adding a budget.
          </p>
        ) : null}
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        {editor ? (
          <form
            ref={formRef}
            tabIndex={-1}
            onSubmit={saveBudget}
            aria-labelledby="budget-form-heading"
          >
            <h4 id="budget-form-heading">{editor.id ? "Edit budget" : "New budget"}</h4>
            <div className="form-grid">
              <label>
                Budget category
                <select
                  aria-label="Budget category"
                  value={editor.category}
                  onChange={(event) => {
                    setEditor({ ...editor, category: event.target.value });
                    setErrors((current) => ({ ...current, category: "" }));
                  }}
                  disabled={busy}
                  aria-invalid={Boolean(errors.category)}
                  aria-describedby={errors.category ? "budget-category-error" : undefined}
                >
                  <option value="">Choose a category</option>
                  {formCategories.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                      {category.is_active ? "" : " (archived)"}
                    </option>
                  ))}
                </select>
                {errors.category ? (
                  <span className="field-error" id="budget-category-error">
                    {errors.category}
                  </span>
                ) : null}
              </label>
              <label>
                Budget amount
                <input
                  aria-label="Budget amount"
                  inputMode="decimal"
                  value={editor.amount}
                  onChange={(event) => {
                    setEditor({ ...editor, amount: event.target.value });
                    setErrors((current) => ({ ...current, amount: "" }));
                  }}
                  disabled={busy}
                  aria-invalid={Boolean(errors.amount)}
                  aria-describedby={errors.amount ? "budget-amount-error" : undefined}
                  placeholder="500.00"
                />
                {errors.amount ? (
                  <span className="field-error" id="budget-amount-error">
                    {errors.amount}
                  </span>
                ) : null}
              </label>
            </div>
            {errors.month || errors.currency ? (
              <p className="field-error">{errors.month ?? errors.currency}</p>
            ) : null}
            <div className="form-actions">
              <button className="primary-button" type="submit" disabled={busy}>
                {busy ? "Saving…" : editor.id ? "Save budget" : "Create budget"}
              </button>
              <button
                className="secondary-button"
                type="button"
                onClick={clearEditor}
                disabled={busy}
              >
                Cancel budget
              </button>
            </div>
          </form>
        ) : null}

        {budgetsLoading ? (
          <p className="empty-state">Loading budgets…</p>
        ) : budgetError ? (
          <div className="error-banner" role="alert">
            <p>{budgetError}</p>
            <button
              className="secondary-button"
              type="button"
              onClick={() => setBudgetRefresh((value) => value + 1)}
              disabled={busy || !validMonth}
            >
              Retry budgets
            </button>
          </div>
        ) : budgets?.length === 0 ? (
          <p className="empty-state">No budgets for this month and currency.</p>
        ) : budgets ? (
          <div className="budget-list">
            {budgets.map((budget) => {
              const usage = report?.categories.find((row) => row.budget_id === budget.id);
              const percentage = usage
                ? (Number(usage.spending) / Number(budget.amount)) * 100
                : null;
              const percentageLabel =
                percentage === null
                  ? null
                  : `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(percentage)}% used`;
              const overBudget =
                usage?.remaining !== null &&
                usage?.remaining !== undefined &&
                Number(usage.remaining) < 0;
              return (
                <article className="budget-item" key={budget.id}>
                  <div className="budget-item-heading">
                    <h4>{budget.category_name}</h4>
                    <strong>{formatMoney(budget.amount, budget.currency)}</strong>
                  </div>
                  <dl className="budget-detail">
                    <div>
                      <dt>Spent</dt>
                      <dd>
                        {usage
                          ? formatMoney(usage.spending, currency)
                          : reportLoading
                            ? "Loading…"
                            : "Unavailable"}
                      </dd>
                    </div>
                    <div>
                      <dt>Remaining</dt>
                      <dd className={overBudget ? "is-over-budget" : undefined}>
                        {usage?.remaining !== null && usage?.remaining !== undefined
                          ? formatMoney(usage.remaining, currency)
                          : reportLoading
                            ? "Loading…"
                            : "Unavailable"}
                      </dd>
                    </div>
                  </dl>
                  {percentage !== null ? (
                    <>
                      <div
                        className={`budget-progress${overBudget ? " is-over-budget" : ""}`}
                        aria-hidden="true"
                      >
                        <span style={{ width: `${Math.max(0, Math.min(100, percentage))}%` }} />
                      </div>
                      <p className="planning-note">
                        {percentageLabel}
                        {overBudget
                          ? " · Over budget"
                          : Number(usage?.spending) < 0
                            ? " · Refunds exceed spending"
                            : ""}
                      </p>
                    </>
                  ) : (
                    <p className="planning-note">
                      {reportLoading
                        ? "Spending totals are loading."
                        : "Spending totals are unavailable. Retry the report to see budget usage."}
                    </p>
                  )}
                  <div className="resource-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      aria-label={`Edit budget for ${budget.category_name}`}
                      onClick={() => openEditor(budget)}
                      disabled={busy}
                    >
                      Edit
                    </button>
                    <button
                      className="text-button danger-text"
                      type="button"
                      aria-label={`Delete budget for ${budget.category_name}`}
                      onClick={() => {
                        setDeleting(budget);
                        setEditor(null);
                        setErrors({});
                        setError(null);
                      }}
                      disabled={busy}
                    >
                      Delete
                    </button>
                  </div>
                  {deleting?.id === budget.id ? (
                    <div className="confirm-panel" aria-labelledby={`delete-budget-${budget.id}`}>
                      <h4 id={`delete-budget-${budget.id}`}>Delete this budget?</h4>
                      <p>
                        Remove the {budget.category_name} budget for {monthLabel(budget.month)}?
                        Your transactions will stay unchanged.
                      </p>
                      <div className="form-actions">
                        <button
                          className="danger-button"
                          type="button"
                          onClick={() => void removeBudget()}
                          disabled={busy}
                        >
                          Confirm delete budget
                        </button>
                        <button
                          className="secondary-button"
                          type="button"
                          onClick={() => {
                            setDeleting(null);
                            setError(null);
                          }}
                          disabled={busy}
                        >
                          Cancel delete budget
                        </button>
                      </div>
                    </div>
                  ) : null}
                </article>
              );
            })}
          </div>
        ) : null}
      </section>
    </section>
  );
}
