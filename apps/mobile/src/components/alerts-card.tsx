/**
 * Asking for notification permission only when the person chooses to, after they've seen what
 * the app does. A launch-time prompt gets reflexive "Don't allow" taps.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Linking, View } from 'react-native';

import { ToggleRow } from '@/components/controls';
import { AppText, Button, Card } from '@/components/ui';
import { pushPermission, registerForPush, unregisterPush } from '@/lib/push';
import { space } from '@/theme';

const DISMISSED = 'lung.alerts.dismissed';
const KEY = ['push'] as const;

function usePush() {
  const qc = useQueryClient();
  const status = useQuery({ queryKey: KEY, queryFn: pushPermission });
  const turnOn = useMutation({
    mutationFn: registerForPush,
    onSettled: () => qc.invalidateQueries({ queryKey: KEY }),
  });
  return { status: status.data, turnOn, refresh: () => qc.invalidateQueries({ queryKey: KEY }) };
}

/** On Today: shown until the person turns alerts on or dismisses the card. */
export function AlertsCard() {
  const qc = useQueryClient();
  const { status, turnOn } = usePush();
  const dismissed = useQuery({
    queryKey: ['alerts-dismissed'],
    queryFn: async () => (await AsyncStorage.getItem(DISMISSED)) === '1',
  });
  if (status !== 'undetermined' || dismissed.data !== false) return null;

  return (
    <Card>
      <AppText variant="heading">Get a heads-up for bad-air days</AppText>
      <AppText muted>
        We'll send one short alert the evening before a high-exposure day or likely smoke, so you
        can plan. Nothing else.
      </AppText>
      {/* stacked, so the labels never wrap inside the pills on narrow phones or large text */}
      <View style={{ gap: space.xs }}>
        <Button title="Turn on alerts" onPress={() => turnOn.mutate()} loading={turnOn.isPending} />
        <Button
          title="Not now"
          kind="ghost"
          compact
          onPress={async () => {
            await AsyncStorage.setItem(DISMISSED, '1');
            await qc.invalidateQueries({ queryKey: ['alerts-dismissed'] });
          }}
        />
      </View>
    </Card>
  );
}

/** In Settings: the alerts switch, or a way to the system settings if alerts are blocked. */
export function AlertsSetting() {
  const { status, turnOn, refresh } = usePush();
  if (status === undefined) return null;
  if (status === 'denied') {
    return (
      <Card>
        <AppText variant="heading">Alerts are blocked</AppText>
        <AppText variant="caption" muted>
          Notifications for this app are turned off in your phone's settings.
        </AppText>
        <Button title="Open settings" kind="secondary" onPress={() => Linking.openSettings()} />
      </Card>
    );
  }
  return (
    <Card>
      <ToggleRow
        label="Bad-air alerts"
        hint="One short alert the evening before a high-exposure day or likely smoke."
        value={status === 'granted'}
        onChange={async (on) => {
          if (on) turnOn.mutate();
          else {
            await unregisterPush(); // stop alerts to this phone; permission stays as it is
            refresh();
          }
        }}
      />
    </Card>
  );
}
