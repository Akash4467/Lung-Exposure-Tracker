import { useQuery } from '@tanstack/react-query';
import { View } from 'react-native';

import { QueryState } from '@/components/query-state';
import { TripsCard } from '@/components/trips';
import { BandBadge, HourChart, hourLabel } from '@/components/score';
import { AppText, Card, Disclaimer, Screen } from '@/components/ui';
import { scoreApi } from '@/lib/api/endpoints';
import type { ScoreOut } from '@/lib/api/types';
import { keys } from '@/lib/query';
import { space, useColors } from '@/theme';

export default function Tomorrow() {
  const fc = useQuery({ queryKey: keys.forecast, queryFn: scoreApi.forecast });
  return (
    <Screen
      edges={['top']}
      air={outdoorAverage(fc.data) ?? 'breeze'}
      refreshing={fc.isRefetching}
      onRefresh={() => fc.refetch()}>
      <AppText variant="title">Tomorrow</AppText>
      <QueryState query={fc}>{(f) => <Body f={f} />}</QueryState>
      <TripsCard />
    </Screen>
  );
}

/** Tomorrow's sky shows the outdoor air forecast (not the indoor-filtered dose). */
function outdoorAverage(f: ScoreOut | undefined): number | undefined {
  if (!f?.hours.length) return f?.avg_pm25;
  return f.hours.reduce((a, h) => a + h.pm25, 0) / f.hours.length;
}

const ADVICE = {
  green: 'Air looks fine for your usual day.',
  amber: 'Plan outdoor time for the cleaner hours below.',
  red: 'A poor-air day. Keep windows closed in the worst hours and move outdoor activity to the cleaner ones.',
} as const;

function Body({ f }: { f: ScoreOut }) {
  const c = useColors();
  const smoke = f.fire_risk === 'medium' || f.fire_risk === 'high';
  return (
    <>
      {smoke ? (
        <View style={{ backgroundColor: c.band.red.bg, padding: space.md, borderRadius: 16 }}>
          <AppText variant="heading" color={c.band.red.fg}>
            Smoke risk: {f.fire_risk}
          </AppText>
          <AppText color={c.band.red.fg}>
            Fires upwind may bring smoke. Keep windows closed if the air smells of smoke.
          </AppText>
        </View>
      ) : null}

      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
          <View>
            <AppText variant="caption" muted>
              Forecast Lung Load
            </AppText>
            <AppText variant="display">{f.score}</AppText>
          </View>
          <BandBadge band={f.band} />
        </View>
        <AppText>{ADVICE[f.band]}</AppText>
        <AppText variant="caption" muted>
          Likely between {Math.round(f.range.p10)} and {Math.round(f.range.p90)}
        </AppText>
      </Card>

      <Card>
        <AppText variant="heading">Outdoor air, hour by hour</AppText>
        <HourChart hours={f.hours} best={f.best_outdoor_hours} worst={f.worst_hours} />
        <View style={{ flexDirection: 'row', gap: space.md }}>
          <HourList title="Best to be outside" hours={f.best_outdoor_hours} color={c.band.green.fg} />
          <HourList title="Worst" hours={f.worst_hours} color={c.band.red.fg} />
        </View>
      </Card>
      <Disclaimer />
    </>
  );
}

function HourList({ title, hours, color }: { title: string; hours: ScoreOut['hours']; color: string }) {
  return (
    <View style={{ flex: 1, gap: 4 }}>
      <AppText variant="label" color={color}>
        {title}
      </AppText>
      {hours.map((h) => (
        <AppText key={h.start} variant="caption">
          {hourLabel(h.start)} · {Math.round(h.pm25)} µg/m³
        </AppText>
      ))}
    </View>
  );
}
