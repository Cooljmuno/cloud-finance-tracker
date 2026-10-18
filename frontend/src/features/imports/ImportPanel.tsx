import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, fieldErrors } from "../../api/client";
import { commitImport, getImportHistory, previewImport } from "../../api/imports";
import type {
  FinancialAccount,
  ImportBatch,
  ImportCommit,
  ImportPreview,
  Paginated,
} from "../../api/types";
import { useAppAuth } from "../../auth/AuthContext";
import { formatDate, formatMoney } from "../../shared/format";

type Props = {
  accounts: FinancialAccount[];
  onImported: (batch: ImportBatch, duplicate: boolean) => void;
  onBusyChange: (busy: boolean) => void;
};

export function ImportPanel({ accounts, onImported, onBusyChange }: Props) {
  const { transport, invalidate } = useAppAuth();
  const [accountId, setAccountId] = useState(
    () => accounts.find((account) => account.is_active)?.id ?? "",
  );
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [receipt, setReceipt] = useState<ImportCommit | null>(null);
  const [operation, setOperation] = useState<"preview" | "commit" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [history, setHistory] = useState<Paginated<ImportBatch> | null>(null);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyRefresh, setHistoryRefresh] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const mounted = useRef(true);
  const inFlight = useRef(false);
  const requestGeneration = useRef(0);
  const previewController = useRef<AbortController | null>(null);
  const previewRef = useRef<HTMLElement>(null);
  const receiptRef = useRef<HTMLElement>(null);
  const activeAccounts = accounts.filter((account) => account.is_active);
  const selectedAccount = activeAccounts.find((account) => account.id === accountId);
  const busy = operation !== null;

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      requestGeneration.current += 1;
      previewController.current?.abort();
      inFlight.current = false;
      onBusyChange(false);
    };
  }, [onBusyChange]);

  useEffect(() => {
    if (!accounts.some((account) => account.id === accountId && account.is_active)) {
      setAccountId(accounts.find((account) => account.is_active)?.id ?? "");
      setPreview(null);
      setReceipt(null);
      setErrors({});
      setError(null);
    }
  }, [accounts, accountId]);

  useEffect(() => {
    if (receipt) receiptRef.current?.focus();
    else if (preview) previewRef.current?.focus();
  }, [preview, receipt]);

  useEffect(() => {
    if (!transport) {
      setHistoryLoading(false);
      return;
    }
    const controller = new AbortController();
    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);
    setHistory(null);
    getImportHistory(transport, historyPage, controller.signal)
      .then((result) => {
        if (active) setHistory(result);
      })
      .catch((requestError: unknown) => {
        if (!active || (requestError instanceof DOMException && requestError.name === "AbortError"))
          return;
        if (requestError instanceof ApiError && requestError.status === 401) {
          void invalidate();
        } else if (
          requestError instanceof ApiError &&
          requestError.status === 404 &&
          historyPage > 1
        ) {
          setHistoryPage(1);
        } else {
          setHistoryError(
            requestError instanceof Error ? requestError.message : "Unable to load import history.",
          );
        }
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [historyPage, historyRefresh, invalidate, transport]);

  function clearSelectionResult() {
    requestGeneration.current += 1;
    previewController.current?.abort();
    setPreview(null);
    setReceipt(null);
    setError(null);
    setErrors({});
  }

  function beginRequest(nextOperation: "preview" | "commit") {
    inFlight.current = true;
    const generation = ++requestGeneration.current;
    setOperation(nextOperation);
    onBusyChange(true);
    return generation;
  }

  function currentRequest(generation: number) {
    return mounted.current && requestGeneration.current === generation;
  }

  function finishRequest(generation: number) {
    if (!currentRequest(generation)) return;
    inFlight.current = false;
    setOperation(null);
    onBusyChange(false);
  }

  async function previewFile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    setPreview(null);
    setReceipt(null);
    setError(null);
    setErrors({});
    if (!transport) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const nextErrors: Record<string, string> = {};
    if (!selectedAccount) nextErrors.account = "Choose an active import account.";
    if (!file) nextErrors.file = "Choose a CSV file.";
    else if (file.size > 256 * 1024) nextErrors.file = "Choose a CSV file no larger than 256 KiB.";
    if (Object.keys(nextErrors).length > 0 || !file || !selectedAccount) {
      setErrors(nextErrors);
      setError("Review the highlighted fields.");
      return;
    }
    const generation = beginRequest("preview");
    const controller = new AbortController();
    previewController.current = controller;
    try {
      const result = await previewImport(transport, accountId, file, controller.signal);
      if (currentRequest(generation)) {
        setPreview(result);
        if (result.already_imported) {
          setHistoryPage(1);
          setHistoryRefresh((current) => current + 1);
          onImported(result.already_imported, true);
        }
      }
    } catch (requestError: unknown) {
      if (
        !currentRequest(generation) ||
        (requestError instanceof DOMException && requestError.name === "AbortError")
      )
        return;
      if (requestError instanceof ApiError && requestError.status === 401) {
        await invalidate();
      } else {
        const backendErrors = fieldErrors(requestError);
        setErrors(backendErrors);
        setError(
          backendErrors.account || backendErrors.file
            ? "Review the highlighted fields."
            : (backendErrors.non_field_errors ??
                (requestError instanceof Error
                  ? requestError.message
                  : "Unable to preview this file. Try again.")),
        );
      }
    } finally {
      finishRequest(generation);
    }
  }

  async function importTransactions() {
    if (
      inFlight.current ||
      !preview?.can_commit ||
      !preview.preview_token ||
      !file ||
      !selectedAccount ||
      preview.account !== accountId
    )
      return;
    if (!transport) {
      setError("Your session has expired. Sign in again.");
      return;
    }
    const generation = beginRequest("commit");
    setError(null);
    setErrors({});
    try {
      const result = await commitImport(transport, accountId, file, preview.preview_token);
      if (!currentRequest(generation)) return;
      setReceipt(result);
      setPreview(null);
      setHistoryPage(1);
      setHistoryRefresh((current) => current + 1);
      onImported(result.batch, result.duplicate);
    } catch (requestError: unknown) {
      if (!currentRequest(generation)) return;
      if (requestError instanceof ApiError && requestError.status === 401) {
        await invalidate();
      } else if (requestError instanceof ApiError && requestError.status === 400) {
        const backendErrors = fieldErrors(requestError);
        setErrors(backendErrors);
        setPreview((current) =>
          current ? { ...current, can_commit: false, preview_token: null } : current,
        );
        const detail =
          backendErrors.preview_token ?? backendErrors.non_field_errors ?? requestError.message;
        setError(`${detail} Preview import again before importing transactions.`);
      } else {
        const detail =
          requestError instanceof Error
            ? requestError.message
            : "The import response could not be received.";
        setError(
          `${detail} Retry Import transactions with this unchanged file to safely check whether the import completed.`,
        );
      }
    } finally {
      finishRequest(generation);
    }
  }

  return (
    <div>
      <section className="transaction-panel" aria-labelledby="imports-heading" aria-busy={busy}>
        <div className="panel-heading">
          <div>
            <p className="card-kicker">Transaction files</p>
            <h2 id="imports-heading">CSV imports</h2>
          </div>
          <a
            className="text-button"
            href="/sample-transactions.csv"
            download="sample-transactions.csv"
          >
            Download sample CSV
          </a>
        </div>
        <p>
          Preview a UTF-8 CSV before importing. Files may contain up to 500 data rows and must be no
          larger than 256 KiB.
        </p>
        <p>
          Use these five column headers exactly:{" "}
          <code>transaction_date,description,amount,status,notes</code>.
        </p>
        <p className="muted">
          Use YYYY-MM-DD dates, nonzero signed amounts with up to two decimal places, and posted or
          pending status. Negative amounts are spending; positive amounts are inflows. Notes may be
          blank.
        </p>
        <p className="notice">
          Importing the exact same file into the same account adds it only once. Overlapping files
          can add duplicate transactions. Identical rows within a file are preserved.
        </p>

        {activeAccounts.length === 0 ? (
          <p className="notice">
            Create or restore an account in Accounts before importing transactions.
          </p>
        ) : null}

        <form onSubmit={previewFile} aria-label="Preview CSV import">
          <div className="form-grid">
            <label>
              Import account
              <select
                aria-label="Import account"
                value={accountId}
                disabled={busy || activeAccounts.length === 0}
                aria-invalid={Boolean(errors.account)}
                aria-describedby={errors.account ? "import-account-error" : undefined}
                onChange={(event) => {
                  if (inFlight.current) return;
                  setAccountId(event.target.value);
                  clearSelectionResult();
                }}
              >
                {activeAccounts.length === 0 ? <option value="">No active accounts</option> : null}
                {activeAccounts.map((account) => (
                  <option key={account.id} value={account.id}>
                    {account.name} ({account.currency})
                  </option>
                ))}
              </select>
              {errors.account ? (
                <span className="field-error" id="import-account-error">
                  {errors.account}
                </span>
              ) : null}
            </label>
            <label>
              CSV file
              <input
                aria-label="CSV file"
                type="file"
                accept=".csv,text/csv"
                disabled={busy || activeAccounts.length === 0}
                aria-invalid={Boolean(errors.file)}
                aria-describedby={errors.file ? "import-file-error" : undefined}
                onChange={(event) => {
                  if (inFlight.current) return;
                  setFile(event.target.files?.[0] ?? null);
                  clearSelectionResult();
                }}
              />
              {errors.file ? (
                <span className="field-error" id="import-file-error">
                  {errors.file}
                </span>
              ) : null}
            </label>
          </div>
          <div className="form-actions">
            <button
              className="primary-button"
              type="submit"
              disabled={busy || !file || !selectedAccount}
            >
              {operation === "preview" ? "Previewing…" : "Preview import"}
            </button>
          </div>
        </form>

        {error ? (
          <p className="form-error" role="alert">
            {error}
          </p>
        ) : null}

        {preview ? (
          <section
            className="import-preview"
            aria-labelledby="import-preview-heading"
            ref={previewRef}
            tabIndex={-1}
          >
            <h3 id="import-preview-heading">Import preview</h3>
            <p>
              {preview.file_name} · {selectedAccount?.name}
            </p>
            <div className="import-summary">
              <p>
                Total rows: <strong>{preview.row_count}</strong>
              </p>
              <p>
                Valid rows: <strong>{preview.valid_count}</strong>
              </p>
              <p>
                Row errors: <strong>{preview.error_count}</strong>
              </p>
            </div>
            {preview.already_imported ? (
              <div className="import-receipt">
                <h4>File already imported</h4>
                <p>
                  This file was previously imported into {preview.already_imported.account_name} on{" "}
                  {formatDate(preview.already_imported.created_at.slice(0, 10))}. No transactions
                  added.
                </p>
              </div>
            ) : null}
            {preview.errors.length > 0 ? (
              <div className="import-errors">
                <p>Correct the row errors and select the corrected CSV before previewing again.</p>
                <div className="table-scroll">
                  <table aria-label="Import row errors">
                    <thead>
                      <tr>
                        <th scope="col">Row</th>
                        <th scope="col">Field</th>
                        <th scope="col">Error</th>
                      </tr>
                    </thead>
                    <tbody>
                      {preview.errors.map((rowError, index) => (
                        <tr key={`${rowError.row}-${rowError.field}-${index}`}>
                          <td>{rowError.row}</td>
                          <td>{rowError.field}</td>
                          <td>{rowError.message}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {preview.errors_truncated ? (
                  <p>
                    Additional errors are omitted. Correct this file and preview again to check all
                    rows.
                  </p>
                ) : null}
              </div>
            ) : null}
            {preview.rows.length > 0 ? (
              <div className="table-scroll">
                <table aria-label="Validated import rows">
                  <thead>
                    <tr>
                      <th scope="col">Row</th>
                      <th scope="col">Date</th>
                      <th scope="col">Description</th>
                      <th scope="col">Amount</th>
                      <th scope="col">Status</th>
                      <th scope="col">Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.slice(0, 20).map((row) => (
                      <tr key={row.row}>
                        <td>{row.row}</td>
                        <td>{formatDate(row.transaction_date)}</td>
                        <td>{row.description}</td>
                        <td>{formatMoney(row.amount, selectedAccount?.currency ?? "USD")}</td>
                        <td>{row.status}</td>
                        <td>{row.notes || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
            {preview.preview_truncated || preview.valid_count > preview.rows.length ? (
              <p>
                Showing the first {Math.min(preview.rows.length, 20)} valid rows. Importing includes
                all {preview.row_count} rows when the file is valid.
              </p>
            ) : null}
            <div className="form-actions">
              <button
                className="primary-button"
                type="button"
                onClick={() => void importTransactions()}
                disabled={
                  busy ||
                  !preview.can_commit ||
                  !preview.preview_token ||
                  !selectedAccount ||
                  preview.account !== accountId
                }
              >
                {operation === "commit" ? "Importing…" : "Import transactions"}
              </button>
            </div>
          </section>
        ) : null}

        {receipt ? (
          <section
            className="import-receipt"
            aria-labelledby="import-receipt-heading"
            ref={receiptRef}
            tabIndex={-1}
          >
            <h3 id="import-receipt-heading">
              {receipt.duplicate ? "File already imported" : "Import complete"}
            </h3>
            <p>
              {receipt.batch.file_name} · {receipt.batch.account_name}
            </p>
            <p>
              {receipt.duplicate
                ? "No transactions added."
                : `${receipt.batch.row_count} transactions imported.`}
            </p>
            <p>
              Original import: {receipt.batch.row_count} rows on{" "}
              {formatDate(receipt.batch.created_at.slice(0, 10))}.
            </p>
          </section>
        ) : null}
      </section>

      <section
        className="transaction-panel import-history"
        aria-labelledby="import-history-heading"
        aria-busy={historyLoading}
      >
        <div className="panel-heading">
          <div>
            <p className="card-kicker">Completed files</p>
            <h2 id="import-history-heading">Import history</h2>
          </div>
        </div>
        {historyLoading ? <p>Loading import history…</p> : null}
        {historyError ? (
          <div className="error-banner" role="alert">
            <span>{historyError}</span>
            <button
              className="text-button"
              type="button"
              onClick={() => setHistoryRefresh((current) => current + 1)}
              disabled={busy}
            >
              Retry history
            </button>
          </div>
        ) : null}
        {!historyLoading && !historyError && history?.results.length === 0 ? (
          <p className="notice">No completed imports yet.</p>
        ) : null}
        {history && history.results.length > 0 ? (
          <>
            <div className="table-scroll">
              <table aria-label="Completed imports">
                <thead>
                  <tr>
                    <th scope="col">File</th>
                    <th scope="col">Account</th>
                    <th scope="col">Original rows</th>
                    <th scope="col">Imported</th>
                  </tr>
                </thead>
                <tbody>
                  {history.results.map((batch) => (
                    <tr key={batch.id}>
                      <td>{batch.file_name}</td>
                      <td>{batch.account_name}</td>
                      <td>{batch.row_count}</td>
                      <td>
                        <time dateTime={batch.created_at}>
                          {formatDate(batch.created_at.slice(0, 10))}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination" aria-label="Import history pages">
              <button
                className="secondary-button"
                type="button"
                aria-label="Previous import history page"
                onClick={() => setHistoryPage((current) => Math.max(1, current - 1))}
                disabled={!history.previous || historyLoading || busy}
              >
                Previous
              </button>
              <span>
                Page {historyPage} · {history.count} imports
              </span>
              <button
                className="secondary-button"
                type="button"
                aria-label="Next import history page"
                onClick={() => setHistoryPage((current) => current + 1)}
                disabled={!history.next || historyLoading || busy}
              >
                Next
              </button>
            </div>
          </>
        ) : null}
      </section>
    </div>
  );
}
