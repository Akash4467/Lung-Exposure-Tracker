import { router } from 'expo-router';
import { View } from 'react-native';

import { Progress, ToggleRow } from '@/components/controls';
import { AppText, Button, Screen, Segmented, TextField } from '@/components/ui';
import { useSession } from '@/lib/auth/session';
import { ageError, useDraft, weightError } from '@/store/onboarding';
import { space } from '@/theme';

const SEX = [
  { value: 'woman', label: 'Woman' },
  { value: 'man', label: 'Man' },
  { value: 'other', label: 'Other / prefer not to say' },
] as const;

export default function ProfileStep() {
  const d = useDraft();
  const { signOut } = useSession();
  const ok = !!d.age && !ageError(d.age) && !!d.sex && !weightError(d.weight);

  return (
    <Screen
      footer={
        <>
          <Button title="Next" disabled={!ok} onPress={() => router.push('/places')} />
          <Button title="Sign out" kind="ghost" onPress={() => signOut()} />
        </>
      }>
      <Progress step={1} of={4} />
      <View style={{ gap: space.sm }}>
        <AppText variant="title">About you</AppText>
        <AppText muted>
          How much air you breathe depends on your age, body and activity. This is all the
          estimate needs.
        </AppText>
      </View>

      <TextField
        label="Age"
        value={d.age}
        onChangeText={(t) => d.set({ age: t.replace(/\D/g, '').slice(0, 3) })}
        keyboardType="number-pad"
        error={ageError(d.age)}
      />
      <Segmented label="Sex" options={SEX} value={d.sex} onChange={(sex) => d.set({ sex })} />
      <ToggleRow
        label="I have asthma or another breathing condition"
        hint="Makes warnings more cautious. Stored privately, never logged or shared."
        value={d.sensitive}
        onChange={(sensitive) => d.set({ sensitive })}
      />
      <TextField
        label="Weight in kg (optional)"
        value={d.weight}
        onChangeText={(t) => d.set({ weight: t.replace(/[^\d.]/g, '').slice(0, 5) })}
        keyboardType="decimal-pad"
        error={weightError(d.weight)}
        hint="Makes your breathing rate, and so the estimate, more personal."
      />
    </Screen>
  );
}
