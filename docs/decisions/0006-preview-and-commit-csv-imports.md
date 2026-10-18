# ADR 0006: Preview and commit bounded CSV imports

- Status: Accepted
- Date: 2026-10-18

## Context

Users need to inspect a statement before adding transactions. A malformed row must not leave a
partially imported statement, and retrying a request after a lost response must not create a second
copy. Two purchases with matching dates, descriptions, and amounts may still be legitimate, so
transaction similarity alone cannot decide which records to remove.

The project needs a design that can be explained and operated with one Django service and one
PostgreSQL database. Bounded uploads fit synchronous requests without adding background workers or
retaining uploaded statements.

## Decision

Accept one documented UTF-8 CSV format with exactly these headers, in order:

```csv
transaction_date,description,amount,status,notes
```

Limit each upload to 256 KiB and 500 nonblank records. Require strict calendar dates, nonzero
decimal amounts with at most 12 whole digits and two decimal places, and normalized descriptions
of at most 255 characters. Accept `pending`, `posted`, or blank status, defaulting blank to
`posted`. Notes are optional and limited to 1,000 characters. Skip blank records, preserve repeated
transaction records, and reject structurally malformed CSV and incorrect headers.

Use the same parsing and validation rules for preview and commit. Preview checks all records and
returns at most 20 valid rows, at most 50 field errors, and the full error count. A smaller display
does not mean that the remaining records went unchecked. Any invalid record blocks the entire
file; users correct the source file rather than silently importing a subset.

On successful preview, issue a signed receipt with a 15-minute expiry. It binds the authenticated
user, account, and SHA-256 hash of the exact uploaded bytes. The signature prevents clients from
substituting another account or file after validation. It is a short-lived validation receipt, not
an authentication credential; every endpoint still requires the normal local session or Cognito
authentication and ownership checks.

Commit requires the file and signed receipt again. Recheck the receipt, account state, and every
record. Lock the selected account row within a database transaction, then check for an existing
import with that account and file hash. Save the import batch and all transactions atomically if
none exists. Keep a unique `(account, file_hash)` database constraint as the final duplicate guard.
The account lock serializes simultaneous commits to the same account, including different files.
This is a deliberate tradeoff for small, bounded statements and a simpler correctness argument.

Return `201` for a new batch and `200` with the original batch receipt for an exact repeat. Keep
the filename out of the uniqueness key, so renaming a file cannot bypass retry protection. Scope
the key to the account, so the same bytes may be imported into another owned account. Byte changes
such as changed line endings or reordered records produce a different fingerprint. Overlapping
statements are also different imports; this design does not claim to deduplicate them.

Retain the filename, hash, imported record count, account, and timestamp as the batch receipt. Do
not retain raw CSV bytes in the database or as uploaded files after the request. Transactions
reference their batch through a read-only `import_batch` field, allowing users to trace how a row
entered the ledger. New imports are uncategorized until the later rules milestone.

Allow users to edit or delete imported transactions. Retain the original receipt even when every
transaction has been removed. A repeat returns that receipt rather than recreating deleted rows or
overwriting edits. Accounts with import receipts cannot be deleted and return `409`; archiving
preserves their history. Every import list, detail, preview, and commit remains scoped to the
authenticated owner.

Expose a dedicated Imports page with sample download, preview, field errors, explicit commit, and
paginated import history. Keep validation failures visible and financial writes behind the commit
action. Requiring a new preview after changing files or accounts makes that boundary clear.

## Consequences

- Invalid files and failed commits leave no partial financial history.
- Exact retries produce one import per account, including simultaneous requests and retries after
  a response is lost.
- Duplicate-looking rows inside a statement are preserved; detecting overlapping statements needs
  a separate future product decision.
- Reuploading at commit avoids stored upload state, but transfers the bounded file twice and
  requires users to preview again after the receipt expires.
- The database stores structured transactions and limited provenance rather than copies of source
  statements. There is no bulk undo feature; transaction edits and deletion remain explicit.
- Account locks favor clear correctness over maximum import throughput. Performance claims require
  measured workloads rather than the presence of a lock or uniqueness constraint alone.
- Existing deployments must apply the new migration before using Imports. The Docker backend
  startup already runs migrations; an existing running container can use `python manage.py migrate`.
