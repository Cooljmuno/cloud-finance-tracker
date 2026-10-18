export type CurrentUser = {
  id: string;
  username: string;
  email: string;
};

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export type FinancialAccount = {
  id: string;
  name: string;
  account_type: "checking" | "savings" | "credit_card" | "cash" | "investment" | "loan" | "other";
  institution: string;
  currency: string;
  opening_balance: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type Category = {
  id: string;
  name: string;
  kind: "expense" | "income" | "transfer";
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type AccountInput = Pick<
  FinancialAccount,
  "name" | "account_type" | "institution" | "opening_balance"
>;

export type CategoryInput = Pick<Category, "name" | "kind">;

export type FinanceTransaction = {
  id: string;
  account: string;
  account_name: string;
  currency: string;
  category: string | null;
  category_name: string | null;
  import_batch: string | null;
  category_source: "manual" | "rule" | "uncategorized";
  matched_rule: string | null;
  matched_rule_name: string | null;
  transaction_date: string;
  description: string;
  amount: string;
  status: "pending" | "posted";
  notes: string;
  created_at: string;
  updated_at: string;
};

export type TransactionFilters = {
  account: string;
  category: string;
  status: "" | "pending" | "posted";
  dateFrom: string;
  dateTo: string;
};

export type CreateTransaction = {
  account: string;
  category?: string | null;
  category_mode?: "automatic" | "manual";
  transaction_date: string;
  description: string;
  amount: string;
  status: "pending" | "posted";
  notes: string;
};

export type ImportBatch = {
  id: string;
  account: string;
  account_name: string;
  file_name: string;
  file_hash: string;
  row_count: number;
  created_at: string;
};

export type ImportRow = {
  row: number;
  transaction_date: string;
  description: string;
  amount: string;
  status: "pending" | "posted";
  notes: string;
};

export type ImportRowError = {
  row: number;
  field: string;
  message: string;
};

export type ImportPreview = {
  account: string;
  file_name: string;
  row_count: number;
  valid_count: number;
  error_count: number;
  errors: ImportRowError[];
  errors_truncated: boolean;
  rows: ImportRow[];
  preview_truncated: boolean;
  preview_token: string | null;
  already_imported: ImportBatch | null;
  can_commit: boolean;
};

export type ImportCommit = {
  batch: ImportBatch;
  duplicate: boolean;
};

export type CategorizationRule = {
  id: string;
  name: string;
  match_text: string;
  priority: number;
  category: string;
  category_name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type RuleInput = Pick<
  CategorizationRule,
  "name" | "match_text" | "priority" | "category" | "is_active"
>;

export type MonthlyBudget = {
  id: string;
  category: string;
  category_name: string;
  month: string;
  currency: string;
  amount: string;
  created_at: string;
  updated_at: string;
};

export type BudgetInput = Pick<MonthlyBudget, "category" | "month" | "currency" | "amount">;

export type MonthlyReport = {
  month: string;
  currency: string;
  transaction_count: number;
  pending_count: number;
  totals: { income: string; spending: string; net: string; uncategorized_spending: string };
  categories: {
    category: string | null;
    category_name: string;
    spending: string;
    budget: string | null;
    remaining: string | null;
    budget_id: string | null;
  }[];
  trend: { month: string; income: string; spending: string }[];
};
