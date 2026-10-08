/**
 * The one HTTP client. It adds the access token, refreshes it when it expires (once, shared by
 * every request that hit the 401 at the same time), retries a GET once after a network error,
 * and turns the API's error format into a typed ApiError the screens can show.
 */
import type { ApiErrorBody, SessionOut } from './types';

export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:18000').replace(
  /\/$/,
  '',
);
const TIMEOUT_MS = 20_000;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly retryAfterS?: number,
    readonly fields?: { field: string; message: string }[],
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** True for "your data is still loading, try again shortly" (HTTP 503 not_ready). */
  get notReady() {
    return this.status === 503;
  }
}

export interface Tokens {
  access: string;
  refresh: string;
}

/** Wired up by the session provider: where tokens live and what happens on sign-out. */
export interface TokenStore {
  get(): Tokens | null;
  set(session: SessionOut): void;
  clear(): void;
}

let store: TokenStore | null = null;
export function setTokenStore(s: TokenStore) {
  store = s;
}

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE';

interface Options {
  method?: Method;
  body?: unknown;
  auth?: boolean; // default true
  signal?: AbortSignal; // cancel from the caller (e.g. a newer search)
}

async function raw(
  path: string,
  { method = 'GET', body, auth = true, signal }: Options,
  token?: string,
) {
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  if (signal) {
    if (signal.aborted) ctrl.abort();
    else signal.addEventListener('abort', () => ctrl.abort(), { once: true });
  }
  try {
    return await fetch(`${API_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: ctrl.signal,
    });
  } finally {
    clearTimeout(timer);
  }
}

async function toError(res: Response): Promise<ApiError> {
  let body: Partial<ApiErrorBody> = {};
  try {
    body = (await res.json()) as ApiErrorBody;
  } catch {
    // not JSON (e.g. a proxy error page)
  }
  const retry = Number(res.headers.get('Retry-After')) || undefined;
  return new ApiError(
    res.status,
    body.error?.code ?? `http_${res.status}`,
    body.error?.message ?? 'Something went wrong. Please try again.',
    retry,
    body.error?.details,
  );
}

let refreshing: Promise<boolean> | null = null;

/** Swap the refresh token for a new pair. Concurrent callers share one attempt. */
function refreshOnce(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const t = store?.get();
      if (!t) return false;
      try {
        const res = await raw('/v1/auth/refresh', {
          method: 'POST',
          body: { refresh_token: t.refresh },
          auth: false,
        });
        if (!res.ok) return false;
        store?.set((await res.json()) as SessionOut);
        return true;
      } catch {
        return false; // offline: keep the tokens, the next call will try again
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const auth = opts.auth ?? true;
  let attempt = 0;
  for (;;) {
    let res: Response;
    try {
      res = await raw(path, opts, store?.get()?.access);
    } catch {
      // Network error or timeout: retry a read once, never a write.
      if ((opts.method ?? 'GET') === 'GET' && attempt === 0) {
        attempt++;
        continue;
      }
      throw new ApiError(0, 'network', "Can't reach the server. Check your connection.");
    }

    if (res.status === 401 && auth && store?.get() && attempt < 2) {
      attempt = 2;
      if (await refreshOnce()) continue;
      store?.clear(); // the refresh token is gone or was revoked: sign in again
      throw await toError(res);
    }
    if (!res.ok) throw await toError(res);
    if (res.status === 204) return undefined as T;
    const text = await res.text(); // 202s may or may not carry a body
    return (text ? JSON.parse(text) : undefined) as T;
  }
}
