import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, fieldErrors } from "../../api/client";
import type { AccountInput, FinancialAccount } from "../../api/types";
import { formatMoney } from "../../shared/format";

type Props = {
  accounts: FinancialAccount[];
  onCreate: (payload: AccountInput) => Promise<void>;
  onUpdate: (id: string, payload: Partial<AccountInput & { is_active: boolean }>) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
};

type Editor = { id: string | null; currency: string; values: AccountInput };

const accountTypes: { value: FinancialAccount["account_type"]; label: string }[] = [
  { value: "checking", label: "Checking" },
  { value: "savings", label: "Savings" },
  { value: "credit_card", label: "Credit card" },
  { value: "cash", label: "Cash" },
  { value: "investment", label: "Investment" },
  { value: "loan", label: "Loan" },
  { value: "other", label: "Other" },
];

function newEditor(): Editor {
  return {
    id: null,
    currency: "USD",
    values: { name: "", account_type: "checking", institution: "", opening_balance: "0.00" },
  };
}

export function AccountManager({ accounts, onCreate, onUpdate, onDelete }: Props) {
  const [editor, setEditor] = useState<Editor | null>(() =>
    accounts.length === 0 ? newEditor() : null,
  );
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  const editorOpen = editor !== null;
  const editingId = editor?.id;

  useEffect(() => {
    if (editorOpen) formRef.current?.focus();
  }, [editorOpen, editingId]);

  useEffect(() => {
    if (accounts.length === 0) {
      setEditor((current) => (current && !current.id ? current : newEditor()));
    }
  }, [accounts.length]);

  function openEditor(account?: FinancialAccount) {
    if (busy) return;
    setEditor(
      account
        ? {
            id: account.id,
            currency: account.currency,
            values: {
              name: account.name,
              account_type: account.account_type,
              institution: account.institution,
              opening_balance: account.opening_balance,
            },
          }
        : newEditor(),
    );
    setDeletingId(null);
    setErrors({});
    setError(null);
  }

  function changeField<Key extends keyof AccountInput>(field: Key, value: AccountInput[Key]) {
    setEditor((current) =>
      current
        ? {
            ...current,
            values: { ...current.values, [field]: value },
          }
        : current,
    );
    setErrors((current) => ({ ...current, [field]: "" }));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editor || busy) return;
    const payload = {
      ...editor.values,
      name: editor.values.name.trim(),
      institution: editor.values.institution.trim(),
      opening_balance: editor.values.opening_balance.trim(),
    };
    const nextErrors: Record<string, string> = {};
    if (!payload.name) nextErrors.name = "Enter an account name.";
    if (!/^-?(?:0|[1-9]\d{0,11})(?:\.\d{1,2})?$/.test(payload.opening_balance)) {
      nextErrors.opening_balance =
        "Use an amount with up to 12 whole-number digits and two decimal places.";
    }
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) {
      setError("Review the highlighted fields.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (editor.id) {
        await onUpdate(editor.id, payload);
      } else {
        await onCreate(payload);
      }
      setEditor(null);
    } catch (requestError: unknown) {
      const backendErrors = fieldErrors(requestError);
      setErrors(backendErrors);
      const hasFieldError = ["name", "account_type", "institution", "opening_balance"].some(
        (field) => Boolean(backendErrors[field]),
      );
      setError(
        hasFieldError
          ? "Review the highlighted fields."
          : (backendErrors.non_field_errors ??
              (requestError instanceof Error ? requestError.message : "Unable to save account.")),
      );
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(account: FinancialAccount) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setDeletingId(null);
    try {
      await onUpdate(account.id, { is_active: !account.is_active });
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Unable to update account.");
    } finally {
      setBusy(false);
    }
  }

  async function deleteAccount(account: FinancialAccount) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await onDelete(account.id);
      setDeletingId(null);
      setEditor((current) => (current?.id === account.id ? null : current));
    } catch (requestError: unknown) {
      setError(
        requestError instanceof ApiError && requestError.status === 409
          ? `${requestError.message} ${account.is_active ? "Archive this account" : "Keep this account archived"} to preserve its transaction history.`
          : requestError instanceof Error
            ? requestError.message
            : "Unable to delete account.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="transaction-panel"
      aria-labelledby="account-manager-heading"
      aria-busy={busy}
    >
      <div className="panel-heading">
        <div>
          <p className="card-kicker">Financial accounts</p>
          <h2 id="account-manager-heading">Accounts</h2>
        </div>
        <button
          className="primary-button"
          type="button"
          onClick={() => openEditor()}
          disabled={busy}
        >
          Add account
        </button>
      </div>

      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}

      {editor ? (
        <form ref={formRef} tabIndex={-1} onSubmit={save} aria-labelledby="account-form-heading">
          <h3 id="account-form-heading">{editor.id ? "Edit account" : "Add account"}</h3>
          <div className="form-grid">
            <label>
              Account name
              <input
                aria-label="Account name"
                value={editor.values.name}
                onChange={(event) => changeField("name", event.target.value)}
                maxLength={100}
                disabled={busy}
                aria-invalid={Boolean(errors.name)}
                aria-describedby={errors.name ? "account-name-error" : undefined}
              />
              {errors.name ? (
                <span className="field-error" id="account-name-error">
                  {errors.name}
                </span>
              ) : null}
            </label>
            <label>
              Account type
              <select
                aria-label="Account type"
                value={editor.values.account_type}
                onChange={(event) =>
                  changeField(
                    "account_type",
                    event.target.value as FinancialAccount["account_type"],
                  )
                }
                disabled={busy}
                aria-invalid={Boolean(errors.account_type)}
                aria-describedby={errors.account_type ? "account-type-error" : undefined}
              >
                {accountTypes.map((type) => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
              {errors.account_type ? (
                <span className="field-error" id="account-type-error">
                  {errors.account_type}
                </span>
              ) : null}
            </label>
            <label>
              Institution
              <input
                aria-label="Institution"
                value={editor.values.institution}
                onChange={(event) => changeField("institution", event.target.value)}
                maxLength={100}
                disabled={busy}
                aria-invalid={Boolean(errors.institution)}
                aria-describedby={errors.institution ? "account-institution-error" : undefined}
              />
              {errors.institution ? (
                <span className="field-error" id="account-institution-error">
                  {errors.institution}
                </span>
              ) : null}
            </label>
            <label>
              Opening balance
              <input
                aria-label="Opening balance"
                type="text"
                inputMode="decimal"
                value={editor.values.opening_balance}
                onChange={(event) => changeField("opening_balance", event.target.value)}
                disabled={busy}
                aria-invalid={Boolean(errors.opening_balance)}
                aria-describedby={errors.opening_balance ? "account-balance-error" : undefined}
              />
              {errors.opening_balance ? (
                <span className="field-error" id="account-balance-error">
                  {errors.opening_balance}
                </span>
              ) : null}
            </label>
            <label>
              Currency
              <input value={editor.currency} readOnly disabled={busy} />
            </label>
          </div>
          <div className="form-actions">
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setEditor(null);
                setErrors({});
                setError(null);
              }}
              disabled={busy}
            >
              Cancel
            </button>
            <button className="primary-button" type="submit" disabled={busy}>
              {busy ? "Saving…" : editor.id ? "Save account" : "Create account"}
            </button>
          </div>
        </form>
      ) : null}

      {accounts.length === 0 ? (
        <p className="notice">
          Create your first account to start recording transactions. New accounts use USD.
        </p>
      ) : (
        <div className="resource-grid">
          {accounts.map((account) => (
            <article className="resource-card" key={account.id}>
              <h3>{account.name}</h3>
              <p className="resource-meta">
                {accountTypes.find((type) => type.value === account.account_type)?.label} ·{" "}
                {account.currency} · {account.is_active ? "Active" : "Archived"}
              </p>
              {account.institution ? <p className="resource-meta">{account.institution}</p> : null}
              <p className="resource-meta">
                Opening balance: {formatMoney(account.opening_balance, account.currency)}
              </p>
              <div className="resource-actions">
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`Edit account ${account.name}`}
                  onClick={() => openEditor(account)}
                  disabled={busy}
                >
                  Edit
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`${account.is_active ? "Archive" : "Restore"} account ${account.name}`}
                  onClick={() => void toggleActive(account)}
                  disabled={busy}
                >
                  {account.is_active ? "Archive" : "Restore"}
                </button>
                <button
                  className="danger-button"
                  type="button"
                  aria-label={`Delete account ${account.name}`}
                  onClick={() => {
                    setDeletingId(account.id);
                    setError(null);
                  }}
                  disabled={busy}
                >
                  Delete
                </button>
              </div>
              {deletingId === account.id ? (
                <div
                  className="confirm-panel"
                  role="group"
                  aria-label={`Confirm deletion of account ${account.name}`}
                >
                  <p>
                    Delete {account.name}? Only accounts without transactions can be deleted.
                    Archive an account to preserve its history.
                  </p>
                  <div className="resource-actions">
                    <button
                      className="danger-button"
                      type="button"
                      onClick={() => void deleteAccount(account)}
                      disabled={busy}
                    >
                      Confirm delete
                    </button>
                    <button
                      className="text-button"
                      type="button"
                      onClick={() => {
                        setDeletingId(null);
                        setError(null);
                      }}
                      disabled={busy}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : null}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
