import type { FinanceTransaction } from "../../api/types";
import { formatDate, formatMoney } from "../../shared/format";

export function TransactionTable({ transactions }: { transactions: FinanceTransaction[] }) {
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
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
