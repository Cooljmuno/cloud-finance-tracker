# ADR 0005: Manage resources while preserving transaction history

- Status: Accepted
- Date: 2026-10-18

## Context

Authenticated users need to create their first accounts and categories, correct transactions, and
retire financial metadata without breaking historical references. These workflows must work for an
empty profile as well as the seeded local demonstration.

## Decision

Expose account and category creation, editing, archiving, restoration, and deletion in the React
client. Keep authentication separate: local users retain session sign-in and the demo setup, while
future Cognito users can configure their workspace after hosted sign-in. This adds no local
registration flow.

Archive accounts and categories by setting `is_active=False`. Retain their transaction references
and include archived resources in historical filters. New transactions may use only active
resources. When editing an existing transaction, allow its current archived account or category to
remain selected; another archived resource cannot be newly assigned.

Allow deletion of unused accounts and categories after explicit inline confirmation. If transactions
reference the resource, return `409` and advise archiving. Check references before deletion and
handle restricted-deletion errors if references change between the check and the delete. Transaction
deletion also requires an inline confirmation with a cancel action.

Keep account and category names unique per owner, ignoring case, using database constraints and
serializer validation. If a conflicting write appears after initial validation, the serializer
rechecks the name after the failed atomic save and returns a field error for the duplicate. Other
database failures remain errors rather than being mislabeled as duplicate names.

Update client state after the server acknowledges a mutation, using returned resources for creates
and edits. Refresh the ledger after changes, preserve form values on failed saves, and disable
mutation controls while requests run. After deleting the only transaction on a later page, move to
the previous page. If a requested page becomes invalid, recover by loading page one. Clear filters
that reference a successfully deleted account or category.

Default new account forms to USD and show existing currency as read-only. Keep currency conversion
and cross-currency totals outside this milestone.

## Consequences

- Users can configure an authenticated empty workspace without seeding finance records.
- Archiving preserves historical context while preventing retired resources from being selected for
  new transactions.
- Server-acknowledged updates keep failed writes visible and avoid client-side rollback logic.
- Database constraints remain the final guard against duplicate names; serializer checks provide
  useful field errors.
- Tests exercise conflict paths through controlled interleavings. They verify those correctness
  paths rather than establishing throughput or concurrent-load performance.
