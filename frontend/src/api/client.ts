import { appConfig } from "../config";

export type AuthTransport = { mode: "session" } | { mode: "cognito"; accessToken: string };

type ErrorBody = Record<string, unknown> | unknown[] | string | null;

export class ApiError extends Error {
  status: number;
  body: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(messageFromErrorBody(body, `Request failed with status ${status}.`));
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function messageFromErrorBody(body: ErrorBody, fallback: string): string {
  if (typeof body === "string" && body) {
    return body;
  }
  if (body && !Array.isArray(body) && typeof body === "object") {
    const detail = body.detail;
    if (typeof detail === "string") {
      return detail;
    }
  }
  return fallback;
}

function resolveUrl(pathOrUrl: string): string {
  const baseUrl = new URL(`${appConfig.apiBaseUrl}/`);
  const resolved = /^https?:\/\//.test(pathOrUrl)
    ? new URL(pathOrUrl)
    : new URL(pathOrUrl.replace(/^\//, ""), baseUrl);

  if (resolved.origin !== baseUrl.origin || !resolved.pathname.startsWith(baseUrl.pathname)) {
    throw new Error("Refused to send authentication to a URL outside the configured API.");
  }

  return resolved.toString();
}

function readCookie(name: string): string | null {
  const prefix = `${encodeURIComponent(name)}=`;
  const cookie = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

async function parseResponseBody(response: Response): Promise<ErrorBody> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    return (await response.json()) as ErrorBody;
  }
  const text = await response.text();
  return text || null;
}

async function getCsrfToken(signal?: AbortSignal): Promise<string> {
  const currentCookie = readCookie("csrftoken");
  if (currentCookie) {
    return currentCookie;
  }

  const response = await fetch(resolveUrl("auth/csrf/"), {
    credentials: "include",
    headers: { Accept: "application/json" },
    signal,
  });
  const body = await parseResponseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  if (body && !Array.isArray(body) && typeof body === "object") {
    const token = body.csrfToken;
    if (typeof token === "string") {
      return token;
    }
  }
  throw new Error("The API did not issue a CSRF token.");
}

export async function requestJson<T>(
  pathOrUrl: string,
  options: RequestInit = {},
  transport: AuthTransport,
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body && !(options.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let credentials: RequestCredentials = "omit";
  if (transport.mode === "session") {
    credentials = "include";
    if (!["GET", "HEAD", "OPTIONS", "TRACE"].includes(method)) {
      headers.set("X-CSRFToken", await getCsrfToken(options.signal ?? undefined));
    }
  } else {
    headers.set("Authorization", `Bearer ${transport.accessToken}`);
  }

  const response = await fetch(resolveUrl(pathOrUrl), {
    ...options,
    method,
    headers,
    credentials,
  });
  if (response.status === 204) {
    if (!response.ok) {
      throw new ApiError(response.status, null);
    }
    return undefined as T;
  }

  const body = await parseResponseBody(response);
  if (!response.ok) {
    throw new ApiError(response.status, body);
  }
  return body as T;
}

export function fieldErrors(error: unknown): Record<string, string> {
  if (!(error instanceof ApiError) || !error.body || Array.isArray(error.body)) {
    return {};
  }
  if (typeof error.body !== "object") {
    return {};
  }

  return Object.fromEntries(
    Object.entries(error.body).flatMap(([field, value]) => {
      if (typeof value === "string") {
        return [[field, value]];
      }
      if (Array.isArray(value) && typeof value[0] === "string") {
        return [[field, value[0]]];
      }
      return [];
    }),
  );
}
