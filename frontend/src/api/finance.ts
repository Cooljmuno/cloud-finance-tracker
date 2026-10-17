import { requestJson, type AuthTransport } from "./client";
import type {
  Category,
  CreateTransaction,
  FinanceTransaction,
  FinancialAccount,
  Paginated,
  TransactionFilters,
} from "./types";

async function fetchAll<T>(path: string, transport: AuthTransport, signal?: AbortSignal) {
  const results: T[] = [];
  let next: string | null = path;

  while (next) {
    const page: Paginated<T> = await requestJson(next, { signal }, transport);
    results.push(...page.results);
    next = page.next;
  }
  return results;
}

export function getAccounts(transport: AuthTransport, signal?: AbortSignal) {
  return fetchAll<FinancialAccount>("accounts/", transport, signal);
}

export function getCategories(transport: AuthTransport, signal?: AbortSignal) {
  return fetchAll<Category>("categories/", transport, signal);
}

export function getTransactions(
  transport: AuthTransport,
  filters: TransactionFilters,
  page: number,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams();
  if (filters.account) query.set("account", filters.account);
  if (filters.category) query.set("category", filters.category);
  if (filters.status) query.set("status", filters.status);
  if (filters.dateFrom) query.set("date_from", filters.dateFrom);
  if (filters.dateTo) query.set("date_to", filters.dateTo);
  if (page > 1) query.set("page", String(page));
  const suffix = query.size ? `?${query.toString()}` : "";

  return requestJson<Paginated<FinanceTransaction>>(
    `transactions/${suffix}`,
    { signal },
    transport,
  );
}

export function createTransaction(transport: AuthTransport, payload: CreateTransaction) {
  return requestJson<FinanceTransaction>(
    "transactions/",
    { method: "POST", body: JSON.stringify(payload) },
    transport,
  );
}
