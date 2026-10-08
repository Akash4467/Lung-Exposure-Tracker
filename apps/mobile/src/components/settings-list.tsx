/**
 * Settings rows in the "glass" style: an icon tile, the setting and a one-line summary of what's
 * saved now, and a chevron. Used for "Your details" (profile, home & work, schedule, home air).
 */
import { type Href, router } from 'expo-router';
import { Pressable, StyleSheet, View } from 'react-native';
import Svg, { Circle, Line, Path, Rect } from 'react-native-svg';

import { AppText, Card } from '@/components/ui';
import { radius, space, useColors } from '@/theme';

export type RowIcon = 'person' | 'pin' | 'clock' | 'home' | 'mail';

const TINT: Record<RowIcon, string> = {
  person: '#E8EEF9',
  pin: '#E3F3EC',
  clock: '#FBF0DA',
  home: '#F1E9F8',
  mail: '#FBEAE8',
};

function Icon({ name, color }: { name: RowIcon; color: string }) {
  const p = {
    stroke: color,
    strokeWidth: 1.8,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    fill: 'none',
  } as const;
  return (
    <Svg width={20} height={20} viewBox="0 0 24 24">
      {name === 'person' ? (
        <>
          <Circle cx={12} cy={8} r={4} {...p} />
          <Path d="M4.5 20c1.4-3.6 4.2-5.5 7.5-5.5s6.1 1.9 7.5 5.5" {...p} />
        </>
      ) : name === 'pin' ? (
        <>
          <Path d="M12 21s-6.5-5.6-6.5-11a6.5 6.5 0 0 1 13 0c0 5.4-6.5 11-6.5 11z" {...p} />
          <Circle cx={12} cy={10} r={2.3} {...p} />
        </>
      ) : name === 'clock' ? (
        <>
          <Circle cx={12} cy={12} r={8.5} {...p} />
          <Line x1={12} y1={7.5} x2={12} y2={12} {...p} />
          <Line x1={12} y1={12} x2={15.5} y2={14} {...p} />
        </>
      ) : name === 'home' ? (
        <>
          <Path d="M4 11l8-6.5 8 6.5" {...p} />
          <Path d="M6.5 9.5V19h11V9.5" {...p} />
          <Path d="M10.5 15.5c0-1.2 1.5-1.6 1.5-3 .9.8 1.5 1.8 1.5 3a1.5 1.5 0 0 1-3 0z" {...p} />
        </>
      ) : (
        <>
          <Rect x={3.5} y={6} width={17} height={12.5} rx={2.5} {...p} />
          <Path d="M4.5 7.5l7.5 5.5 7.5-5.5" {...p} />
        </>
      )}
    </Svg>
  );
}

export function SettingsRow({
  icon,
  label,
  summary,
  href,
  last,
}: {
  icon: RowIcon;
  label: string;
  summary?: string;
  href: Href;
  last?: boolean;
}) {
  const c = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={summary ? `${label}. ${summary}` : label}
      onPress={() => router.push(href)}
      style={({ pressed }) => [styles.row, pressed && { backgroundColor: c.field }]}>
      <View style={[styles.tile, { backgroundColor: TINT[icon] }]}>
        <Icon name={icon} color={c.text} />
      </View>
      <View
        style={[
          styles.text,
          !last && { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: c.border },
        ]}>
        <View style={{ flex: 1, gap: 1 }}>
          <AppText variant="label" numberOfLines={1}>
            {label}
          </AppText>
          {summary ? (
            <AppText variant="caption" muted numberOfLines={2}>
              {summary}
            </AppText>
          ) : null}
        </View>
        <View style={[styles.chevron, { backgroundColor: c.field }]}>
          <Svg width={14} height={14} viewBox="0 0 24 24">
            <Path
              d="M9 6l6 6-6 6"
              stroke={c.textMuted}
              strokeWidth={2.4}
              strokeLinecap="round"
              strokeLinejoin="round"
              fill="none"
            />
          </Svg>
        </View>
      </View>
    </Pressable>
  );
}

/** A glass group of rows, with a small heading above it. */
export function SettingsGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <View style={{ gap: space.xs }}>
      <AppText variant="overline" muted style={{ paddingHorizontal: space.xs }}>
        {title.toUpperCase()}
      </AppText>
      <Card style={{ padding: 0, gap: 0, overflow: 'hidden' }}>{children}</Card>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: space.md, paddingLeft: space.lg },
  tile: {
    width: 38,
    height: 38,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  text: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 64,
    paddingVertical: space.sm,
    paddingRight: space.lg,
  },
  chevron: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
