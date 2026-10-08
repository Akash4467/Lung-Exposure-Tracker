import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ActivityIndicator, View } from 'react-native';

import { ToggleRow } from '@/components/controls';
import { QueryState } from '@/components/query-state';
import { BandBadge } from '@/components/score';
import { AppText, Card, Disclaimer, Screen, Segmented } from '@/components/ui';
import { meApi, scoreApi } from '@/lib/api/endpoints';
import type { Brief, ProfileOut } from '@/lib/api/types';
import { sourceLabel } from '@/lib/labels';
import { keys } from '@/lib/query';
import { useDebounced } from '@/lib/use-debounced';
import { space, useColors } from '@/theme';

const SHIFTS = [
  { value: '-120', label: '2 h earlier' },
  { value: '-60', label: '1 h earlier' },
  { value: '0', label: 'As usual' },
  { value: '60', label: '1 h later' },
  { value: '120', label: '2 h later' },
] as const;

/** The changes that make sense for this user (no "run a purifier" if they already do). */
function options(p: ProfileOut): { id: string; label: string }[] {
  const home = p.places.home;
  const out: { id: string; label: string }[] = [];
  if (!home.purifier) out.push({ id: 'purifier_home', label: 'Run an air purifier at home' });
  if (home.windows !== 'closed') out.push({ id: 'close_windows_home', label: 'Keep home windows closed' });
  if (p.schedule.commute_mask !== 'n95') out.push({ id: 'n95_commute', label: 'Wear an N95 on the commute' });
  if (!p.places.office.purifier) out.push({ id: 'purifier_office', label: 'Purifier at work' });
  for (const s of home.sources) {
    out.push({ id: `source:${s.kind}`, label: `Cut down: ${sourceLabel(s.kind).toLowerCase()}` });
  }
  return out;
}

export default function Simulate() {
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  return (
    <Screen edges={['bottom']}>
      <AppText muted>Try a change and see how today's estimate would move.</AppText>
      <QueryState query={profile}>{(p) => <Controls p={p} />}</QueryState>
    </Screen>
  );
}

function Controls({ p }: { p: ProfileOut }) {
  const [shift, setShift] = useState<(typeof SHIFTS)[number]['value']>('0');
  const [on, setOn] = useState<string[]>([]);
  const input = useDebounced({ shift: Number(shift), mitigations: [...on].sort() }, 300);
  const sim = useQuery({
    queryKey: ['simulate', input.shift, input.mitigations.join(',')],
    queryFn: () =>
      scoreApi.simulate({ commute_shift_minutes: input.shift, mitigations: input.mitigations }),
    placeholderData: keepPreviousData, // keep the last answer on screen while the next loads
    staleTime: 5 * 60_000,
  });

  return (
    <>
      <Segmented label="Leave home" options={SHIFTS} value={shift} onChange={setShift} />
      {options(p).map((o) => (
        <ToggleRow
          key={o.id}
          label={o.label}
          value={on.includes(o.id)}
          onChange={(v) => setOn((cur) => (v ? [...cur, o.id] : cur.filter((x) => x !== o.id)))}
        />
      ))}
      <QueryState query={sim}>
        {(r) => (
          <Card>
            <View style={{ flexDirection: 'row', gap: space.md, alignItems: 'center' }}>
              <Side title="As things are" b={r.before} />
              <AppText variant="title" muted>
                →
              </AppText>
              <Side title="With your changes" b={r.after} />
              {sim.isFetching ? <ActivityIndicator /> : null}
            </View>
            <Saving pct={r.saves_pct} />
            {r.as_workday ? (
              <AppText variant="caption" muted>
                Today is a day off for you, so commute changes are shown on today's air as if it
                were a workday.
              </AppText>
            ) : null}
          </Card>
        )}
      </QueryState>
      <Disclaimer />
    </>
  );
}

function Side({ title, b }: { title: string; b: Brief }) {
  return (
    <View style={{ flex: 1, gap: 4 }}>
      <AppText variant="caption" muted>
        {title}
      </AppText>
      <AppText variant="title">{b.score}</AppText>
      <BandBadge band={b.band} size="sm" />
    </View>
  );
}

function Saving({ pct }: { pct: number }) {
  const c = useColors();
  if (Math.abs(pct) < 0.5) return <AppText muted>No real difference.</AppText>;
  return pct > 0 ? (
    <AppText variant="heading" color={c.band.green.fg}>
      {Math.round(pct)}% less polluted air breathed
    </AppText>
  ) : (
    <AppText variant="heading" color={c.band.red.fg}>
      {Math.round(-pct)}% more polluted air breathed
    </AppText>
  );
}
