import { useQuery } from '@tanstack/react-query';
import { Link, router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';

import { AlertsCard } from '@/components/alerts-card';
import { AqiPill, useAqi } from '@/components/aqi-pill';
import { LoadBreakdown } from '@/components/load-breakdown';
import { LocationChip, useTodayLocation } from '@/components/location-switch';
import { QueryState } from '@/components/query-state';
import {
  ActivitySplit,
  BandBadge,
  LungLoadRing,
  SplitBar,
  timeAgo,
  TipCard,
} from '@/components/score';
import { AppText, Button, Card, Disclaimer, Overline, Screen } from '@/components/ui';
import { authApi, mapApi, meApi, scoreApi } from '@/lib/api/endpoints';
import type { ScoreOut } from '@/lib/api/types';
import { keys } from '@/lib/query';
import { BAND_LABEL, radius, space, useColors } from '@/theme';

const HEADLINE = {
  green: 'Your lungs had an easy day.',
  amber: 'Your lungs took in more than the WHO guideline.',
  red: 'Your lungs took in a heavy load today.',
} as const;

export default function Today() {
  const today = useQuery({
    queryKey: keys.today,
    queryFn: scoreApi.today,
    refetchInterval: 15 * 60_000,
  });
  const me = useQuery({ queryKey: keys.me, queryFn: authApi.me });
  const date = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'short',
  });
  return (
    <Screen
      edges={['top']}
      air={today.data?.avg_pm25 ?? 'breeze'}
      refreshing={today.isRefetching}
      onRefresh={() => today.refetch()}>
      <View style={styles.header}>
        <View style={{ gap: 2, flex: 1 }}>
          <Overline>{date}</Overline>
          <AppText variant="title">Today</AppText>
        </View>
        <LocationChip />
      </View>
      {me.data && !me.data.email_verified ? <VerifyBanner /> : null}
      {today.data?.trip ? <TripBanner label={today.data.trip.label} /> : null}
      <OutsideNow />
      <QueryState query={today}>{(s) => <TodayBody s={s} />}</QueryState>
    </Screen>
  );
}

function VerifyBanner() {
  const c = useColors();
  return (
    <Link href="/verify-email" asChild>
      <Pressable
        accessibilityRole="link"
        style={[styles.banner, { backgroundColor: c.band.amber.bg, borderColor: c.glassBorder }]}>
        <AppText color={c.band.amber.fg}>
          Confirm your email so you can reset your password if you ever need to. Tap to enter
          the code.
        </AppText>
      </Pressable>
    </Link>
  );
}

function TripBanner({ label }: { label: string }) {
  const c = useColors();
  return (
    <View style={[styles.banner, { backgroundColor: c.glassStrong, borderColor: c.glassBorder }]}>
      <AppText>
        Away today: <AppText style={{ fontWeight: '600' }}>{label}</AppText>. Your Lung Load uses
        the air there, as a day off.
      </AppText>
    </View>
  );
}

/** The outdoor air where you are now (home, or the trip destination), as AQI. */
function OutsideNow() {
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  const loc = useTodayLocation();
  const away = loc.data?.kind === 'trip' ? loc.data.trip : undefined;
  const home = away ?? profile.data?.places.home;
  const air = useQuery({
    queryKey: ['map-place', home?.lat.toFixed(2), home?.lon.toFixed(2)],
    queryFn: () => mapApi.place(home!.lat, home!.lon),
    enabled: !!home,
    staleTime: 15 * 60_000,
  });
  const now = air.data?.now;
  const a = useAqi(now?.pm25 ?? 0);
  if (!now) return null;
  return (
    <Card style={{ padding: space.md, gap: space.xs }}>
      <View style={styles.rowBetween}>
        <AppText variant="caption" muted>
          {away ? `Outside now · ${away.label}` : 'Outside your home now'}
        </AppText>
        <AppText variant="caption" muted>
          {a.scaleName}
        </AppText>
      </View>
      <View style={[styles.rowBetween, { flexWrap: 'nowrap' }]}>
        <AqiPill pm25={now.pm25} />
        <AppText variant="caption" muted>
          PM2.5 {Math.round(now.pm25)} µg/m³
        </AppText>
      </View>
    </Card>
  );
}

