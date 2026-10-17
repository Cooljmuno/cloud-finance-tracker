import { useState, type FormEvent } from "react";

import { fieldErrors } from "../../api/client";
import type { Category, CreateTransaction, FinancialAccount } from "../../api/types";
import { localToday } from "../../shared/format";

type Props = {
  accounts: FinancialAccount[];
  categories: Category[];
  onCancel: () => void;
  onSubmit: (payload: CreateTransaction) => Promise<void>;
};

export function TransactionForm({ accounts, categories, onCancel, onSubmit }: Props) {
  const [values, setValues] = useState({
    account: accounts[0]?.id ?? "",
    category: "",
    transaction_date: localToday(),
    description: "",
    amount: "",
    status: "posted" as "posted" | "pending",
    notes: "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

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
      await onSubmit({
        ...values,
        description: values.description.trim(),
        category: values.category || null,
        notes: values.notes.trim(),
      });
    } catch (error: unknown) {
      const backendErrors = fieldErrors(error);
      setErrors(backendErrors);
      setFormError(
        Object.keys(backendErrors).length > 0
          ? "Review the highlighted fields."
          : error instanceof Error
            ? error.message
            : "Unable to create transaction.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="transaction-panel" aria-labelledby="transaction-form-heading">
      <div className="panel-heading">
        <div>
          <p className="card-kicker">New ledger entry</p>
          <h2 id="transaction-form-heading">Add transaction</h2>
        </div>
        <button className="icon-button" type="button" onClick={onCancel} aria-label="Close form">
          ×
        </button>
      </div>
      <form onSubmit={submit}>
        <div className="form-grid">
          <label>
            Account
            <select value={values.account} onChange={(event) => setField("account", event.target.value)}>
              {accounts.map((account) => (
                <option value={account.id} key={account.id}>
                  {account.name}
                </option>
              ))}
            </select>
            {errors.account ? <span className="field-error">{errors.account}</span> : null}
          </label>
          <label>
            Category <span className="optional">Optional</span>
            <select value={values.category} onChange={(event) => setField("category", event.target.value)}>
              <option value="">Uncategorized</option>
              {categories.map((category) => (
                <option value={category.id} key={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
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
            {errors.description ? <span className="field-error">{errors.description}</span> : null}
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
            {submitting ? "Saving…" : "Save transaction"}
          </button>
        </div>
      </form>
    </section>
  );
}
