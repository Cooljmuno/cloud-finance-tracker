# ADR 0007: Explainable categorization, monthly budgets, and spending reports

- Status: Accepted
- Date: 2026-10-18

## Context

Imported and manually entered transactions need useful categories without overwriting decisions a
user has already made. Users also need to compare monthly expense spending with a budget and see
recent trends. These operations should remain understandable within the existing Django service
and PostgreSQL database, with the same owner isolation and decimal money model as the ledger.

A signed amount alone does not distinguish a purchase from an income correction or an internal
transfer. Reports therefore need a documented interpretation of category kinds, refunds, pending
transactions, dates, and currencies before charts can communicate meaningful totals.

## Decision

### Ordered rules with explicit provenance

Use case-insensitive literal substring matching against normalized transaction descriptions. A
rule has an owned category, a unique case-insensitive name, an enabled state, and an integer
priority from 1 through 9,999, defaulting to 100. Run rules in ascending priority order, then oldest
creation time, then UUID for a stable tie break. The first enabled match whose category remains
active wins. Do not add regular expressions, inference, or external categorization services.

Require an active owned category for a new rule or a changed category assignment. An edited rule
may retain its current archived category, but matching skips it until the category is restored.
Rule collection and detail CRUD are available at `/api/v1/rules/` and
`/api/v1/rules/{uuid}/`, with owner-scoped querysets and foreign-resource validation.

Track transaction categorization through read-only `category_source` values of `manual`, `rule`,
and `uncategorized`, plus a nullable matched-rule reference. A manual choice includes an explicit
choice of no category. Migrate all preexisting transactions to manual, including null categories,
because an older row cannot tell us whether its original absence of a category was deliberate.

Accept optional write-only `category_mode` values of `automatic` and `manual`. A new transaction
without a category or mode uses automatic matching. An explicit category, including null, without
a mode records a manual decision. Automatic mode cannot be combined with a non-null category.
Manual mode without a category preserves the current category and clears the matched rule.

Updating a transaction without category inputs preserves its decision. A changed description
reevaluates automatic assignments, while a manual assignment remains unchanged. Notes-only edits
preserve existing provenance. The frontend omits unchanged category inputs when editing so that
an unrelated edit does not silently turn a rule assignment into a manual one.

Keep rule CRUD separate from reapplication. The confirmed `POST /api/v1/rules/apply/` action
atomically examines only transactions with a null category and an `uncategorized` source. It
returns examined and updated counts. Existing rule assignments and manual decisions, including
manual nulls, remain untouched. Deleting a rule clears its reference without clearing a
transaction's category or changing its source; later application does not overwrite that history.

CSV preview continues to validate records without promising a category. A new commit evaluates
the current rules while creating transactions. This updates the earlier uncategorized-import
behavior in ADR 0006 without changing its file format, signed preview proof, atomicity, or exact-file
retry protection. An exact retry returns its original receipt and never reapplies current rules.

### Monthly budgets with database guarantees

Store one positive decimal budget per owner, expense category, calendar month, and currency. The
API represents the month as `YYYY-MM`; storage uses its first day. Currency is normalized to three
uppercase ASCII letters and defaults to USD. Enforce uniqueness and positive amounts in the
database as well as serializer validation, including a useful validation error for a duplicate
write race.

Expose paginated owner-scoped CRUD at `/api/v1/budgets/` and
`/api/v1/budgets/{uuid}/`, with optional month and currency filters. Require an active owned
expense category for new assignments, while allowing an existing budget to retain its current
archived expense category. A category referenced by a budget cannot change away from expense.
Categories referenced by rules or budgets return `409` on deletion and advise archiving instead.

Keep budget rows independent of transactions: creating or editing a budget does not create an
expense, reserve funds, or alter an account balance. Deleting a budget removes its planning target
without deleting ledger history.

### One documented report calculation

Expose `GET /api/v1/reports/monthly/?month=YYYY-MM&currency=USD`. Require a strict calendar month
at or after `0001-06` so the response can include six complete calendar months. Use the requested
currency, defaulting to USD, and return monetary values as fixed two-decimal strings.

Scope reports to the authenticated owner and the currency of each transaction's account. Use
calendar transaction dates. Include transactions linked to archived accounts and categories.
Exclude pending transactions, opening balances, and transfer-category entries from income and
spending. Return a separate count of nontransfer pending transactions in the selected month;
the posted transaction count also excludes transfers.

Apply these same calculations to the selected month, category spending, budget usage, and trend:

- Income-category amounts contribute their signed amount to income. Negative adjustments reduce
  income.
- Expense-category amounts contribute their negated signed amount to spending. Positive refunds
  reduce spending rather than being counted again as income.
- Uncategorized positive amounts contribute to income; uncategorized negative amounts contribute
  their negated amount to spending.
- Net equals income minus spending. A transaction assigned to a transfer category contributes to
  neither total.

Report category rows include expense categories with posted activity or a budget, and an
uncategorized row when negative uncategorized transactions exist. A budget-only category has zero
spending. Sort rows by descending spending, then stable name and identifier. Remaining budget is
budget minus spending; refunds may make spending negative and remaining greater than the budget.
Do not clamp the underlying values to fit a chart.

Return exactly six monthly trend entries ending with the selected month, filling months without
activity with zero. Planning presents category spending and the trend with accessible charts and
exact values. Month and currency changes invalidate stale results, and loading or failures are
visible rather than replaced with invented zero totals.

There is no exchange-rate conversion, mixed-currency aggregate, account balance calculation, or
automatic detection of uncategorized internal transfers. Reports use the current kind of each
assigned category and the current currency of each account. Changing either classification can
change the interpretation of older transactions; reports are derived from the current ledger
rather than immutable historical report snapshots.

## Consequences

- A user can explain a rule match and override it, while explicit bulk application has a narrow,
  reviewable effect. Previously uncategorized manual choices are intentionally preserved.
- Rule changes affect future automatic evaluations. Existing assignments are not a live view of
  the current rules, and exact import retries retain their original behavior.
- One database-backed ledger supplies budget usage, totals, and trends, avoiding a second mutable
  store of financial summaries. These are correctness and maintainability choices, not measured
  performance claims.
- Refunds and income corrections retain their sign. Charts must support negative values and show
  exact numbers instead of hiding them behind a percentage bar.
- Separate currency reports avoid unsupported conversion claims. Opening balances and transfers
  remain outside income and spending.
- Archived history remains reportable. Restricting deletion of referenced categories preserves
  rules, budgets, and transaction references.
- Existing checkouts must apply migrations before using these features. The backend startup runs
  migrations; an already running container can use
  `docker compose exec backend python manage.py migrate`.
- AWS provisioning, observability, and deployment workflows remain a separate milestone. No
  deployment or production-load performance is implied by these application features.
