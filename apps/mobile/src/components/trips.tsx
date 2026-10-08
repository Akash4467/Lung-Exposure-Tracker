/**
 * Trips out of town: plan one from a place on the map, see them listed with the
 * destination's air for each day. On trip days the Lung Load uses the destination's air.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { AqiPill } from '@/components/aqi-pill';
import { AppText, Button, Card, ErrorBanner, Overline, Segmented } from '@/components/ui';
import { aqi, useAqiScale } from '@/lib/aqi';
import { mapApi, tripsApi } from '@/lib/api/endpoints';
import type { TripOut } from '@/lib/api/types';
import { errorMessage, keys } from '@/lib/query';
import { radius, space, useColors } from '@/theme';

/** YYYY-MM-DD for a date `days` from today, in the phone's own time. */
export function isoDay(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

const nice = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });

const STARTS = [
  { value: '0', label: 'Today' },
  { value: '1', label: 'Tomorrow' },
  { value: '3', label: 'In 3 days' },
  { value: '7', label: 'Next week' },
] as const;
const NIGHTS = [
  { value: '1', label: '1 day' },
  { value: '2', label: '2 days' },
  { value: '3', label: '3 days' },
  { value: '5', label: '5 days' },
  { value: '7', label: 'A week' },
] as const;

function useRefreshTrips() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.trips }),
      qc.invalidateQueries({ queryKey: keys.today }),
      qc.invalidateQueries({ queryKey: keys.forecast }),
      qc.invalidateQueries({ queryKey: keys.location }),
    ]);
}

/** Inside a place card on the map: "Plan a trip here". */
export function TripPlanner({
  place,
  onDone,
}: {
  place: { label: string; lat: number; lon: number };
  onDone: () => void;
}) {
  const refresh = useRefreshTrips();
  const [start, setStart] = useState<(typeof STARTS)[number]['value']>('1');
  const [length, setLength] = useState<(typeof NIGHTS)[number]['value']>('3');
  const save = useMutation({
    mutationFn: () =>
      tripsApi.add({
        label: place.label,
        lat: place.lat,
        lon: place.lon,
        start_date: isoDay(Number(start)),
        end_date: isoDay(Number(start) + Number(length) - 1),
      }),
    onSuccess: async () => {
      await refresh();
      onDone();
    },
  });
  return (
    <View style={{ gap: space.sm }}>
      <ErrorBanner message={errorMessage(save.error)} />
      <Segmented label="Starts" options={STARTS} value={start} onChange={setStart} />
      <Segmented label="How long" options={NIGHTS} value={length} onChange={setLength} />
      <AppText variant="caption" muted>
        {nice(isoDay(Number(start)))} – {nice(isoDay(Number(start) + Number(length) - 1))}. Those
        days your Lung Load will use {place.label}'s air.
      </AppText>
      <Button title={`Add trip to ${place.label}`} onPress={() => save.mutate()} loading={save.isPending} />
    </View>
  );
}

/** On Tomorrow: trips now and coming up, with each day's air at the destination. */
export function TripsCard() {
  const trips = useQuery({ queryKey: keys.trips, queryFn: tripsApi.list });
  if (!trips.data?.trips.length) return null;
  return (
    <View style={{ gap: space.sm }}>
      <Overline>Your trips</Overline>
      {trips.data.trips.map((t) => (
        <TripItem key={t.id} t={t} />
      ))}
    </View>
  );
}

function TripItem({ t }: { t: TripOut }) {
  const c = useColors();
  const scale = useAqiScale((s) => s.scale);
  const refresh = useRefreshTrips();
  const air = useQuery({
    queryKey: ['map-place', t.lat.toFixed(2), t.lon.toFixed(2)],
    queryFn: () => mapApi.place(t.lat, t.lon),
    staleTime: 15 * 60_000,
  });
  const remove = useMutation({ mutationFn: () => tripsApi.remove(t.id), onSuccess: refresh });
  const tripDays = (air.data?.days ?? []).filter(
    (d) => d.date >= t.start_date && d.date <= t.end_date,
  );
  return (
    <Card>
      <View style={styles.head}>
        <View style={{ flex: 1 }}>
          <AppText variant="heading" numberOfLines={1}>
            {t.label}
          </AppText>
          <AppText variant="caption" muted>
            {t.status === 'now' ? 'Now · ' : ''}
            {nice(t.start_date)}
            {t.days > 1 ? ` – ${nice(t.end_date)}` : ''}
          </AppText>
        </View>
        {air.data?.now ? <AqiPill pm25={air.data.now.pm25} small /> : null}
      </View>
      {tripDays.length ? (
        <View style={styles.days}>
          {tripDays.map((d) => {
            const a = aqi(d.avg_pm25, scale);
            return (
              <View key={d.date} style={styles.day}>
                <View style={[styles.dot, { backgroundColor: a.color }]} />
                <AppText variant="label">{a.value}</AppText>
                <AppText variant="caption" muted>
                  {new Date(`${d.date}T12:00:00`).toLocaleDateString(undefined, { weekday: 'short' })}
                </AppText>
              </View>
            );
          })}
        </View>
      ) : (
        <AppText variant="caption" muted>
          The forecast covers the next 5 days; it'll appear here as the trip gets closer.
        </AppText>
      )}
      <View style={[styles.note, { backgroundColor: c.field }]}>
        <AppText variant="caption">
          On these days your Lung Load uses {t.label}'s air: a day off there, indoors with
          normal windows.
        </AppText>
      </View>
      <View style={{ alignSelf: 'flex-start' }}>
        <Button
          title="Remove trip"
          kind="ghost"
          compact
          loading={remove.isPending}
          onPress={() => remove.mutate()}
        />
      </View>
    </Card>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  days: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md },
  day: { alignItems: 'center', gap: 2, minWidth: 44 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  note: { borderRadius: radius.md, padding: space.md },
});
