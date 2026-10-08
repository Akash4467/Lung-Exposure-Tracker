import { focusManager, QueryClient } from '@tanstack/react-query';
import { AppState, Platform } from 'react-native';

import { ApiError } from './api/client';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      // Retry "data still loading" (503) and network blips; never retry 4xx.
      retry: (count, err) =>
        err instanceof ApiError && (err.notReady || err.status === 0) && count < 6,
      retryDelay: (count, err) =>
        err instanceof ApiError && err.retryAfterS
          ? Math.min(err.retryAfterS, 30) * 1000
          : Math.min(2000 * 2 ** count, 30_000),
    },
    mutations: { retry: false },
  },
});

// Refresh server data when the app comes back to the foreground.
if (Platform.OS !== 'web') {
  AppState.addEventListener('change', (s) => focusManager.setFocused(s === 'active'));
}

export const keys = {
  me: ['me'] as const,
  profile: ['profile'] as const,
  catalog: ['catalog'] as const,
  today: ['score', 'today'] as const,
  forecast: ['score', 'forecast'] as const,
  history: ['score', 'history'] as const,
  activity: ['activity', 'today'] as const,
  trips: ['trips'] as const,
  location: ['location'] as const,
  tracks: ['tracks', 'today'] as const,
};

export function errorMessage(e: unknown): string | null {
  if (!e) return null;
  if (e instanceof ApiError) return e.message;
  return 'Something went wrong. Please try again.';
}
