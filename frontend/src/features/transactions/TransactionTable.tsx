import type { FinanceTransaction } from "../../api/types";
import { formatDate, formatMoney } from "../../shared/format";

type Props = {
  transactions: FinanceTransaction[];
  onEdit: (transaction: FinanceTransaction) => void;
  onDelete: (transaction: FinanceTransaction) => void;
  disabled?: boolean;
};

export function TransactionTable({ transactions, onEdit, onDelete, disabled }: Props) {
  if (transactions.length === 0) {
    return (
      <div className="empty-state">
        <span aria-hidden="true">◎</span>
        <h3>No matching transactions</h3>
        <p>Adjust the filters or add a new synthetic transaction.</p>
      </div>
    );
  }

  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Description</th>
            <th scope="col">Account</th>
            <th scope="col">Category</th>
            <th scope="col">Status</th>
            <th scope="col" className="amount-column">
              Amount
            </th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((transaction) => {
            const isInflow = !transaction.amount.startsWith("-");
            return (
              <tr key={transaction.id}>
                <td className="date-cell">{formatDate(transaction.transaction_date)}</td>
                <td>
                  <strong>{transaction.description}</strong>
                  {transaction.notes ? <span className="row-note">{transaction.notes}</span> : null}
                </td>
                <td>{transaction.account_name}</td>
                <td>{transaction.category_name ?? "Uncategorized"}</td>
                <td>
                  <span className={`status-pill status-pill--${transaction.status}`}>
                    {transaction.status}
                  </span>
                </td>
                <td className={`amount-column amount-${isInflow ? "positive" : "negative"}`}>
                  {formatMoney(transaction.amount, transaction.currency)}
                </td>
                <td>
                  <div className="row-actions">
                    <button
                      className="text-button"
                      type="button"
                      disabled={disabled}
                      aria-label={`Edit transaction ${transaction.description}`}
                      onClick={() => onEdit(transaction)}
                    >
                      Edit
                    </button>
                    <button
                      className="text-button danger-text"
                      type="button"
                      disabled={disabled}
                      aria-label={`Delete transaction ${transaction.description}`}
                      onClick={() => onDelete(transaction)}
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
