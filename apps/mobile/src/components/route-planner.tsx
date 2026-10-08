/**
 * Plan a trip by the air, like directions in a maps app: From (your location or any place) →
 * To, then the drives (fastest and cleanest marked), and what each way of travelling would put
 * in your lungs for the whole trip. Kept compact so the route itself stays visible on the map.
 */
import { useQuery } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Keyboard,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withTiming,
} from 'react-native-reanimated';

import { AqiPill } from '@/components/aqi-pill';
import { AppText, Card, ErrorBanner } from '@/components/ui';
import type { RoutePlanOut } from '@/lib/api/types';
import { currentPosition, LocationDenied, searchPlaces } from '@/lib/geocode';
import { MODES } from '@/lib/labels';
import { useDebounced } from '@/lib/use-debounced';
import { radius, space, useColors } from '@/theme';

export interface Endpoint {
  label: string;
  lat: number;
  lon: number;
}

type Field = 'from' | 'to';

const SHEET_BG = '#FAFAFB';

const modeLabel = (m: string) =>
  m === 'walk'
    ? 'Walk'
    : m === 'cycle'
      ? 'Cycle'
      : m === 'two_wheeler'
        ? '2-wheeler'
        : (MODES.find((x) => x.value === m)?.label ?? m);

export function minutes(m: number) {
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`;
}

/** Top panel: the two ends of the trip. Collapses to one line once both are set. */
export function RoutePanel({
  from,
  to,
  near,
  onChange,
  onClose,
}: {
  from: Endpoint | null;
  to: Endpoint | null;
  near?: { lat: number; lon: number };
  onChange: (field: Field, e: Endpoint) => void;
  onClose: () => void;
}) {
  const c = useColors();
  const [editing, setEditing] = useState<Field | null>(to ? null : 'to');
  const [query, setQuery] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const q = useDebounced(query, 450);
  const results = useQuery({
    queryKey: ['route-search', q, near?.lat, near?.lon],
    queryFn: ({ signal }) => searchPlaces(q, signal, near),
    enabled: !!editing && q.trim().length >= 3,
    staleTime: 60 * 60_000,
  });

  const choose = (e: Endpoint) => {
    if (!editing) return;
    Keyboard.dismiss();
    onChange(editing, e);
    setQuery('');
    setEditing(null);
  };

  const here = async () => {
    setError(null);
    setLocating(true);
    try {
      choose({ label: 'My location', ...(await currentPosition()) });
    } catch (e) {
      setError(
        e instanceof LocationDenied
          ? 'Location permission is off; search for the place instead.'
          : 'Could not get your location; search instead.',
      );
    } finally {
      setLocating(false);
    }
  };

  // Both ends chosen and not editing: one compact line, tap to change.
  if (from && to && !editing) {
    return (
      <Card strong style={{ ...styles.compact, backgroundColor: SHEET_BG }}>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={`From ${from.label} to ${to.label}. Change`}
          onPress={() => setEditing('to')}
          style={styles.compactTrip}>
          <View style={[styles.dot, styles.dotFrom]} />
          <AppText variant="label" numberOfLines={1} style={{ flexShrink: 1 }}>
            {from.label}
          </AppText>
          <AppText variant="label" muted>
            →
          </AppText>
          <View style={[styles.dot, { backgroundColor: c.text }]} />
          <AppText variant="label" numberOfLines={1} style={{ flexShrink: 1 }}>
            {to.label}
          </AppText>
        </Pressable>
        <Pressable accessibilityLabel="Close directions" hitSlop={10} onPress={onClose}>
          <AppText variant="heading">✕</AppText>
        </Pressable>
      </Card>
    );
  }

  const row = (field: Field, value: Endpoint | null, placeholder: string) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${field === 'from' ? 'From' : 'To'}: ${value?.label ?? placeholder}`}
      onPress={() => {
        setEditing(field);
        setQuery('');
      }}
      style={[
        styles.row,
        { backgroundColor: c.field, borderColor: editing === field ? c.text : 'transparent' },
      ]}>
      <View style={[styles.dot, field === 'from' ? styles.dotFrom : { backgroundColor: c.text }]} />
      {editing === field ? (
        <TextInput
          autoFocus
          value={query}
          onChangeText={setQuery}
          placeholder={placeholder}
          placeholderTextColor="#8A8F98"
          maxFontSizeMultiplier={1.3}
          style={[styles.input, { color: c.text }]}
        />
      ) : (
        <AppText numberOfLines={1} muted={!value} style={{ flex: 1 }}>
          {value?.label ?? placeholder}
        </AppText>
      )}
    </Pressable>
  );

  return (
    <View style={{ gap: space.sm }}>
      <Card strong style={{ padding: space.md, gap: space.sm, backgroundColor: SHEET_BG }}>
        <View style={styles.head}>
          <AppText variant="heading" style={{ flex: 1 }}>
            Route by the air
          </AppText>
          <Pressable accessibilityLabel="Close directions" hitSlop={10} onPress={onClose}>
            <AppText variant="heading">✕</AppText>
          </Pressable>
        </View>
        {row('from', from, 'From: search a place')}
        {row('to', to, 'To: where are you going?')}
        <ErrorBanner message={error} />
      </Card>
      {editing ? (
        <Card strong style={{ padding: space.sm, gap: 0, backgroundColor: SHEET_BG }}>
          <Pressable
            accessibilityRole="button"
            onPress={here}
            style={({ pressed }) => [styles.result, pressed && { backgroundColor: c.field }]}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.sm }}>
              <AppText>◎ My location</AppText>
              {locating ? <ActivityIndicator color={c.text} size="small" /> : null}
            </View>
          </Pressable>
          {results.isFetching && !results.data?.length ? (
            <View style={[styles.result, styles.searching]}>
              <ActivityIndicator color={c.text} size="small" />
              <AppText muted>Searching…</AppText>
            </View>
          ) : null}
          {(results.data ?? []).slice(0, 5).map((p, i) => (
            <Pressable
              key={`${i}:${p.lat},${p.lon}`}
              accessibilityRole="button"
              onPress={() => choose({ label: p.label, lat: p.lat, lon: p.lon })}
              style={({ pressed }) => [styles.result, pressed && { backgroundColor: c.field }]}>
              <AppText numberOfLines={1}>{p.label}</AppText>
              {p.detail ? (
                <AppText variant="caption" muted numberOfLines={1}>
                  {p.detail}
                </AppText>
              ) : null}
            </Pressable>
          ))}
        </Card>
      ) : null}
    </View>
  );
}

