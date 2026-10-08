/** Lung Load over the last two weeks: a bar per day against the WHO line, plus insights. */
import { useQuery } from '@tanstack/react-query';
import { StyleSheet, View } from 'react-native';
import Svg, { Line, Rect } from 'react-native-svg';

import { QueryState } from '@/components/query-state';
import { BandBadge } from '@/components/score';
import { AppText, Card, Disclaimer, Overline, Screen } from '@/components/ui';
import { scoreApi } from '@/lib/api/endpoints';
import type { DayOut, HistoryOut } from '@/lib/api/types';
import { keys } from '@/lib/query';
import { space, useColors } from '@/theme';

const DAYS = 14;

export default function Trends() {
  const h = useQuery({ queryKey: keys.history, queryFn: () => scoreApi.history(DAYS) });
  const days = h.data?.days ?? [];
  const air = days.length ? days.reduce((a, d) => a + d.avg_pm25, 0) / days.length : 'breeze';
  return (
    <Screen edges={['top']} air={air} refreshing={h.isRefetching} onRefresh={() => h.refetch()}>
      <View style={{ gap: 2 }}>
        <Overline>Last {DAYS} days</Overline>
        <AppText variant="title">Trends</AppText>
      </View>
      <QueryState query={h}>{(data) => <Body h={data} />}</QueryState>
    </Screen>
  );
}

const shortDate = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

function Body({ h }: { h: HistoryOut }) {
  const c = useColors();
  const ins = h.insights;
  if (h.days.length < 2) {
    return (
      <Card>
        <AppText variant="heading">Your trends build up day by day</AppText>
        <AppText muted>
          Come back tomorrow to compare. After a week you'll see how this week went against the
          last one.
        </AppText>
      </Card>
    );
  }
  const better = ins.change_pct !== null && ins.change_pct < 0;
  return (
    <>
      <Card>
        <Overline>This week</Overline>
        <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: space.md }}>
          <AppText variant="display">{ins.avg_score_7d ?? '–'}</AppText>
          <AppText muted style={{ paddingBottom: 8 }}>
            average Lung Load
          </AppText>
        </View>
        {ins.change_pct !== null ? (
          <AppText variant="heading" color={better ? c.band.green.fg : c.band.red.fg}>
            {better ? '↓' : '↑'} {Math.abs(Math.round(ins.change_pct))}%{' '}
            {better ? 'lighter' : 'heavier'} than last week
          </AppText>
        ) : (
          <AppText variant="caption" muted>
            Compared with last week once you have two weeks of days.
          </AppText>
        )}
        <DayBars days={h.days} />
      </Card>

      <View style={{ flexDirection: 'row', gap: space.sm }}>
        {ins.best_day ? (
          <Card style={{ flex: 1, padding: space.md, gap: 2 }}>
            <AppText variant="caption" muted>
              Easiest day
            </AppText>
            <AppText variant="title">{ins.best_day.score}</AppText>
            <AppText variant="caption" muted>
              {shortDate(ins.best_day.date)}
            </AppText>
          </Card>
        ) : null}
        {ins.worst_day ? (
          <Card style={{ flex: 1, padding: space.md, gap: 2 }}>
            <AppText variant="caption" muted>
              Heaviest day
            </AppText>
            <AppText variant="title">{ins.worst_day.score}</AppText>
            <AppText variant="caption" muted>
              {shortDate(ins.worst_day.date)}
            </AppText>
          </Card>
        ) : null}
      </View>

      <Card>
        <AppText variant="heading">How you breathed</AppText>
        <Insight
          label="Average breathing"
          value={ins.avg_breathing_lpm ? `${ins.avg_breathing_lpm} L/min` : '–'}
        />
        <Insight
          label="Dose while walking, running or cycling"
          value={`${Math.round(ins.exercise_share * 100)}%`}
        />
        {ins.exercise_share >= 0.1 ? (
          <AppText variant="caption" muted>
            A good share of your dose comes while exercising. On high days, the cleaner hours on
            the Tomorrow tab are the best time to go out.
          </AppText>
        ) : null}
      </Card>

      <Card>
        <AppText variant="heading">Days by level</AppText>
        <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
          {(['green', 'amber', 'red'] as const).map((b) => (
            <View key={b} style={{ flexDirection: 'row', alignItems: 'center', gap: space.xs }}>
              <BandBadge band={b} size="sm" />
              <AppText variant="label">× {ins.bands[b] ?? 0}</AppText>
            </View>
          ))}
        </View>
      </Card>
      <Disclaimer />
    </>
  );
}

function Insight({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.insight}>
      <AppText muted style={{ flex: 1 }}>
        {label}
      </AppText>
      <AppText variant="heading">{value}</AppText>
    </View>
  );
}

/** One bar per day, coloured by band, with a dashed line at 100 (WHO-guideline air). */
function DayBars({ days }: { days: DayOut[] }) {
  const c = useColors();
  const height = 140;
  const max = Math.max(200, ...days.map((d) => d.score)) * 1.05;
  const slot = 100 / DAYS;
  const offset = DAYS - days.length; // newest on the right
  const y = (v: number) => height - (v / max) * height;
  return (
    <View
      accessibilityRole="image"
      accessibilityLabel={`Lung Load for the last ${days.length} days, from ${Math.min(...days.map((d) => d.score))} to ${Math.max(...days.map((d) => d.score))}`}>
      <Svg width="100%" height={height}>
        {days.map((d, i) => {
          const bh = Math.max(3, height - y(d.score));
          return (
            <Rect
              key={d.date}
              x={`${(offset + i) * slot + slot * 0.18}%`}
              y={height - bh}
              width={`${slot * 0.64}%`}
              height={bh}
              rx={4}
              fill={c.band[d.band].fg}
              opacity={0.85}
            />
          );
        })}
        <Line
          x1="0"
          x2="100%"
          y1={y(100)}
          y2={y(100)}
          stroke={c.text}
          strokeOpacity={0.45}
          strokeDasharray="4 4"
          strokeWidth={1}
        />
      </Svg>
      <View style={styles.axis}>
        <AppText variant="caption" muted>
          2 weeks ago
        </AppText>
        <AppText variant="caption" muted>
          - - - WHO line (100)
        </AppText>
        <AppText variant="caption" muted>
          Today
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  insight: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6 },
});
