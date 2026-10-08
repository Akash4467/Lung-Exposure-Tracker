/** Settings: connect Health Connect (heart rate, steps, workouts from the phone or a watch). */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, Card, ErrorBanner } from '@/components/ui';
import { connectHealth, healthStatus, openHealthSettings, syncHealth } from '@/lib/health';
import { errorMessage, keys } from '@/lib/query';
import { space, useColors } from '@/theme';

export function HealthCard() {
  const c = useColors();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['health'], queryFn: healthStatus });
  const [synced, setSynced] = useState<number | null>(null);

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ['health'] }),
      qc.invalidateQueries({ queryKey: keys.today }),
      qc.invalidateQueries({ queryKey: keys.activity }),
    ]);
  const sync = useMutation({
    mutationFn: syncHealth,
    onSuccess: async (n) => {
      setSynced(n);
      await refresh();
    },
  });
  const connect = useMutation({
    mutationFn: connectHealth,
    onSuccess: async (ok) => {
      await qc.invalidateQueries({ queryKey: ['health'] });
      if (ok) sync.mutate();
    },
  });

  if (status.data === undefined || status.data === 'unsupported') return null;
  return (
    <Card>
      <AppText variant="heading">Health Connect</AppText>
      <AppText variant="caption" muted>
        Heart rate, steps and workouts from your phone or watch show how hard you were breathing, so
        walks and runs count without logging them. Read-only; only the last 2 days are used.
      </AppText>
      <ErrorBanner message={errorMessage(connect.error ?? sync.error)} />
      {status.data === 'needs-install' ? (
        <>
          <AppText variant="caption" color={c.band.amber.fg}>
            Health Connect isn't available or needs an update on this phone.
          </AppText>
          <Button title="Open Health Connect" kind="secondary" onPress={openHealthSettings} />
        </>
      ) : status.data === 'off' ? (
        <Button
          title="Connect Health Connect"
          onPress={() => connect.mutate()}
          loading={connect.isPending}
        />
      ) : (
        <View style={{ gap: space.xs }}>
          <AppText variant="label" color={c.accent}>
            Connected
          </AppText>
          <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
            <Button
              title="Sync now"
              kind="secondary"
              compact
              onPress={() => sync.mutate()}
              loading={sync.isPending}
            />
            <Button title="Manage access" kind="ghost" compact onPress={openHealthSettings} />
          </View>
          {synced !== null ? (
            <AppText variant="caption" muted>
              {synced
                ? `Added ${synced} stretch${synced > 1 ? 'es' : ''} of activity from the last 2 days.`
                : 'Nothing new in the last 2 days.'}
            </AppText>
          ) : null}
        </View>
      )}
    </Card>
  );
}
