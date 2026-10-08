/** Components that show a score. Band colour is always paired with a text label. */
import { useIsFocused } from 'expo-router';
import { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, RadialGradient, Rect, Stop } from 'react-native-svg';

import { AppText } from '@/components/ui';
import type { Activity, HourOut, ScoreOut, Tip } from '@/lib/api/types';
import { BAND_LABEL, type Band, radius, space, useColors } from '@/theme';

const RING_MAX = 800; // the ring is full at score 800 (2x the red threshold)

export function BandBadge({
  band,
  size = 'md',
  center,
}: {
  band: Band;
  size?: 'sm' | 'md';
  center?: boolean;
}) {
  const c = useColors();
  const { fg, bg } = c.band[band];
  return (
    <View
      style={[
        styles.badge,
        { backgroundColor: bg, paddingVertical: size === 'sm' ? 2 : 4 },
        center && { alignSelf: 'center' },
      ]}
      accessibilityLabel={`${BAND_LABEL[band]} exposure`}>
      <View style={[styles.dot, { backgroundColor: fg }]} />
      <AppText variant={size === 'sm' ? 'caption' : 'label'} color={fg}>
        {BAND_LABEL[band]}
      </AppText>
    </View>
  );
}

/**
 * The Lung Load ring. It slowly expands and relaxes at the person's own breathing pace
 * (litres per minute ÷ ~0.5 L per breath), and holds still when reduced motion is on.
 */
export function LungLoadRing({
  score,
  band,
  breathingLpm,
  size = 230,
}: {
  score: number;
  band: Band;
  breathingLpm?: number | null;
  size?: number;
}) {
  const times = score / 100;
  const c = useColors();
  const reduced = useReducedMotion();
  const focused = useIsFocused();
  const breath = useSharedValue(0);
  const perMin = Math.min(24, Math.max(10, (breathingLpm ?? 7) / 0.5));
  const halfMs = 30_000 / perMin;

  useEffect(() => {
    if (reduced || !focused) {
      cancelAnimation(breath);
      return;
    }
    breath.value = withRepeat(
      withTiming(1, { duration: halfMs, easing: Easing.inOut(Easing.sin) }),
      -1,
      true,
    );
    return () => cancelAnimation(breath);
  }, [reduced, focused, halfMs, breath]);

  const pulse = useAnimatedStyle(() => ({
    transform: [{ scale: 1 + 0.035 * breath.value }],
    opacity: 0.55 + 0.45 * breath.value,
  }));

  const stroke = 10;
  const r = (size - stroke) / 2 - 8;
  const circ = 2 * Math.PI * r;
  const frac = Math.min(score / RING_MAX, 1);
  const fg = c.band[band].fg;
  return (
    <View
      style={{ width: size, height: size, alignItems: 'center', justifyContent: 'center' }}
      accessibilityRole="image"
      accessibilityLabel={`Lung Load ${score}, ${BAND_LABEL[band]}, ${(score / 100).toFixed(1)} times the WHO limit`}>
      <Animated.View style={[StyleSheet.absoluteFill, pulse]}>
        <Svg width={size} height={size}>
          <Defs>
            <RadialGradient id="halo" cx="50%" cy="50%" r="50%">
              <Stop offset="0.6" stopColor={fg} stopOpacity={0.16} />
              <Stop offset="1" stopColor={fg} stopOpacity={0} />
            </RadialGradient>
          </Defs>
          <Circle cx={size / 2} cy={size / 2} r={size / 2} fill="url(#halo)" />
        </Svg>
      </Animated.View>
      <Svg width={size} height={size} style={StyleSheet.absoluteFill}>
        <Circle cx={size / 2} cy={size / 2} r={r} fill="rgba(255,255,255,0.7)" />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke="rgba(18,20,23,0.08)"
          strokeWidth={stroke}
          fill="none"
        />
        <Circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          stroke={fg}
          strokeWidth={stroke}
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${circ * frac} ${circ}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </Svg>
      <AppText variant="overline" muted>
        LUNG LOAD
      </AppText>
      <AppText variant="hero" maxFontSizeMultiplier={1}>
        {score}
      </AppText>
      <AppText
        variant="caption"
        muted
        maxFontSizeMultiplier={1.1}
        style={{ maxWidth: r * 1.3, textAlign: 'center' }}>
        {times >= 1.05 ? `${times.toFixed(1)}× the WHO limit` : 'within the WHO limit'}
      </AppText>
    </View>
  );
}

const ACTIVITY_LABEL: Record<Activity, string> = {
  asleep: 'Asleep',
  light: 'Resting / light',
  walk: 'Walking',
  run: 'Running',
  cycle: 'Cycling',
};

export const activityLabel = (a: Activity) => ACTIVITY_LABEL[a] ?? a;

