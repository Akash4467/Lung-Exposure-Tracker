/**
 * "Your commute" over the map: roadside PM2.5 along the route at the times you travel, and
 * what each way of travelling means per hour on that same route (air let in × mask ×
 * how hard you breathe doing it).
 */
import { router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText, Button, Card, Segmented } from '@/components/ui';
import { aqi, useAqiScale } from '@/lib/aqi';
import type { CommuteOut } from '@/lib/api/types';
import { MODES } from '@/lib/labels';
import { radius, space, useColors } from '@/theme';

export type Leg = 'morning' | 'evening';

const SHORT: Record<string, string> = { two_wheeler: '2-wheeler', metro: 'Metro' };
const modeLabel = (m: string) => MODES.find((x) => x.value === m)?.label ?? m;
const shortMode = (m: string) => SHORT[m] ?? modeLabel(m);

const clock = (iso: string) =>
  new Date(iso)
    .toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
    .replace(/\s?[AP]M$/i, '');

export function CommuteSheet({
  c,
  leg,
  onLeg,
  onClose,
}: {
  c: CommuteOut;
  leg: Leg;
  onLeg: (l: Leg) => void;
  onClose: () => void;
}) {
  const col = useColors();
  const l = c[leg];
  const scale = useAqiScale((s) => s.scale);
  const road = l.avg_pm25 !== null ? aqi(l.avg_pm25, scale) : null;
  const worst = Math.max(...c.modes.map((m) => m.ug_per_hour), 1);
  return (
    <Card strong style={{ gap: space.sm, padding: space.md }}>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <AppText variant="heading">Your commute</AppText>
          <AppText variant="caption" muted>
            {c.distance_km ? `${c.distance_km} km · ` : ''}
            {modeLabel(c.mode)}
            {c.mask !== 'none' ? ` · ${c.mask.toUpperCase()} mask` : ''}
          </AppText>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close"
          hitSlop={10}
          onPress={onClose}
          style={[styles.close, { backgroundColor: col.field }]}>
          <AppText variant="label">✕</AppText>
        </Pressable>
      </View>

      <Segmented
        options={[
          { value: 'morning', label: `To work ${clock(c.morning.depart)}` },
          { value: 'evening', label: `Home ${clock(c.evening.depart)}` },
        ]}
        value={leg}
        onChange={onLeg}
      />

      {l.avg_pm25 !== null && road ? (
        <AppText variant="caption">
          Beside the road:{' '}
          <AppText variant="caption" style={{ fontWeight: '600' }}>
            AQI {road.value}
          </AppText>{' '}
          ({road.label.toLowerCase()}, PM2.5 {Math.round(l.avg_pm25)} µg/m³). Per hour of travel:
        </AppText>
      ) : (
        <AppText muted>Air data for this time isn't in yet.</AppText>
      )}

      {c.modes.length ? (
        <View style={{ gap: 6 }}>
          {c.modes.map((m) => (
            <View key={m.mode} style={styles.mode}>
              <AppText
                variant="caption"
                style={{ width: 82, fontWeight: m.current ? '600' : '400' }}
                numberOfLines={1}>
                {shortMode(m.mode)}
              </AppText>
              <View style={[styles.track, { backgroundColor: col.field }]}>
                <View
                  style={{
                    width: `${Math.max(4, (m.ug_per_hour / worst) * 100)}%`,
                    height: '100%',
                    borderRadius: radius.pill,
                    backgroundColor: m.current ? col.text : '#9AA1AB',
                  }}
                />
              </View>
              <AppText
                variant="caption"
                numberOfLines={1}
                style={{ width: 74, textAlign: 'right' }}>
                {Math.round(m.ug_per_hour)} µg/h
              </AppText>
            </View>
          ))}
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
        <Button
          title="Change home & work"
          kind="secondary"
          compact
          onPress={() => router.push('/edit-profile')}
        />
        <Button
          title="Try a time or mask"
          kind="secondary"
          compact
          onPress={() => router.push('/simulate')}
        />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  close: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  mode: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  track: { flex: 1, height: 8, borderRadius: radius.pill, overflow: 'hidden' },
});
