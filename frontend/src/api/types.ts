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
  category: string | null;
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
