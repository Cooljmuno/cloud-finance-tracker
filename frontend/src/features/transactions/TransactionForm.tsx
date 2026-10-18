import { useEffect, useRef, useState, type FormEvent } from "react";

import { fieldErrors } from "../../api/client";
import type {
  Category,
  CreateTransaction,
  FinanceTransaction,
  FinancialAccount,
} from "../../api/types";
import { localToday } from "../../shared/format";

type Props = {
  accounts: FinancialAccount[];
  categories: Category[];
  transaction?: FinanceTransaction;
  onCancel: () => void;
  onSubmit: (payload: CreateTransaction) => Promise<void>;
};

export function TransactionForm({ accounts, categories, transaction, onCancel, onSubmit }: Props) {
  const panel = useRef<HTMLElement>(null);
  const availableAccounts = accounts.filter(
    (account) => account.is_active || account.id === transaction?.account,
  );
  const availableCategories = categories.filter(
    (category) => category.is_active || category.id === transaction?.category,
  );
  const initialCategory =
    !transaction || transaction.category_source !== "manual"
      ? "__automatic"
      : (transaction.category ?? "");
  const [values, setValues] = useState({
    account: transaction?.account ?? availableAccounts[0]?.id ?? "",
    category: initialCategory,
    transaction_date: transaction?.transaction_date ?? localToday(),
    description: transaction?.description ?? "",
    amount: transaction?.amount ?? "",
    status: transaction?.status ?? ("posted" as "posted" | "pending"),
    notes: transaction?.notes ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    panel.current?.focus();
  }, []);

  function setField(field: keyof typeof values, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
    setErrors((current) => ({ ...current, [field]: "" }));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors: Record<string, string> = {};
    const amountPattern = /^-?(?:0|[1-9]\d*)(?:\.\d{1,2})?$/;
    if (!values.account) nextErrors.account = "Choose an active account.";
    if (!values.description.trim()) nextErrors.description = "Enter a description.";
    if (!amountPattern.test(values.amount) || Number(values.amount) === 0) {
      nextErrors.amount = "Use a nonzero signed amount with up to two decimal places.";
    }
    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    setSubmitting(true);
    setFormError(null);
    try {
      const { category: selectedCategory, ...entry } = values;
      const categoryChoice: Pick<CreateTransaction, "category" | "category_mode"> =
        transaction && selectedCategory === initialCategory
          ? {}
          : selectedCategory === "__automatic"
            ? { category: null, category_mode: "automatic" }
            : { category: selectedCategory || null, category_mode: "manual" };
      await onSubmit({
        ...entry,
        ...categoryChoice,
        description: values.description.trim(),
        notes: values.notes.trim(),
      });
    } catch (error: unknown) {
      const backendErrors = Object.fromEntries(
        Object.entries(fieldErrors(error)).filter(([field]) => field in values),
      );
      setErrors(backendErrors);
      setFormError(
        Object.keys(backendErrors).length > 0
          ? "Review the highlighted fields."
          : error instanceof Error
            ? error.message
            : "Unable to save transaction.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section
      ref={panel}
      tabIndex={-1}
      className="transaction-panel"
      aria-labelledby="transaction-form-heading"
    >
      <div className="panel-heading">
        <div>
          <p className="card-kicker">{transaction ? "Update ledger entry" : "New ledger entry"}</p>
          <h2 id="transaction-form-heading">
            {transaction ? "Edit transaction" : "Add transaction"}
          </h2>
        </div>
        <button
          className="icon-button"
          type="button"
          onClick={onCancel}
          aria-label="Close form"
          disabled={submitting}
        >
          ×
        </button>
      </div>
      <form onSubmit={submit}>
        <fieldset disabled={submitting}>
          <div className="form-grid">
            <label>
              Account
              <select
                value={values.account}
                onChange={(event) => setField("account", event.target.value)}
              >
                {availableAccounts.map((account) => (
                  <option value={account.id} key={account.id}>
                    {account.name}
                    {account.is_active ? "" : " (archived)"}
                  </option>
                ))}
              </select>
              {errors.account ? <span className="field-error">{errors.account}</span> : null}
            </label>
            <label>
              Category <span className="optional">Optional</span>
              <select
                value={values.category}
                onChange={(event) => setField("category", event.target.value)}
              >
                <option value="__automatic">Automatic rules</option>
                <option value="">Uncategorized</option>
                {availableCategories.map((category) => (
                  <option value={category.id} key={category.id}>
                    {category.name}
                    {category.is_active ? "" : " (archived)"}
                  </option>
                ))}
              </select>
              <span className="field-hint">
                Automatic uses the first matching enabled rule. Choosing a category or Uncategorized
                keeps your manual choice.
              </span>
              {errors.category ? <span className="field-error">{errors.category}</span> : null}
            </label>
            <label>
              Date
              <input
                type="date"
                value={values.transaction_date}
                onChange={(event) => setField("transaction_date", event.target.value)}
                required
              />
              {errors.transaction_date ? (
                <span className="field-error">{errors.transaction_date}</span>
              ) : null}
            </label>
            <label>
              Status
              <select
                value={values.status}
                onChange={(event) => setField("status", event.target.value)}
              >
                <option value="posted">Posted</option>
                <option value="pending">Pending</option>
              </select>
            </label>
            <label className="wide-field">
              Description
              <input
                value={values.description}
                onChange={(event) => setField("description", event.target.value)}
                maxLength={255}
                placeholder="e.g. Juniper Market"
              />
              {errors.description ? (
                <span className="field-error">{errors.description}</span>
              ) : null}
            </label>
            <label>
              Amount
              <input
                type="text"
                inputMode="decimal"
                value={values.amount}
                onChange={(event) => setField("amount", event.target.value)}
                placeholder="-42.18"
              />
              <span className="field-hint">Negative is spending; positive is income.</span>
              {errors.amount ? <span className="field-error">{errors.amount}</span> : null}
            </label>
            <label className="wide-field">
              Notes <span className="optional">Optional</span>
              <textarea
                value={values.notes}
                onChange={(event) => setField("notes", event.target.value)}
                maxLength={1000}
                rows={3}
              />
              {errors.notes ? <span className="field-error">{errors.notes}</span> : null}
            </label>
          </div>
          {formError ? (
            <p className="form-error" role="alert">
              {formError}
            </p>
          ) : null}
          <div className="form-actions">
            <button className="text-button" type="button" onClick={onCancel}>
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={submitting}>
              {submitting ? "Saving…" : transaction ? "Save changes" : "Save transaction"}
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  );
}
