/**
 * The signed-in state. Tokens are cached in memory for the API client (which needs them
 * synchronously on every request) and persisted in secure storage.
 */
import { useQueryClient } from '@tanstack/react-query';
import { router } from 'expo-router';
import {
  createContext,
  type PropsWithChildren,
  use,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from 'react';

import { setTokenStore, type Tokens } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';
import { unregisterPush } from '@/lib/push';
import type { SessionOut } from '@/lib/api/types';

import { readItem, writeItem } from './storage';

const KEY = 'lung.session';

type Status = 'loading' | 'signedOut' | 'signedIn';

interface SessionCtx {
  status: Status;
  userId: string | null;
  signIn: (s: SessionOut) => void;
  signOut: () => Promise<void>;
}

const Ctx = createContext<SessionCtx | null>(null);

export function useSession(): SessionCtx {
  const v = use(Ctx);
  if (!v) throw new Error('useSession must be inside <SessionProvider>');
  return v;
}

interface Stored extends Tokens {
  userId: string;
}

let current: Stored | null = null;

export function SessionProvider({ children }: PropsWithChildren) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<Status>('loading');
  const [userId, setUserId] = useState<string | null>(null);

  const apply = useCallback((next: Stored | null) => {
    current = next;
    setUserId(next?.userId ?? null);
    setStatus(next ? 'signedIn' : 'signedOut');
    void writeItem(KEY, next ? JSON.stringify(next) : null);
  }, []);

  /** Store the session (also used when the API client rotates tokens). */
  const store = useCallback(
    (s: SessionOut) =>
      apply({ access: s.access_token, refresh: s.refresh_token, userId: s.user_id }),
    [apply],
  );

  /** A fresh sign-in: store it, then let the root index pick the right area. */
  const signIn = useCallback(
    (s: SessionOut) => {
      store(s);
      router.replace('/');
    },
    [store],
  );

  // The API client reads and rotates tokens through this.
  useEffect(() => {
    setTokenStore({
      get: () => current,
      set: store, // token rotation: no navigation
      clear: () => {
        apply(null);
        queryClient.clear();
        router.replace('/');
      },
    });
  }, [apply, store, queryClient]);

  useEffect(() => {
    readItem(KEY)
      .then((raw) => apply(raw ? (JSON.parse(raw) as Stored) : null))
      .catch(() => apply(null));
  }, [apply]);

  const signOut = useCallback(async () => {
    await unregisterPush(); // while the token is still valid
    const refresh = current?.refresh;
    apply(null);
    queryClient.clear();
    router.replace('/');
    if (refresh) await authApi.logout(refresh).catch(() => undefined); // best effort
  }, [apply, queryClient]);

  const value = useMemo(
    () => ({ status, userId, signIn, signOut }),
    [status, userId, signIn, signOut],
  );
  return <Ctx value={value}>{children}</Ctx>;
}