const LOADING_STEPS = [
  'Finding roads…',
  'Checking the air along each route…',
  'Comparing ways to travel…',
];

/** While routes load: a breeze sweeping across, the step being worked on, ghost cards. */
function RouteLoading() {
  const c = useColors();
  const [stepIdx, setStepIdx] = useState(0);
  const sweep = useSharedValue(0);
  const pulse = useSharedValue(0.45);

  useEffect(() => {
    sweep.value = withRepeat(
      withTiming(1, { duration: 1400, easing: Easing.inOut(Easing.quad) }),
      -1,
    );
    pulse.value = withRepeat(
      withSequence(withTiming(1, { duration: 700 }), withTiming(0.45, { duration: 700 })),
      -1,
    );
    const t = setInterval(() => setStepIdx((s) => (s + 1) % LOADING_STEPS.length), 1600);
    return () => clearInterval(t);
  }, [sweep, pulse]);

  const breeze = useAnimatedStyle(() => ({
    transform: [{ translateX: -120 + sweep.value * 360 }],
    opacity: 1 - Math.abs(sweep.value - 0.5) * 1.2,
  }));
  const ghost = useAnimatedStyle(() => ({ opacity: pulse.value }));

  return (
    <Card strong style={{ gap: space.md, padding: space.md, backgroundColor: SHEET_BG }}>
      <View style={[styles.track, { backgroundColor: c.field, height: 6 }]}>
        <Animated.View style={[styles.breeze, breeze]} />
      </View>
      <AppText variant="label" accessibilityLiveRegion="polite">
        {LOADING_STEPS[stepIdx]}
      </AppText>
      <View style={{ flexDirection: 'row', gap: space.sm }}>
        {[0, 1, 2].map((i) => (
          <Animated.View key={i} style={[styles.ghost, { backgroundColor: c.field }, ghost]} />
        ))}
      </View>
    </Card>
  );
}

