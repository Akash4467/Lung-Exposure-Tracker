/** Form controls beyond the basics: time stepper, toggle row, multi-select chips. */
import { Pressable, StyleSheet, Switch, View } from 'react-native';

import { AppText } from '@/components/ui';
import { addMinutes, display } from '@/lib/time';
import { radius, space, useColors } from '@/theme';

/** A time in 15-minute steps. Big targets, no native picker needed, works everywhere. */
export function TimeStepper({
  label,
  value,
  onChange,
  step = 15,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  step?: number;
}) {
  const c = useColors();
  const btn = (delta: number, text: string, hint: string) => (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${hint} ${label}`}
      onPress={() => onChange(addMinutes(value, delta))}
      hitSlop={6}
      style={({ pressed }) => [
        styles.stepBtn,
        { backgroundColor: c.field, opacity: pressed ? 0.7 : 1 },
      ]}>
      <AppText variant="heading">{text}</AppText>
    </Pressable>
  );
  return (
    <View style={[styles.row, { borderColor: c.glassBorder, backgroundColor: c.glass }]}>
      <AppText style={{ flex: 1 }}>{label}</AppText>
      {btn(-step, '−', 'Earlier')}
      <AppText
        variant="heading"
        style={styles.time}
        accessibilityLabel={`${label}: ${display(value)}`}
        accessibilityLiveRegion="polite">
        {display(value)}
      </AppText>
      {btn(step, '+', 'Later')}
    </View>
  );
}

export function ToggleRow({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  const c = useColors();
  return (
    <View style={[styles.row, { borderColor: c.glassBorder, backgroundColor: c.glass }]}>
      <View style={{ flex: 1, gap: 2 }}>
        <AppText>{label}</AppText>
        {hint ? (
          <AppText variant="caption" muted>
            {hint}
          </AppText>
        ) : null}
      </View>
      <Switch
        value={value}
        onValueChange={onChange}
        accessibilityLabel={label}
        trackColor={{ true: c.accent, false: '#D5D8DD' }}
        thumbColor="#FFFFFF"
      />
    </View>
  );
}

export function MultiChips<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { value: T; label: string }[];
  value: T[];
  onChange: (v: T[]) => void;
}) {
  const c = useColors();
  return (
    <View style={{ gap: space.xs }}>
      <AppText variant="label">{label}</AppText>
      <View style={styles.chips}>
        {options.map((o) => {
          const on = value.includes(o.value);
          return (
            <Pressable
              key={String(o.value)}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: on }}
              onPress={() =>
                onChange(on ? value.filter((v) => v !== o.value) : [...value, o.value])
              }
              style={[
                styles.chip,
                {
                  backgroundColor: on ? c.glassStrong : c.glass,
                  borderColor: on ? c.text : c.glassBorder,
                  borderWidth: on ? 1.5 : 1,
                },
              ]}>
              <AppText variant="label" style={{ fontWeight: on ? '600' : '500' }}>
                {o.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

/** "Step 2 of 4" with a thin progress bar. */
export function Progress({ step, of }: { step: number; of: number }) {
  const c = useColors();
  return (
    <View style={{ gap: space.xs }} accessibilityLabel={`Step ${step} of ${of}`}>
      <AppText variant="caption" muted>
        Step {step} of {of}
      </AppText>
      <View style={[styles.track, { backgroundColor: 'rgba(18,20,23,0.12)' }]}>
        <View style={{ width: `${(step / of) * 100}%`, height: '100%', backgroundColor: c.primary, borderRadius: radius.pill }} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    minHeight: 56,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  stepBtn: {
    width: 40,
    height: 40,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  time: { minWidth: 84, textAlign: 'center', fontVariant: ['tabular-nums'] },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 40,
    minWidth: 52,
    paddingHorizontal: space.md,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  track: { height: 3, borderRadius: radius.pill, overflow: 'hidden' },
});
