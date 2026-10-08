/**
 * Commute footprint, in full: every way of making the commute side by side (estimated CO2
 * per week, with its range), the best realistic swap, recorded trips if any, and where the
 * numbers come from. Climate only: Lung Load is a separate measure (see the Map's planner).
 */
import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { Linking, Pressable, StyleSheet, View } from 'react-native';

import { QueryState } from '@/components/query-state';
import { AppText, Button, Card, Overline, Screen } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import type { FootprintMode, FootprintOut } from '@/lib/api/types';
import { byMode, headline, kg, kgRange, modeName } from '@/lib/footprint';
import { keys } from '@/lib/query';
import { radius, space, useColors } from '@/theme';

export default function Footprint() {
  const q = useQuery({ queryKey: keys.footprint, queryFn: meApi.footprint });
  return (
    <Screen edges={['bottom']} refreshing={q.isRefetching} onRefresh={() => q.refetch()}>
      <QueryState query={q}>{(f) => <Body f={f} />}</QueryState>
    </Screen>
  );
}

function Body({ f }: { f: FootprintOut }) {
  const c = useColors();
  const commute = f.commute;
  if (!commute) {
    return (
      <Card>
        <AppText variant="heading">Add your commute first</AppText>
        <AppText muted>
          Once your home, work and the way you travel are set, you&apos;ll see the estimated CO₂ of
          your commute here.
        </AppText>
        <Button
          title="Profile & daily routine"
          kind="secondary"
          onPress={() => router.push('/edit-profile')}
        />
      </Card>
    );
  }
  const h = headline(f);
  const max = Math.max(...commute.modes.map((m) => m.week_kg.high), 0.001);
  return (
    <>
      <Card>
        <Overline>Your commute · estimate</Overline>
        <AppText variant="title">{kg(commute.week_kg.central)} kg CO₂ a week</AppText>
        <AppText muted>
          {commute.one_way_km} km each way {byMode(commute.mode)}, {commute.days_per_week}{' '}
          {commute.days_per_week === 1 ? 'day' : 'days'} a week: {commute.week_km} km. Range{' '}
          {kgRange(commute.week_kg)} kg; about {kg(commute.year_kg.central)} kg a year.
        </AppText>
        {h ? (
          <AppText
            variant="label"
            color={h.tone === 'good' ? c.accent : c.text}
            style={{ fontWeight: '500' }}>
            {h.text}
          </AppText>
        ) : null}
      </Card>

      <Card>
        <AppText variant="heading">Every way, per week</AppText>
        <AppText variant="caption" muted>
          The bar is the best guess; the pale band is the range.
        </AppText>
        <View style={{ gap: space.md }}>
          {commute.modes.map((m) => (
            <ModeRow key={m.mode} m={m} max={max} />
          ))}
        </View>
        <AppText variant="caption" muted>
          Walking and cycling show only when the distance makes them realistic.
        </AppText>
      </Card>

      {f.recorded ? (
        <Card>
          <AppText variant="heading">Your recorded trips</AppText>
          <AppText muted>
            Last {f.recorded.days} days: about {kg(f.recorded.total_kg.central)} kg CO₂ (
            {kgRange(f.recorded.total_kg)}).
          </AppText>
          {f.recorded.by_mode.map((r) => (
            <View key={r.mode} style={styles.row}>
              <AppText style={{ flex: 1 }}>{cap(modeName(r.mode))}</AppText>
              <AppText muted>{r.km} km</AppText>
              <AppText variant="label" style={{ minWidth: 64, textAlign: 'right' }}>
                {kg(r.kg.central)} kg
              </AppText>
            </View>
          ))}
          <AppText variant="caption" muted>
            Recorded vehicle trips count as the vehicle in your profile: the phone can&apos;t tell a
            bus from a car.
          </AppText>
        </Card>
      ) : null}

      <Card>
        <AppText variant="heading">Climate and your lungs are different</AppText>
        <AppText muted>
          CO₂ warms the climate; PM2.5 is what you breathe. The lowest-CO₂ way isn&apos;t always the
          easiest on your lungs: cycling emits nothing but you breathe hard next to traffic.
        </AppText>
        <Button
          title="Compare Lung Load on the Map →"
          kind="secondary"
          compact
          onPress={() => router.push('/map')}
        />
      </Card>

      <Card>
        <AppText variant="heading">How we estimate</AppText>
        {[
          'Distance: your commute route by road, there and back, on your office days.',
          'Car and two-wheeler: fuel burned per km, assuming you travel alone.',
          'Bus: one published average; the range is our assumption for how full the bus is.',
          'Metro: the power stations’ share for the electricity it uses, per passenger.',
          'Not counted: making the vehicles, roads and tracks.',
        ].map((t) => (
          <AppText key={t} variant="caption" muted>
            • {t}
          </AppText>
        ))}
        <Overline>Sources</Overline>
        {f.sources.map((s) => (
          <Pressable
            key={s.url}
            accessibilityRole="link"
            onPress={() => void Linking.openURL(s.url)}
            style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}>
            <AppText variant="caption" color={c.accent}>
              {s.publisher} ({s.year}). {s.title}
            </AppText>
          </Pressable>
        ))}
      </Card>
    </>
  );
}

function ModeRow({ m, max }: { m: FootprintMode; max: number }) {
  const c = useColors();
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%` as const;
  const zero = m.week_kg.high === 0;
  return (
    <View
      accessible
      accessibilityLabel={`${modeName(m.mode)}${m.current ? ', your way' : ''}: about ${kg(m.week_kg.central)} kilograms a week`}>
      <View style={styles.row}>
        <AppText variant="label" style={{ flex: 1 }}>
          {cap(modeName(m.mode))}
          {m.current ? '  · yours' : ''}
        </AppText>
        <AppText variant="label">{zero ? '0 kg' : `${kg(m.week_kg.central)} kg`}</AppText>
      </View>
      <View style={[styles.track, { backgroundColor: c.surfaceMuted }]}>
        <View
          style={[
            styles.band,
            {
              left: pct(m.week_kg.low),
              width: pct(m.week_kg.high - m.week_kg.low),
              backgroundColor: m.current ? 'rgba(18,20,23,0.18)' : 'rgba(47,143,106,0.22)',
            },
          ]}
        />
        <View
          style={[
            styles.bar,
            {
              width: pct(m.week_kg.central),
              backgroundColor: m.current ? c.primary : c.accent,
            },
          ]}
        />
      </View>
      <AppText variant="caption" muted>
        {zero
          ? 'No fuel or electricity'
          : `${kgRange(m.week_kg)} kg · ${m.g_per_km.central} g per km`}
      </AppText>
    </View>
  );
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  track: {
    height: 10,
    borderRadius: radius.pill,
    overflow: 'hidden',
    marginVertical: 4,
  },
  band: { position: 'absolute', top: 0, bottom: 0 },
  bar: {
    position: 'absolute',
    left: 0,
    top: 3,
    bottom: 3,
    borderRadius: radius.pill,
  },
});