/** Share of the day's dose by what the person was doing. */
export function ActivitySplit({ split }: { split: Partial<Record<Activity, number>> }) {
  const c = useColors();
  const parts = (Object.keys(ACTIVITY_LABEL) as Activity[])
    .map((a) => ({ key: a, share: split[a] ?? 0, color: c.activity[a] }))
    .filter((p) => p.share > 0.005);
  if (!parts.length) return null;
  return (
    <View style={{ gap: space.sm }}>
      <View style={[styles.bar, { backgroundColor: 'rgba(18,20,23,0.08)' }]}>
        {parts.map((p) => (
          <View key={p.key} style={{ flex: p.share, backgroundColor: p.color }} />
        ))}
      </View>
      <View style={styles.legend}>
        {parts.map((p) => (
          <View key={p.key} style={styles.legendItem}>
            <View style={[styles.dot, { backgroundColor: p.color }]} />
            <AppText variant="caption">
              {ACTIVITY_LABEL[p.key]} {Math.round(p.share * 100)}%
            </AppText>
          </View>
        ))}
      </View>
    </View>
  );
}

export function SplitBar({ split }: { split: ScoreOut['split'] }) {
  const c = useColors();
  const parts = [
    { key: 'home', label: 'Home', share: split.home, color: c.split.home },
    { key: 'commute', label: 'Commute', share: split.commute, color: c.split.commute },
    { key: 'office', label: 'Work', share: split.office, color: c.split.office },
  ] as const;
  return (
    <View style={{ gap: space.sm }}>
      <View style={[styles.bar, { backgroundColor: 'rgba(18,20,23,0.08)' }]}>
        {parts.map((p) =>
          p.share > 0.005 ? (
            <View key={p.key} style={{ flex: p.share, backgroundColor: p.color }} />
          ) : null,
        )}
      </View>
      <View style={styles.legend}>
        {parts.map((p) => (
          <View key={p.key} style={styles.legendItem}>
            <View style={[styles.dot, { backgroundColor: p.color }]} />
            <AppText variant="caption">
              {p.label} {Math.round(p.share * 100)}%
            </AppText>
          </View>
        ))}
      </View>
    </View>
  );
}

export function TipCard({ tip }: { tip: Tip }) {
  const c = useColors();
  return (
    <View style={[styles.tip, { borderColor: c.glassBorder, backgroundColor: c.glass }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <AppText>{tip.text}</AppText>
        {tip.free ? (
          <AppText variant="caption" color={c.accent}>
            Free
          </AppText>
        ) : null}
      </View>
      <View style={[styles.saves, { backgroundColor: c.band.green.bg }]}>
        <AppText variant="label" color={c.band.green.fg}>
          −{Math.round(tip.saves_pct)}%
        </AppText>
      </View>
    </View>
  );
}

/** 24 hourly bars of outdoor PM2.5; best hours green, worst red. */
export function HourChart({
  hours,
  best,
  worst,
}: {
  hours: HourOut[];
  best: HourOut[];
  worst: HourOut[];
}) {
  const c = useColors();
  const h = 120;
  const max = Math.max(60, ...hours.map((x) => x.pm25));
  const bestSet = new Set(best.map((x) => x.start));
  const worstSet = new Set(worst.map((x) => x.start));
  const barW = 100 / Math.max(hours.length, 1);
  return (
    <View
      accessibilityRole="image"
      accessibilityLabel={`Hourly outdoor PM2.5 tomorrow, from ${Math.round(Math.min(...hours.map((x) => x.pm25)))} to ${Math.round(max)}`}>
      <Svg width="100%" height={h}>
        {hours.map((x, i) => {
          const bh = Math.max(2, (x.pm25 / max) * (h - 4));
          const color = worstSet.has(x.start)
            ? c.band.red.fg
            : bestSet.has(x.start)
              ? c.band.green.fg
              : c.textMuted;
          return (
            <Rect
              key={x.start}
              x={`${i * barW + barW * 0.15}%`}
              y={h - bh}
              width={`${barW * 0.7}%`}
              height={bh}
              rx={2}
              fill={color}
              opacity={worstSet.has(x.start) || bestSet.has(x.start) ? 1 : 0.45}
            />
          );
        })}
      </Svg>
      <View style={styles.axis}>
        {['12 am', '6 am', '12 pm', '6 pm', '12 am'].map((l, i) => (
          <AppText key={i} variant="caption" muted>
            {l}
          </AppText>
        ))}
      </View>
    </View>
  );
}

export const hourLabel = (iso: string) => {
  const d = new Date(iso);
  const hh = d.getHours();
  return `${hh % 12 === 0 ? 12 : hh % 12} ${hh < 12 ? 'am' : 'pm'}`;
};

export function timeAgo(iso: string): string {
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 2) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `${h} h ago` : `${Math.round(h / 24)} d ago`;
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    alignSelf: 'flex-start',
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  bar: { flexDirection: 'row', height: 14, borderRadius: radius.pill, overflow: 'hidden' },
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: space.md },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  tip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  saves: { paddingHorizontal: space.sm, paddingVertical: 4, borderRadius: radius.sm },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 4 },
});
