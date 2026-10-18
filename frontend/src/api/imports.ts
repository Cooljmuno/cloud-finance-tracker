import { requestJson, type AuthTransport } from "./client";
import type { ImportBatch, ImportCommit, ImportPreview, Paginated } from "./types";

function importPayload(accountId: string, file: File) {
  const body = new FormData();
  body.append("account", accountId);
  body.append("file", file);
  return body;
}

export function previewImport(
  transport: AuthTransport,
  accountId: string,
  file: File,
  signal?: AbortSignal,
) {
  return requestJson<ImportPreview>(
    "imports/preview/",
    { method: "POST", body: importPayload(accountId, file), signal },
    transport,
  );
}

export function commitImport(
  transport: AuthTransport,
  accountId: string,
  file: File,
  previewToken: string,
) {
  const body = importPayload(accountId, file);
  body.append("preview_token", previewToken);
  return requestJson<ImportCommit>("imports/commit/", { method: "POST", body }, transport);
}

export function getImportHistory(transport: AuthTransport, page: number, signal?: AbortSignal) {
  return requestJson<Paginated<ImportBatch>>(
    page > 1 ? `imports/?page=${page}` : "imports/",
    { signal },
    transport,
  );
}
