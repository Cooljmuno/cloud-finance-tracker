import { requestJson, type AuthTransport } from "./client";
import type {
  BudgetInput,
  CategorizationRule,
  MonthlyBudget,
  MonthlyReport,
  Paginated,
  RuleInput,
} from "./types";

async function allPages<T>(path: string, transport: AuthTransport, signal?: AbortSignal) {
  const results: T[] = [];
  let next: string | null = path;
  while (next) {
    const page: Paginated<T> = await requestJson(next, { signal }, transport);
    results.push(...page.results);
    next = page.next;
  }
  return results;
}

export function getRules(transport: AuthTransport, signal?: AbortSignal) {
  return allPages<CategorizationRule>("rules/", transport, signal);
}

export function createRule(transport: AuthTransport, payload: RuleInput) {
  return requestJson<CategorizationRule>(
    "rules/",
    { method: "POST", body: JSON.stringify(payload) },
    transport,
  );
}

export function updateRule(transport: AuthTransport, id: string, payload: Partial<RuleInput>) {
  return requestJson<CategorizationRule>(
    `rules/${id}/`,
    { method: "PATCH", body: JSON.stringify(payload) },
    transport,
  );
}

export function deleteRule(transport: AuthTransport, id: string) {
  return requestJson<void>(`rules/${id}/`, { method: "DELETE" }, transport);
}

export function applyRules(transport: AuthTransport) {
  return requestJson<{ updated: number; examined: number }>(
    "rules/apply/",
    { method: "POST" },
    transport,
  );
}

export function getBudgets(
  transport: AuthTransport,
  month: string,
  currency: string,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ month, currency });
  return allPages<MonthlyBudget>(`budgets/?${query.toString()}`, transport, signal);
}

export function createBudget(transport: AuthTransport, payload: BudgetInput) {
  return requestJson<MonthlyBudget>(
    "budgets/",
    { method: "POST", body: JSON.stringify(payload) },
    transport,
  );
}

export function updateBudget(transport: AuthTransport, id: string, payload: Partial<BudgetInput>) {
  return requestJson<MonthlyBudget>(
    `budgets/${id}/`,
    { method: "PATCH", body: JSON.stringify(payload) },
    transport,
  );
}

export function deleteBudget(transport: AuthTransport, id: string) {
  return requestJson<void>(`budgets/${id}/`, { method: "DELETE" }, transport);
}

export function getMonthlyReport(
  transport: AuthTransport,
  month: string,
  currency: string,
  signal?: AbortSignal,
) {
  const query = new URLSearchParams({ month, currency });
  return requestJson<MonthlyReport>(`reports/monthly/?${query.toString()}`, { signal }, transport);
}