/** Bottom sheet: swipeable route cards, the best way to go, and (on demand) every way. */
export function RouteSheet({
  plan,
  selected,
  onSelect,
  loading,
  error,
}: {
  plan: RoutePlanOut | undefined;
  selected: string | null;
  onSelect: (id: string) => void;
  loading: boolean;
  error: string | null;
}) {
  const c = useColors();
  const [compare, setCompare] = useState(false);
  if (error) {
    return (
      <Card strong style={{ backgroundColor: SHEET_BG }}>
        <ErrorBanner message={error} />
      </Card>
    );
  }
  if (loading || !plan) return <RouteLoading />;

  const choices = plan.options.filter((o) => o.profile === 'driving-car' || o.id === selected);
  const best = plan.modes[0];
  const worst = Math.max(...plan.modes.map((m) => m.dose_ug), 1);
  return (
    <Card strong style={{ gap: space.sm, padding: space.md, backgroundColor: SHEET_BG }}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: space.sm }}>
        {choices.map((o) => {
          const on = o.id === selected;
          return (
            <Pressable
              key={o.id}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => onSelect(o.id)}
              style={[
                styles.option,
                {
                  borderColor: on ? c.text : c.border,
                  borderWidth: on ? 1.5 : 1,
                  backgroundColor: on ? '#FFFFFF' : SHEET_BG,
                },
              ]}>
              <AppText variant="caption" muted numberOfLines={1}>
                {o.cleanest ? 'Cleanest air' : o.fastest ? 'Fastest' : 'Other route'}
              </AppText>
              <AppText variant="heading" numberOfLines={1}>
                {minutes(o.duration_min)}
              </AppText>
              <AppText variant="caption" muted numberOfLines={1}>
                {o.distance_km} km
              </AppText>
              {o.avg_pm25 !== null ? <AqiPill pm25={o.avg_pm25} small short /> : null}
            </Pressable>
          );
        })}
      </ScrollView>
      {plan.cleaner_by_pct > 0 ? (
        <AppText variant="caption" color={c.accent}>
          The cleanest route has {Math.round(plan.cleaner_by_pct)}% cleaner air than the fastest.
        </AppText>
      ) : null}
      {best ? (
        <AppText variant="caption">
          Least smoke for this trip:{' '}
          <AppText variant="caption" style={{ fontWeight: '600' }}>
            {modeLabel(best.mode)} ({Math.round(best.dose_ug)} µg, {minutes(best.duration_min)})
          </AppText>
        </AppText>
      ) : null}
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: compare }}
        onPress={() => setCompare((x) => !x)}
        hitSlop={6}>
        <AppText variant="label" style={{ textDecorationLine: 'underline' }}>
          {compare ? 'Hide ways of travelling ▴' : 'Compare ways of travelling ▾'}
        </AppText>
      </Pressable>
      {compare ? (
        <View style={{ gap: 6 }}>
          {plan.modes.map((m) => (
            <View key={m.mode} style={styles.mode}>
              <AppText variant="caption" style={{ width: 76 }} numberOfLines={1}>
                {modeLabel(m.mode)}
              </AppText>
              <View style={[styles.track, { backgroundColor: c.field }]}>
                <View
                  style={{
                    width: `${Math.max(3, (m.dose_ug / worst) * 100)}%`,
                    height: '100%',
                    borderRadius: radius.pill,
                    backgroundColor: '#9AA1AB',
                  }}
                />
              </View>
              <AppText
                variant="caption"
                numberOfLines={1}
                style={{ width: 118, textAlign: 'right' }}>
                {Math.round(m.dose_ug)} µg · {minutes(m.duration_min)}
              </AppText>
            </View>
          ))}
          {plan.routes_from === 'straight_line' ? (
            <AppText variant="caption" muted>
              Routes are approximate (straight lines).
            </AppText>
          ) : null}
        </View>
      ) : null}
    </Card>
  );
}

/** Map shapes: the selected route coloured by roadside PM2.5, the other drives in grey. */
export function planShapes(plan: RoutePlanOut | undefined, selected: string | null) {
  const others: GeoJSON.Feature[] = [];
  const chosen: GeoJSON.Feature[] = [];
  for (const o of plan?.options ?? []) {
    if (o.id === selected) {
      for (let i = 1; i < o.path.length; i++) {
        const [la, lo, pa] = o.path[i - 1];
        const [lb, lob, pb] = o.path[i];
        chosen.push({
          type: 'Feature',
          geometry: {
            type: 'LineString',
            coordinates: [
              [lo, la],
              [lob, lb],
            ],
          },
          properties: { pm25: pb ?? pa ?? 0 },
        });
      }
    } else if (o.profile === 'driving-car') {
      others.push({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: o.path.map(([la, lo]) => [lo, la]) },
        properties: {},
      });
    }
  }
  return {
    others: { type: 'FeatureCollection', features: others } as GeoJSON.FeatureCollection,
    chosen: { type: 'FeatureCollection', features: chosen } as GeoJSON.FeatureCollection,
  };
}

/** [west, south, east, north] around a route option, for fitting the camera. */
export function routeBounds(plan: RoutePlanOut | undefined, id: string | null) {
  const o = plan?.options.find((x) => x.id === id);
  if (!o?.path.length) return null;
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const [lat, lon] of o.path) {
    w = Math.min(w, lon);
    e = Math.max(e, lon);
    s = Math.min(s, lat);
    n = Math.max(n, lat);
  }
  return [w, s, e, n] as [number, number, number, number];
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center' },
  compact: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    paddingVertical: space.sm,
    paddingHorizontal: space.lg,
    borderRadius: radius.pill,
  },
  compactTrip: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 40 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    borderRadius: radius.md,
    borderWidth: 1.5,
    paddingHorizontal: space.md,
    minHeight: 46,
  },
  dot: { width: 10, height: 10, borderRadius: 5 },
  dotFrom: { borderWidth: 2, borderColor: '#121417', backgroundColor: '#FFFFFF' },
  input: { flex: 1, fontSize: 16, minHeight: 44, fontFamily: 'Inter_400Regular' },
  result: { paddingVertical: space.sm, paddingHorizontal: space.md, borderRadius: radius.sm },
  searching: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  option: { width: 148, gap: 2, borderRadius: radius.md, padding: space.md },
  mode: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  track: { flex: 1, height: 8, borderRadius: radius.pill, overflow: 'hidden' },
  breeze: { width: 120, height: '100%', borderRadius: radius.pill, backgroundColor: '#5DB596' },
  ghost: { flex: 1, height: 92, borderRadius: radius.md },
});