function Stat({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <Card style={{ flex: 1, padding: space.md, gap: 2 }}>
      <AppText variant="caption" muted numberOfLines={1}>
        {label}
      </AppText>
      <AppText variant="title" numberOfLines={1} adjustsFontSizeToFit>
        {value}
      </AppText>
      <AppText variant="caption" muted numberOfLines={1}>
        {unit}
      </AppText>
    </Card>
  );
}

function TodayBody({ s }: { s: ScoreOut }) {
  const c = useColors();
  const odds = s.band_probability[s.band];
  const hasActivity = Object.keys(s.by_activity ?? {}).length > 0;
  return (
    <>
      <View style={{ alignItems: 'center', gap: space.sm }}>
        <LungLoadRing score={s.score} band={s.band} breathingLpm={s.breathing_lpm} />
        <BandBadge band={s.band} center />
        <AppText variant="heading" style={{ textAlign: 'center', fontWeight: '400' }}>
          {HEADLINE[s.band]}
        </AppText>
        <AppText variant="caption" muted style={{ textAlign: 'center' }}>
          Likely between {Math.round(s.range.p10)} and {Math.round(s.range.p90)}
          {odds !== undefined
            ? ` · ${Math.round(odds * 100)}% chance it's ${BAND_LABEL[s.band].toLowerCase()}`
            : ''}
        </AppText>
      </View>

      <View style={{ flexDirection: 'row', gap: space.sm }}>
        <Stat
          label="Breathing"
          value={s.breathing_lpm ? s.breathing_lpm.toFixed(1) : '–'}
          unit="L / min"
        />
        <Stat label="Your air" value={String(Math.round(s.avg_pm25))} unit="µg/m³ avg" />
        <Stat label="Like" value={s.cigarettes.toFixed(1)} unit="cigarettes" />
      </View>

      <Card>
        <View style={styles.rowBetween}>
          <AppText variant="heading" style={{ flexShrink: 1 }}>
            What you were doing
          </AppText>
          <Button
            title="Log activity"
            kind="secondary"
            compact
            onPress={() => router.push('/log-activity')}
          />
        </View>
        {hasActivity ? <ActivitySplit split={s.by_activity} /> : null}
        <AppText variant="caption" muted>
          {s.air_litres
            ? `About ${Math.round(s.air_litres).toLocaleString()} litres of air so far. `
            : ''}
          Running or walking outside makes you breathe more of whatever air is around.
        </AppText>
      </Card>

      <LoadBreakdown s={s} />

      <Card>
        <AppText variant="heading">Where it came from</AppText>
        <SplitBar split={s.split} />
        {s.indoor_source_share >= 0.05 ? (
          <AppText variant="caption" color={c.band.amber.fg}>
            {Math.round(s.indoor_source_share * 100)}% came from smoke or fumes inside your home.
          </AppText>
        ) : null}
      </Card>

      <AlertsCard />

      {s.tips.length ? (
        <View style={{ gap: space.sm }}>
          <Overline>What would help most</Overline>
          {s.tips.map((t) => (
            <TipCard key={t.id} tip={t} />
          ))}
        </View>
      ) : null}
      <View style={{ gap: space.xs }}>
        <Button
          title="Try what-ifs  →"
          accessibilityHint="See how a different commute time, a purifier or a mask would change today"
          onPress={() => router.push('/simulate')}
        />
        <AppText variant="caption" muted style={{ textAlign: 'center' }}>
          Change your commute time, add a purifier or a mask, and see the difference
        </AppText>
      </View>

      <AppText variant="caption" muted style={{ textAlign: 'center' }}>
        Air data updated {timeAgo(s.data_as_of)} · Open-Meteo
      </AppText>
      <Disclaimer />
    </>
  );
}

const styles = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'flex-end', gap: space.md },
  banner: { padding: space.md, borderRadius: radius.md, borderWidth: 1 },
  rowBetween: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.sm,
  },
});
