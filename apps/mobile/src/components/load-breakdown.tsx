/**
 * "How is this worked out?": the Lung Load sum in plain steps, with the person's own numbers.
 * Separates it from AQI, which only describes the outdoor air at one moment.
 */
import { useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';

import { AppText, Card } from '@/components/ui';
import type { ScoreOut } from '@/lib/api/types';
import { space, useColors } from '@/theme';

const n = (v: number) => Math.round(v).toLocaleString();

export function LoadBreakdown({ s }: { s: ScoreOut }) {
  const c = useColors();
  const [open, setOpen] = useState(false);
  const ready = s.air_litres && s.ref_ug;
  return (
    <Card>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen((o) => !o)}
        style={styles.head}>
        <AppText variant="heading" style={{ flex: 1 }}>
          How is {s.score} worked out?
        </AppText>
        <AppText variant="heading" muted>
          {open ? '−' : '+'}
        </AppText>
      </Pressable>
      {open ? (
        ready ? (
          <View style={{ gap: space.md }}>
            <Step n="1" title="Air you breathed today">
              About {n(s.air_litres!)} litres
              {s.breathing_lpm ? `, ${s.breathing_lpm.toFixed(1)} L a minute on average` : ''}{' '}
              (more when walking or running, less asleep).
            </Step>
            <Step n="2" title="PM2.5 in that air">
              {n(s.dose_ug)} µg reached your lungs: outdoor air at home, work and on the road, after
              what walls and windows keep out
              {s.indoor_source_share >= 0.05
                ? `, plus smoke and fumes inside your home (${Math.round(s.indoor_source_share * 100)}% of it)`
                : ''}
              .
            </Step>
            <Step n="3" title="The same day in WHO-limit air">
              Breathing the same air at the WHO guideline (15 µg/m³) would have been {n(s.ref_ug!)} µg.
            </Step>
            <Step n="4" title="Lung Load">
              {n(s.dose_ug)} ÷ {n(s.ref_ug!)} = {(s.dose_ug / s.ref_ug!).toFixed(1)}×
              {s.sensitivity && s.sensitivity > 1
                ? `, × ${s.sensitivity} because children, people over 65 and people with a lung condition are more sensitive`
                : ''}{' '}
              → <AppText style={{ fontWeight: '600' }}>{s.score}</AppText>. 100 means a day breathing
              WHO-limit air.
            </Step>
            <View style={[styles.note, { backgroundColor: c.field }]}>
              <AppText variant="caption">
                AQI is different: it rates the air outside at one moment. Lung Load adds up what
                your lungs took in over the whole day, indoors, outdoors and on the road, so the
                two numbers don't match.
              </AppText>
            </View>
          </View>
        ) : (
          <AppText muted>The breakdown appears after the next update of today's estimate.</AppText>
        )
      ) : null}
    </Card>
  );
}

function Step({ n: num, title, children }: { n: string; title: string; children: React.ReactNode }) {
  const c = useColors();
  return (
    <View style={styles.step}>
      <View style={[styles.num, { backgroundColor: c.text }]}>
        <AppText variant="label" color="#FFFFFF">
          {num}
        </AppText>
      </View>
      <View style={{ flex: 1, gap: 2 }}>
        <AppText variant="label">{title}</AppText>
        <AppText variant="caption" muted>
          {children}
        </AppText>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: space.md },
  step: { flexDirection: 'row', gap: space.md, alignItems: 'flex-start' },
  num: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  note: { borderRadius: 12, padding: space.md },
});
