# ADR 0003: Model the ledger with signed decimals

- Status: Accepted
- Date: 2026-08-30

## Context

The application needs to preserve imported financial history, isolate every user's records, and
support exact balance and spending calculations. Accounts and categories may be renamed or retired,
but existing transactions must remain interpretable.

## Decision

Keep accounts, categories, and transactions in one `finance` Django app because they form one
transactional boundary.

Represent money with `DecimalField`, never floating point. Transaction amounts are signed: positive
is an inflow, negative is an outflow, and zero is rejected in both the API and database. Store an
account's opening balance, but derive its current balance from posted transactions to avoid two
values drifting apart.

Store an owner on all three models. The direct transaction owner supports indexed tenant and date
queries without joining through accounts. Because that owner is denormalized, serializer relation
querysets and model validation require the transaction, account, and optional category to share the
same owner. Clients never control the owner field.

Normal and bulk Django ORM writes run full model validation, and queryset updates cannot modify
ownership relations. This makes the denormalized invariant an application-wide rule rather than an
API-only convention. Raw SQL is reserved for reviewed migrations and is not an application write
path.

Use case-insensitive owner-scoped uniqueness for account and category names. Referenced accounts and
categories use restricted deletion and are marked inactive instead. A complete user deletion may
still cascade through all of the user's finance records.

Return another user's resource as `404` through owner-scoped querysets. Reject another user's
account or category UUID as an invalid relation without confirming whether that UUID exists.

## Consequences

- Decimal arithmetic and a documented sign convention keep totals deterministic.
- Historical transactions retain their account and category context.
- Tenant/date and reporting indexes favor the application's expected read-heavy workload.
- Cross-currency totals remain unsupported until exchange-rate handling is designed.
- Transfers are not yet linked pairs; the import and reporting layers must treat transfer categories
  separately from income and spending.
- The duplicated transaction owner improves isolation queries but requires continued invariant tests
  for every new write path, including future imports.
