/**
 * A glass card over the map for one place (tapped, searched or "my location"): outdoor PM2.5
 * now, the next days at a glance, and the cleanest hours to be outside.
 */
import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AqiPill, useAqi } from '@/components/aqi-pill';
import { TripPlanner } from '@/components/trips';
import { AppText, Button, Card, Loading } from '@/components/ui';
import { airStep } from '@/lib/air-colors';
import { aqi, useAqiScale } from '@/lib/aqi';
import { mapApi } from '@/lib/api/endpoints';
import type { PlaceAirOut } from '@/lib/api/types';
import { errorMessage } from '@/lib/query';
import { radius, space, useColors } from '@/theme';

export interface MapPlace {
  lat: number;
  lon: number;
  label: string;
  detail?: string;
}

export function PlaceSheet({
  place,
  onClose,
  onDirections,
}: {
  place: MapPlace;
  onClose: () => void;
  onDirections?: () => void;
}) {
  const c = useColors();
  const [planning, setPlanning] = useState(false);
  const [added, setAdded] = useState(false);
  const air = useQuery({
    queryKey: ['map-place', place.lat.toFixed(2), place.lon.toFixed(2)],
    queryFn: () => mapApi.place(place.lat, place.lon),
    staleTime: 15 * 60_000,
  });
  return (
    <Card strong style={styles.card}>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <AppText variant="heading" numberOfLines={1}>
            {place.label}
          </AppText>
          {place.detail ? (
            <AppText variant="caption" muted numberOfLines={1}>
              {place.detail}
            </AppText>
          ) : null}
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Close"
          hitSlop={10}
          onPress={onClose}
          style={[styles.close, { backgroundColor: c.field }]}>
          <AppText variant="label">✕</AppText>
        </Pressable>
      </View>
      {planning ? (
        <TripPlanner
          place={place}
          onDone={() => {
            setPlanning(false);
            setAdded(true);
          }}
        />
      ) : air.data ? (
        <>
          <Body a={air.data} />
          {added ? (
            <AppText variant="caption" color={c.accent}>
              Trip added. You'll find it on the Tomorrow tab.
            </AppText>
          ) : null}
          <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
            {onDirections && place.label !== 'You are here' ? (
              <Button title="Directions here" compact onPress={onDirections} />
            ) : null}
            {!added && place.label !== 'You are here' ? (
              <Button
                title="Plan a trip here"
                kind="secondary"
                compact
                onPress={() => setPlanning(true)}
              />
            ) : null}
          </View>
        </>
      ) : air.isError ? (
        <AppText muted>{errorMessage(air.error)}</AppText>
      ) : (
        <Loading />
      )}
    </Card>
  );
}

function weekday(date: string, i: number) {
  if (i === 0) return 'Today';
  return new Date(`${date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' });
}

/** "2 pm" in the place's own time, from a UTC hour. */
function placeHour(iso: string, offsetS: number) {
  const d = new Date(new Date(iso).getTime() + offsetS * 1000);
  const h = d.getUTCHours();
  return `${h % 12 === 0 ? 12 : h % 12} ${h < 12 ? 'am' : 'pm'}`;
}

function Body({ a }: { a: PlaceAirOut }) {
  const c = useColors();
  const scale = useAqiScale((s) => s.scale);
  const now = useAqi(a.now?.pm25 ?? 0);
  if (!a.now) return <AppText muted>No air data for this spot.</AppText>;
  const step = airStep(a.now.pm25);
  const max = Math.max(60, ...a.days.map((d) => d.avg_pm25));
  const best = a.days[0]?.best_hours ?? [];
  return (
    <>
      <View style={styles.now}>
        <AppText variant="display">{now.value}</AppText>
        <View style={{ flex: 1, gap: 4 }}>
          <AqiPill pm25={a.now.pm25} />
          <AppText variant="caption" muted>
            {now.scaleName} now · PM2.5 {Math.round(a.now.pm25)} µg/m³ · {step.hint}
          </AppText>
        </View>
      </View>

      <View style={styles.days} accessibilityLabel="Average AQI for the next days">
        {a.days.slice(0, 5).map((d, i) => {
          const s = aqi(d.avg_pm25, scale);
          return (
            <View key={d.date} style={styles.day}>
              <View style={[styles.track, { backgroundColor: c.field }]}>
                <View
                  style={{
                    height: `${Math.max(8, (d.avg_pm25 / max) * 100)}%`,
                    backgroundColor: s.color,
                    borderRadius: radius.pill,
                  }}
                />
              </View>
              <AppText variant="label">{s.value}</AppText>
              <AppText variant="caption" muted>
                {weekday(d.date, i)}
              </AppText>
            </View>
          );
        })}
      </View>

      {best.length ? (
        <AppText variant="caption" muted>
          Cleanest hours today: {best.map((h) => placeHour(h, a.utc_offset_s)).join(', ')}
        </AppText>
      ) : null}
    </>
  );
}

const styles = StyleSheet.create({
  card: { gap: space.md },
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  close: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  now: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  days: { flexDirection: 'row', justifyContent: 'space-between', gap: space.sm },
  day: { flex: 1, alignItems: 'center', gap: 2 },
  track: {
    height: 54,
    width: 14,
    borderRadius: radius.pill,
    justifyContent: 'flex-end',
    overflow: 'hidden',
  },
});
