import type { UseQueryResult } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { View } from 'react-native';

import { AppText, Button, Loading } from '@/components/ui';
import { ApiError } from '@/lib/api/client';
import { errorMessage } from '@/lib/query';
import { space } from '@/theme';

/**
 * Loading / "your air data is still arriving" / error / content. The 503 case is normal right
 * after onboarding: the server is fetching the first air data, and the query retries itself
 * after Retry-After.
 */
export function QueryState<T>({
  query,
  children,
}: {
  query: UseQueryResult<T>;
  children: (data: T) => ReactNode;
}) {
  if (query.data !== undefined) return <>{children(query.data)}</>;

  // During automatic retries the latest failure is in failureReason, not error.
  const err = query.error ?? query.failureReason;
  const notReady = err instanceof ApiError && err.notReady;
  if (query.isPending && !err) return <Loading label="Working out your estimate…" />;
  if (notReady) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', gap: space.md, paddingVertical: space.xxl }}>
        <Loading />
        <AppText variant="heading" style={{ textAlign: 'center' }}>
          Getting the air data for your area
        </AppText>
        <AppText muted style={{ textAlign: 'center' }}>
          This usually takes under a minute the first time. It'll appear here automatically.
        </AppText>
      </View>
    );
  }
  if (query.isFetching) return <Loading label="Working out your estimate…" />;
  return (
    <View style={{ gap: space.md, paddingVertical: space.xxl }}>
      <AppText variant="heading">Couldn't load this</AppText>
      <AppText muted>{errorMessage(err)}</AppText>
      <Button title="Try again" onPress={() => query.refetch()} />
    </View>
  );
}
