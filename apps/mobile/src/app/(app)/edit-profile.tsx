import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { View } from 'react-native';

import { MultiChips, TimeStepper, ToggleRow } from '@/components/controls';
import { PlacePicker } from '@/components/place-picker';
import { QueryState } from '@/components/query-state';
import { AppText, Button, ErrorBanner, Screen, Segmented, TextField } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import type { ProfileOut } from '@/lib/api/types';
import { MODES } from '@/lib/labels';
import { goBack } from '@/lib/nav';
import { errorMessage, keys } from '@/lib/query';
import { WEEKDAYS } from '@/lib/time';
import { ageError, scheduleError, toProfileIn, useDraft, weightError } from '@/store/onboarding';
import { space } from '@/theme';

const SEX = [
  { value: 'woman', label: 'Woman' },
  { value: 'man', label: 'Man' },
  { value: 'other', label: 'Other' },
] as const;

export default function EditProfile() {
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  return (
    <Screen edges={['bottom']}>
      <QueryState query={profile}>{(p) => <Form p={p} />}</QueryState>
    </Screen>
  );
}

function Form({ p }: { p: ProfileOut }) {
  const qc = useQueryClient();
  const d = useDraft();
  const { fromProfile } = d;
  useEffect(() => fromProfile(p), [p, fromProfile]); // start from what's saved

  const err = ageError(d.age) ?? weightError(d.weight) ?? scheduleError(d.schedule);
  const save = useMutation({
    mutationFn: () => meApi.saveProfile(toProfileIn(useDraft.getState())),
    onSuccess: async (saved) => {
      qc.setQueryData(keys.profile, saved);
      await Promise.all([
        qc.invalidateQueries({ queryKey: ['score'] }),
        qc.invalidateQueries({ queryKey: ['simulate'] }),
      ]);
      goBack('/settings');
    },
  });

  if (!d.home || !d.office || !d.sex) return null; // first render, before the draft loads

  return (
    <>
      <ErrorBanner message={errorMessage(save.error)} />
      <AppText variant="heading">About you</AppText>
      <TextField
        label="Age"
        value={d.age}
        onChangeText={(t) => d.set({ age: t.replace(/\D/g, '').slice(0, 3) })}
        keyboardType="number-pad"
        error={ageError(d.age)}
      />
      <Segmented label="Sex" options={SEX} value={d.sex} onChange={(sex) => d.set({ sex })} />
      <ToggleRow
        label="Asthma or another breathing condition"
        value={d.sensitive}
        onChange={(sensitive) => d.set({ sensitive })}
      />
      <TextField
        label="Weight in kg (optional)"
        value={d.weight}
        onChangeText={(t) => d.set({ weight: t.replace(/[^\d.]/g, '').slice(0, 5) })}
        keyboardType="decimal-pad"
        error={weightError(d.weight)}
      />

      <AppText variant="heading">Places</AppText>
      <PlacePicker title="Home" value={d.home} onChange={(home) => d.set({ home })} />
      <PlacePicker title="Work or college" value={d.office} onChange={(office) => d.set({ office })} />

      <AppText variant="heading">Your usual day</AppText>
      <View style={{ gap: space.sm }}>
        <TimeStepper label="Wake up" value={d.schedule.wake} onChange={(wake) => d.setSchedule({ wake })} />
        <TimeStepper label="Leave home" value={d.schedule.leave_home} onChange={(v) => d.setSchedule({ leave_home: v })} />
        <TimeStepper label="Reach work" value={d.schedule.arrive_office} onChange={(v) => d.setSchedule({ arrive_office: v })} />
        <TimeStepper label="Leave work" value={d.schedule.leave_office} onChange={(v) => d.setSchedule({ leave_office: v })} />
        <TimeStepper label="Reach home" value={d.schedule.arrive_home} onChange={(v) => d.setSchedule({ arrive_home: v })} />
        <TimeStepper label="Go to sleep" value={d.schedule.sleep} onChange={(sleep) => d.setSchedule({ sleep })} />
      </View>
      <Segmented
        label="Usual travel"
        options={MODES}
        value={d.schedule.commute_mode}
        onChange={(commute_mode) => d.setSchedule({ commute_mode })}
      />
      <MultiChips
        label="Days you go to work"
        options={WEEKDAYS}
        value={d.schedule.office_days}
        onChange={(office_days) => d.setSchedule({ office_days: [...office_days].sort() })}
      />
      <ErrorBanner message={scheduleError(d.schedule)} />
      <Button title="Save" onPress={() => save.mutate()} disabled={!!err || !d.age} loading={save.isPending} />
    </>
  );
}
