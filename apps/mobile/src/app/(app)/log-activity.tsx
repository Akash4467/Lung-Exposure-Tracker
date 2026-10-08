/**
 * Lung Load: tell the app what you did ("ran 30 minutes, outside, ending 20 minutes ago").
 * Today's score updates at once. Later, the phone's activity recognition and Health Connect
 * fill this in automatically.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { StyleSheet, View } from 'react-native';

import { QueryState } from '@/components/query-state';
import { activityLabel } from '@/components/score';
import { AppText, Button, Card, ErrorBanner, Overline, Screen, Segmented } from '@/components/ui';
import { activityApi } from '@/lib/api/endpoints';
import type { Activity, ActivityDayOut } from '@/lib/api/types';
import { goBack } from '@/lib/nav';
import { errorMessage, keys } from '@/lib/query';
import { space, useColors } from '@/theme';

const KINDS: readonly { value: Activity; label: string }[] = [
  { value: 'walk', label: 'Walk' },
  { value: 'run', label: 'Run' },
  { value: 'cycle', label: 'Cycle' },
];
const WHERE = [
  { value: 'out', label: 'Outside' },
  { value: 'in', label: 'Indoors (gym, treadmill)' },
] as const;
const DURATIONS = [
  { value: '15', label: '15 min' },
  { value: '30', label: '30 min' },
  { value: '45', label: '45 min' },
  { value: '60', label: '1 h' },
  { value: '90', label: '1½ h' },
] as const;
const ENDED = [
  { value: '0', label: 'Just now' },
  { value: '30', label: '30 min ago' },
  { value: '60', label: '1 h ago' },
  { value: '120', label: '2 h ago' },
  { value: '240', label: '4 h ago' },
] as const;

type Dur = (typeof DURATIONS)[number]['value'];
type Ended = (typeof ENDED)[number]['value'];

export default function LogActivity() {
  const qc = useQueryClient();
  const [kind, setKind] = useState<Activity>('walk');
  const [where, setWhere] = useState<'out' | 'in'>('out');
  const [dur, setDur] = useState<Dur>('30');
  const [ended, setEnded] = useState<Ended>('0');
  const day = useQuery({ queryKey: keys.activity, queryFn: activityApi.day });

  const refresh = () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.today }),
      qc.invalidateQueries({ queryKey: keys.history }),
      qc.invalidateQueries({ queryKey: keys.activity }),
    ]);

  const save = useMutation({
    mutationFn: () => {
      const end = new Date(Date.now() - Number(ended) * 60_000);
      const start = new Date(end.getTime() - Number(dur) * 60_000);
      return activityApi.log([
        {
          start: start.toISOString(),
          end: end.toISOString(),
          kind,
          outdoors: where === 'out',
          source: 'manual',
        },
      ]);
    },
    onSuccess: async () => {
      await refresh();
      goBack('/today');
    },
  });
  const remove = useMutation({ mutationFn: activityApi.remove, onSuccess: refresh });

  return (
    <Screen
      edges={['bottom']}
      air="breeze"
      footer={
        <Button
          title={`Add ${activityLabel(kind).toLowerCase()}`}
          onPress={() => save.mutate()}
          loading={save.isPending}
        />
      }>
      <View style={{ gap: space.xs }}>
        <AppText variant="title">What did you do?</AppText>
        <AppText muted>
          Moving makes you breathe faster, so you take in more of whatever is in the air.
        </AppText>
      </View>
      <ErrorBanner message={errorMessage(save.error ?? remove.error)} />
      <Segmented label="Activity" options={KINDS} value={kind} onChange={setKind} />
      <Segmented label="Where" options={WHERE} value={where} onChange={setWhere} />
      <Segmented label="How long" options={DURATIONS} value={dur} onChange={setDur} />
      <Segmented label="Finished" options={ENDED} value={ended} onChange={setEnded} />

      <QueryState query={day}>
        {(d) => <TodayList d={d} onRemove={(id) => remove.mutate(id)} busy={remove.isPending} />}
      </QueryState>
    </Screen>
  );
}

function TodayList({
  d,
  onRemove,
  busy,
}: {
  d: ActivityDayOut;
  onRemove: (id: number) => void;
  busy: boolean;
}) {
  const c = useColors();
  if (!d.activities.length) return null;
  const time = (iso: string) =>
    new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
  return (
    <View style={{ gap: space.sm }}>
      <Overline>Logged today</Overline>
      {d.activities.map((a) => (
        <Card key={a.id} style={styles.row}>
          <View style={[styles.dot, { backgroundColor: c.activity[a.kind] }]} />
          <View style={{ flex: 1 }}>
            <AppText>{activityLabel(a.kind)}</AppText>
            <AppText variant="caption" muted>
              {time(a.start)} – {time(a.end)}
              {a.outdoors === false ? ' · indoors' : ''}
              {a.source !== 'manual' ? ' · from your phone' : ''}
            </AppText>
          </View>
          <Button title="Remove" kind="ghost" compact disabled={busy} onPress={() => onRemove(a.id)} />
        </Card>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: space.sm, gap: space.md },
  dot: { width: 10, height: 10, borderRadius: 5 },
});
