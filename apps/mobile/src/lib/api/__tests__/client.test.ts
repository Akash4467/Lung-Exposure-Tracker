/// <reference types="jest" />
import { api, ApiError, setTokenStore, type Tokens } from '../client';
import type { SessionOut } from '../types';

type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });

function mockFetch(handler: Handler) {
  const calls: { url: string; init: RequestInit }[] = [];
  globalThis.fetch = jest.fn(async (url: string, init: RequestInit) => {
    calls.push({ url, init });
    return handler(url, init);
  }) as unknown as typeof fetch;
  return calls;
}

function memoryStore(initial: Tokens | null) {
  let tokens = initial;
  const state = { cleared: 0, refreshed: 0 };
  setTokenStore({
    get: () => tokens,
    set: (s: SessionOut) => {
      state.refreshed++;
      tokens = { access: s.access_token, refresh: s.refresh_token };
    },
    clear: () => {
      state.cleared++;
      tokens = null;
    },
  });
  return state;
}

const session = (n: number): SessionOut => ({
  access_token: `access-${n}`,
  token_type: 'bearer',
  expires_at: '2026-10-04T00:00:00Z',
  refresh_token: `refresh-${n}`,
  user_id: 'u1',
  is_new_user: false,
});

const auth = (init: RequestInit) => (init.headers as Record<string, string>).Authorization;

test('sends the access token and parses JSON', async () => {
  memoryStore({ access: 'access-1', refresh: 'refresh-1' });
  const calls = mockFetch(() => json(200, { ok: true }));
  await expect(api('/v1/auth/me')).resolves.toEqual({ ok: true });
  expect(auth(calls[0].init)).toBe('Bearer access-1');
});

test('concurrent 401s share a single refresh, then every request is retried', async () => {
  const state = memoryStore({ access: 'expired', refresh: 'refresh-1' });
  const calls = mockFetch(async (url, init) => {
    if (url.endsWith('/v1/auth/refresh')) {
      await new Promise((r) => setTimeout(r, 20));
      return json(200, session(2));
    }
    return auth(init) === 'Bearer access-2'
      ? json(200, { ok: true })
      : json(401, { error: { code: 'invalid_token', message: 'expired' } });
  });

  const results = await Promise.all([1, 2, 3, 4, 5].map(() => api('/v1/me/score/today')));
  expect(results).toHaveLength(5);
  expect(calls.filter((c) => c.url.endsWith('/v1/auth/refresh'))).toHaveLength(1);
  expect(state.refreshed).toBe(1);
});

test('a failed refresh signs out and surfaces the 401', async () => {
  const state = memoryStore({ access: 'expired', refresh: 'revoked' });
  mockFetch((url) =>
    url.endsWith('/v1/auth/refresh')
      ? json(401, { error: { code: 'invalid_refresh_token', message: 'sign in again' } })
      : json(401, { error: { code: 'invalid_token', message: 'expired' } }),
  );
  await expect(api('/v1/auth/me')).rejects.toMatchObject({ status: 401, code: 'invalid_token' });
  expect(state.cleared).toBe(1);
});

test('reads are retried once after a network error; writes are not', async () => {
  memoryStore(null);
  let n = 0;
  mockFetch(() => {
    n++;
    if (n === 1) throw new TypeError('Network request failed');
    return json(200, { ok: true });
  });
  await expect(api('/v1/catalog', { auth: false })).resolves.toEqual({ ok: true });

  n = 0;
  mockFetch(() => {
    n++;
    throw new TypeError('Network request failed');
  });
  await expect(api('/v1/me/visits', { method: 'POST', body: {} })).rejects.toMatchObject({
    code: 'network',
  });
  expect(n).toBe(1);
});

test('the API error format becomes a typed ApiError, with Retry-After', async () => {
  memoryStore({ access: 'a', refresh: 'r' });
  mockFetch(() =>
    json(503, { error: { code: 'not_ready', message: 'air data is loading' } }, { 'Retry-After': '60' }),
  );
  const err = (await api('/v1/me/score/today').catch((e) => e)) as ApiError;
  expect(err).toBeInstanceOf(ApiError);
  expect([err.status, err.code, err.message, err.retryAfterS, err.notReady]).toEqual([
    503,
    'not_ready',
    'air data is loading',
    60,
    true,
  ]);
});

test('field errors are kept for forms', async () => {
  memoryStore(null);
  mockFetch(() =>
    json(400, {
      error: {
        code: 'validation_failed',
        message: 'email: not valid',
        details: [{ field: 'email', message: 'not valid' }],
      },
    }),
  );
  const err = (await api('/v1/auth/register', { method: 'POST', body: {}, auth: false }).catch(
    (e) => e,
  )) as ApiError;
  expect(err.fields).toEqual([{ field: 'email', message: 'not valid' }]);
});

test('204 has no body; 202 may have one', async () => {
  memoryStore({ access: 'a', refresh: 'r' });
  mockFetch(() => new Response(null, { status: 204 }));
  await expect(api('/v1/auth/logout', { method: 'POST', body: {} })).resolves.toBeUndefined();
  mockFetch(() => json(202, { accepted: 3 }));
  await expect(api('/v1/me/visits', { method: 'POST', body: {} })).resolves.toEqual({ accepted: 3 });
});
