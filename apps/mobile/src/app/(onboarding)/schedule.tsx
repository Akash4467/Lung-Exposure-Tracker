import { Redirect, router } from 'expo-router';
import { View } from 'react-native';

import { MultiChips, Progress, TimeStepper } from '@/components/controls';
import { AppText, Button, ErrorBanner, Screen, Segmented } from '@/components/ui';
import { MODES } from '@/lib/labels';
import { WEEKDAYS } from '@/lib/time';
import { scheduleError, missingStep, useDraft } from '@/store/onboarding';
import { space } from '@/theme';

export default function ScheduleStep() {
  const d = useDraft();
  const back = missingStep(d, 'schedule');
  const s = d.schedule;
  const err = scheduleError(s);
  if (back) return <Redirect href={back} />;
  return (
    <Screen
      footer={<Button title="Next" disabled={!!err} onPress={() => router.push('/details')} />}>
      <Progress step={3} of={4} />
      <View style={{ gap: space.sm }}>
        <AppText variant="title">Your usual day</AppText>
        <AppText muted>Roughly is fine. You can change it any time.</AppText>
      </View>

      <TimeStepper label="Wake up" value={s.wake} onChange={(wake) => d.setSchedule({ wake })} />
      <TimeStepper label="Leave home" value={s.leave_home} onChange={(v) => d.setSchedule({ leave_home: v })} />
      <TimeStepper label="Reach work" value={s.arrive_office} onChange={(v) => d.setSchedule({ arrive_office: v })} />
      <TimeStepper label="Leave work" value={s.leave_office} onChange={(v) => d.setSchedule({ leave_office: v })} />
      <TimeStepper label="Reach home" value={s.arrive_home} onChange={(v) => d.setSchedule({ arrive_home: v })} />
      <TimeStepper label="Go to sleep" value={s.sleep} onChange={(sleep) => d.setSchedule({ sleep })} />
      <ErrorBanner message={err} />

      <Segmented
        label="How do you usually travel?"
        options={MODES}
        value={s.commute_mode}
        onChange={(commute_mode) => d.setSchedule({ commute_mode })}
      />
      <MultiChips
        label="Days you go to work"
        options={WEEKDAYS}
        value={s.office_days}
        onChange={(office_days) => d.setSchedule({ office_days: [...office_days].sort() })}
      />
    </Screen>
  );
}
