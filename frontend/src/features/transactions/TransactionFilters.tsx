import type { FormEvent } from "react";

import type { Category, FinancialAccount, TransactionFilters as Filters } from "../../api/types";

type Props = {
  accounts: FinancialAccount[];
  categories: Category[];
  value: Filters;
  error: string | null;
  onChange: (filters: Filters) => void;
  onApply: () => void;
  onReset: () => void;
};

export function TransactionFilters({
  accounts,
  categories,
  value,
  error,
  onChange,
  onApply,
  onReset,
}: Props) {
  function setField<Key extends keyof Filters>(field: Key, nextValue: Filters[Key]) {
    onChange({ ...value, [field]: nextValue });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onApply();
  }

  return (
    <form className="filters" onSubmit={submit} aria-label="Transaction filters">
      <div className="filter-grid">
        <label>
          Account
          <select value={value.account} onChange={(event) => setField("account", event.target.value)}>
            <option value="">All accounts</option>
            {accounts.map((account) => (
              <option key={account.id} value={account.id}>
                {account.name}{account.is_active ? "" : " (archived)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Category
          <select value={value.category} onChange={(event) => setField("category", event.target.value)}>
            <option value="">All categories</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}{category.is_active ? "" : " (archived)"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={value.status}
            onChange={(event) => setField("status", event.target.value as Filters["status"])}
          >
            <option value="">Any status</option>
            <option value="posted">Posted</option>
            <option value="pending">Pending</option>
          </select>
        </label>
        <label>
          From
          <input
            type="date"
            value={value.dateFrom}
            onChange={(event) => setField("dateFrom", event.target.value)}
          />
        </label>
        <label>
          To
          <input
            type="date"
            value={value.dateTo}
            onChange={(event) => setField("dateTo", event.target.value)}
          />
        </label>
      </div>
      <div className="filter-actions">
        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : (
          <span />
        )}
        <button className="text-button" type="button" onClick={onReset}>
          Clear
        </button>
        <button className="secondary-button" type="submit">
          Apply filters
        </button>
      </div>
    </form>
  );
}
