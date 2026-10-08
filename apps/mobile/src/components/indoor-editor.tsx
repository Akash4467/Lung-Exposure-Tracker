/**
 * Home details: size, windows, purifier and indoor sources. Used by the last onboarding step
 * and by Settings. The source list comes from GET /v1/catalog, so new kinds added on the
 * server appear here automatically.
 */
import { useQuery } from '@tanstack/react-query';
import { Pressable, StyleSheet, View } from 'react-native';

import { TimeStepper, ToggleRow } from '@/components/controls';
import { AppText, Button, Card, Segmented, TextField } from '@/components/ui';
import { metaApi } from '@/lib/api/endpoints';
import type { SourceIn, Windows } from '@/lib/api/types';
import { minutesLabel, sizeLabel, sourceDefaults, sourceLabel, WINDOWS } from '@/lib/labels';
import { keys } from '@/lib/query';
import { radius, space, useColors } from '@/theme';

export interface IndoorValue {
  size: string | null;
  windows: Windows;
  purifier: boolean;
  cadr: string;
  sources: SourceIn[];
}

const MINUTE_STEPS = [5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 360, 480, 600];

export function IndoorEditor({
  value,
  update,
}: {
  value: IndoorValue;
  /** Changes are computed from the latest value, so two quick taps can't overwrite each other. */
  update: (fn: (current: IndoorValue) => Partial<IndoorValue>) => void;
}) {
  const onChange = (patch: Partial<IndoorValue>) => update(() => patch);
  const c = useColors();
  const catalog = useQuery({ queryKey: keys.catalog, queryFn: metaApi.catalog, staleTime: Infinity });
  const sizes = (catalog.data?.home_sizes ?? ['1rk', '1bhk', '2bhk', '3bhk', '4bhk_plus']).map((s) => ({
    value: s,
    label: sizeLabel(s),
  }));
  const kinds = catalog.data?.indoor_sources.map((s) => s.kind) ?? [];
  const used = new Set(value.sources.map((s) => s.kind));

  const setSource = (i: number, patch: Partial<SourceIn>) =>
    update((v) => ({ sources: v.sources.map((s, j) => (j === i ? { ...s, ...patch } : s)) }));

  return (
    <View style={{ gap: space.lg }}>
      <Segmented label="Home size" options={sizes} value={value.size} onChange={(size) => onChange({ size })} />
      <Segmented label="Windows" options={WINDOWS} value={value.windows} onChange={(windows) => onChange({ windows })} />
      <ToggleRow
        label="I run an air purifier at home"
        value={value.purifier}
        onChange={(purifier) => onChange({ purifier })}
      />
      {value.purifier ? (
        <TextField
          label="Purifier CADR in m³/h (optional)"
          value={value.cadr}
          onChangeText={(t) => onChange({ cadr: t.replace(/\D/g, '').slice(0, 4) })}
          keyboardType="number-pad"
          hint="The clean-air delivery rate printed on the box. Leave empty if you don't know."
        />
      ) : null}

      <View style={{ gap: space.sm }}>
        <AppText variant="label">Smoke or fumes indoors</AppText>
        <AppText variant="caption" muted>
          Cooking, incense and mosquito coils can matter as much as the air outside.
        </AppText>
        {value.sources.map((s, i) => (
          <Card key={`${s.kind}-${i}`}>
            <View style={styles.sourceHead}>
              <AppText variant="heading" style={{ flex: 1 }}>
                {sourceLabel(s.kind)}
              </AppText>
              <Button
                title="Remove"
                kind="ghost"
                onPress={() => update((v) => ({ sources: v.sources.filter((_, j) => j !== i) }))}
              />
            </View>
            <TimeStepper label="Starts" value={s.start} onChange={(start) => setSource(i, { start })} />
            <View style={styles.durations}>
              {MINUTE_STEPS.map((m) => {
                const on = s.minutes === m;
                return (
                  <Pressable
                    key={m}
                    accessibilityRole="radio"
                    accessibilityState={{ selected: on }}
                    onPress={() => setSource(i, { minutes: m })}
                    style={[
                      styles.duration,
                      { backgroundColor: on ? c.primary : c.field },
                    ]}>
                    <AppText variant="caption" color={on ? c.primaryText : c.text}>
                      {minutesLabel(m)}
                    </AppText>
                  </Pressable>
                );
              })}
            </View>
          </Card>
        ))}
        <View style={styles.addRow}>
          {kinds
            .filter((k) => !used.has(k))
            .map((k) => (
              <Pressable
                key={k}
                accessibilityRole="button"
                accessibilityLabel={`Add ${sourceLabel(k)}`}
                onPress={() => {
                  const def = sourceDefaults(k);
                  update((v) =>
                    v.sources.some((s) => s.kind === k)
                      ? {}
                      : { sources: [...v.sources, { kind: k, start: def.start, minutes: def.minutes }] },
                  );
                }}
                style={[styles.add, { borderColor: c.border, backgroundColor: c.surface }]}>
                <AppText variant="label" color={c.accent}>
                  + {sourceLabel(k)}
                </AppText>
              </Pressable>
            ))}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  sourceHead: { flexDirection: 'row', alignItems: 'center' },
  durations: { flexDirection: 'row', flexWrap: 'wrap', gap: space.xs },
  duration: { paddingHorizontal: space.sm, paddingVertical: 6, borderRadius: radius.pill },
  addRow: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  add: { paddingHorizontal: space.md, minHeight: 40, justifyContent: 'center', borderRadius: radius.pill, borderWidth: 1, borderStyle: 'dashed' },
});
