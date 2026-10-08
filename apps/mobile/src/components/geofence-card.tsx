import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Linking } from 'react-native';

import { ToggleRow } from '@/components/controls';
import { AppText, Button, Card, ErrorBanner } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import {
  flushVisits,
  geofenceStatus,
  NeedsAlwaysPermission,
  startGeofencing,
  stopGeofencing,
} from '@/lib/geofence';
import { keys } from '@/lib/query';

/** Settings card: opt in to using real home/office arrival and departure times. */
export function GeofenceCard() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ['geofence'], queryFn: geofenceStatus });
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });

  const toggle = useMutation({
    mutationFn: async (on: boolean) => {
      if (!on) return stopGeofencing();
      const p = profile.data;
      if (!p) throw new Error('Profile not loaded yet');
      await startGeofencing(p.places.home, p.places.office);
      await flushVisits();
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ['geofence'] }),
  });

  if (status.data === 'unsupported') return null;
  const needsSettings = toggle.error instanceof NeedsAlwaysPermission;

  return (
    <Card>
      <ToggleRow
        label="Use my real day"
        hint="Times you actually arrive at and leave home and work replace your usual schedule."
        value={status.data === 'on'}
        onChange={(on) => toggle.mutate(on)}
      />
      <AppText variant="caption" muted>
        Only two circles are watched: home and work. Your phone tells the app when you enter or
        leave one; this switch never records a route (that's "Record my trips" below). Android asks for location "all the
        time" because those moments can happen while the app is closed.
      </AppText>
      <ErrorBanner message={toggle.error ? toggle.error.message : null} />
      {needsSettings ? (
        <Button title="Open settings" kind="secondary" onPress={() => Linking.openSettings()} />
      ) : null}
    </Card>
  );
}
