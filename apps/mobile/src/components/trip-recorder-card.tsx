/** Settings: opt in to recording the routes you actually travel. Off by default. */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Linking, View } from 'react-native';

import { ToggleRow } from '@/components/controls';
import { AppText, Button, Card, ErrorBanner } from '@/components/ui';
import { tracksApi } from '@/lib/api/endpoints';
import { keys } from '@/lib/query';
import {
  NeedsPermission,
  recorderStatus,
  startRecording,
  stopRecording,
} from '@/lib/trip-recorder';
import { space } from '@/theme';

export function TripRecorderCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['recorder'], queryFn: recorderStatus });
  const [deleted, setDeleted] = useState<number | null>(null);
  const toggle = useMutation({
    mutationFn: (on: boolean) => (on ? startRecording() : stopRecording()),
    onSettled: () => qc.invalidateQueries({ queryKey: ['recorder'] }),
  });
  const wipe = useMutation({
    mutationFn: tracksApi.deleteAll,
    onSuccess: async (r) => {
      setDeleted(r.deleted);
      await qc.invalidateQueries({ queryKey: keys.tracks });
      await qc.invalidateQueries({ queryKey: keys.today });
    },
  });

  if (status.data === 'unsupported') return null;
  return (
    <Card>
      <ToggleRow
        label="Record my trips"
        hint="Counts the air where you actually travel, and how: walking, running, cycling or in a vehicle."
        value={status.data === 'on'}
        onChange={(on) => toggle.mutate(on)}
      />
      <AppText variant="caption" muted>
        Off unless you turn it on. While on, your phone shows a notification and notes your location
        as you move. The server turns it into short trip legs (when, how, and the ~10 km air square)
        and does not keep the GPS points; a simplified line is kept so you can see your day on the
        map. Everything is deleted after 7 days, or now with the button below.
      </AppText>
      <ErrorBanner message={toggle.error ? toggle.error.message : null} />
      {toggle.error instanceof NeedsPermission ? (
        <Button title="Open settings" kind="secondary" onPress={() => Linking.openSettings()} />
      ) : null}
      <View style={{ gap: space.xs }}>
        <Button
          title="Delete my recorded trips"
          kind="ghost"
          compact
          loading={wipe.isPending}
          onPress={() => wipe.mutate()}
        />
        {deleted !== null ? (
          <AppText variant="caption" muted style={{ textAlign: 'center' }}>
            {deleted ? `Deleted ${deleted} trip legs.` : 'Nothing recorded to delete.'}
          </AppText>
        ) : null}
      </View>
    </Card>
  );
}
