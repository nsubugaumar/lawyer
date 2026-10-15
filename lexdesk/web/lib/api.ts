/**
 * The one way the web app talks to LexDesk.
 *
 * The 10-minute access token lives only in memory. The refresh token is an
 * HttpOnly cookie the browser sends to /api/v1/auth/ and JavaScript can never
 * read, so an injected script cannot walk away with a lasting session.
 * Every request that comes back 401 is retried once after a silent refresh.
 */

export type ApiError = { status: number; code: string; message: string; fields?: Record<string, string[] | string> };

let accessToken: string | null = null;
let refreshing: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

/**
 * Which firm's public website this is. Signed-in people always work inside
 * their own firm (the server decides that); these only pick the website shown
 * to visitors: a ?firm=name link, or the address in the browser bar.
 */
export function firmHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const headers: Record<string, string> = { "X-LexDesk-Host": window.location.host };
  try {
    const fromLink = new URLSearchParams(window.location.search).get("firm");
    if (fromLink) sessionStorage.setItem("lexdesk.firm", fromLink);
    const slug = fromLink ?? sessionStorage.getItem("lexdesk.firm");
    if (slug) headers["X-LexDesk-Firm"] = slug;
  } catch {
    /* storage blocked: the address bar still identifies the firm */
  }
  return headers;
}

export function setAccessToken(token: string | null) {
  accessToken = token;
}

/** Called when the session ends for good (refresh failed). */
export function onSessionExpired(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = fetch("/api/v1/auth/refresh/", { method: "POST", credentials: "same-origin" })
      .then(async (r) => {
        if (!r.ok) return false;
        const body = await r.json();
        accessToken = body.access;
        return true;
      })
      .catch(() => false)
      .finally(() => {
        setTimeout(() => (refreshing = null), 0);
      });
  }
  return refreshing;
}

type Options = Omit<RequestInit, "body"> & { body?: unknown; query?: Record<string, string | number | boolean | undefined | null> };

function buildUrl(path: string, query?: Options["query"]) {
  const url = path.startsWith("/api/") ? path : `/api/v1${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") params.set(k, String(v));
  const qs = params.toString();
  return qs ? `${url}${url.includes("?") ? "&" : "?"}${qs}` : url;
}

export async function api<T = any>(path: string, opts: Options = {}, retry = true): Promise<T> {
  const headers = new Headers(opts.headers);
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(opts.body);
  }
  if (accessToken) headers.set("Authorization", `Bearer ${accessToken}`);
  for (const [k, v] of Object.entries(firmHeaders())) headers.set(k, v);

  const response = await fetch(buildUrl(path, opts.query), { ...opts, headers, body, credentials: "same-origin" });

  if (response.status === 401 && retry && !path.includes("/auth/login") && !path.includes("/auth/refresh")) {
    if (await refreshSession()) return api<T>(path, opts, false);
    listeners.forEach((fn) => fn());
  }
  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  if (!response.ok) {
    const err = data?.error ?? {};
    const error: ApiError = {
      status: response.status,
      code: err.code ?? "error",
      message:
        err.message ??
        (response.status >= 500
          ? "Something went wrong on our side. Please try again in a moment."
          : "That did not work. Please try again."),
      fields: err.fields,
    };
    throw error;
  }
  return data as T;
}

export function fieldError(error: unknown, field: string): string | undefined {
  const e = error as ApiError | undefined;
  const value = e?.fields?.[field];
  if (!value) return undefined;
  return Array.isArray(value) ? value.join(" ") : String(value);
}

export function errorMessage(error: unknown): string {
  const e = error as ApiError;
  if (e?.fields) {
    const first = Object.entries(e.fields)[0];
    if (first && first[0] === "non_field_errors") return Array.isArray(first[1]) ? first[1][0] : String(first[1]);
  }
  return e?.message ?? "Something went wrong.";
}

/** Paginated DRF list → just the rows. */
export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };
export async function list<T>(path: string, query?: Options["query"]): Promise<T[]> {
  const data = await api<Page<T> | T[]>(path, { query: { page_size: 200, ...query } });
  return Array.isArray(data) ? data : data.results;
}

/**
 * Fetch a protected file with the session token and hand it to the browser,
 * either opened in a new tab (PDFs, images) or saved. The file never touches
 * a public URL.
 */
export async function openFile(path: string, filename: string, inline: boolean) {
  const url = buildUrl(path, inline ? { inline: 1 } : undefined);
  // Inside the Android app, the phone downloads the file itself and opens it
  // in its own viewer (WebViews cannot show PDFs or save blob links).
  const bridge = (window as unknown as { LexDeskApp?: { download: (p: string, t: string, n: string, open: boolean) => void } }).LexDeskApp;
  if (bridge) {
    if (!accessToken) await refreshSession();
    bridge.download(url, accessToken ?? "", filename, inline);
    return;
  }
  const go = () => fetch(url, { headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}, credentials: "same-origin" });
  let response = await go();
  if (response.status === 401 && (await refreshSession())) response = await go();
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw { status: response.status, code: data?.error?.code ?? "error", message: data?.error?.message ?? "That file could not be opened." } as ApiError;
  }
  const blob = await response.blob();
  const href = URL.createObjectURL(blob);
  if (inline) window.open(href, "_blank", "noopener");
  else {
    const a = document.createElement("a");
    a.href = href;
    a.download = filename;
    a.click();
  }
  setTimeout(() => URL.revokeObjectURL(href), 60000);
}

/** Fetch a protected file as a Blob, with the session (for saving offline). */
export async function fetchFile(path: string): Promise<Blob> {
  const url = buildUrl(path);
  const go = () => fetch(url, { headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}, credentials: "same-origin" });
  let response = await go();
  if (response.status === 401 && (await refreshSession())) response = await go();
  if (!response.ok) throw { status: response.status, code: "error", message: "A document could not be saved." } as ApiError;
  return response.blob();
}
