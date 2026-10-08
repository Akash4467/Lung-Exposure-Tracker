import { Redirect, router } from 'expo-router';
import { View } from 'react-native';

import { Progress } from '@/components/controls';
import { PlacePicker } from '@/components/place-picker';
import { AppText, Button, Screen } from '@/components/ui';
import { missingStep, useDraft } from '@/store/onboarding';
import { space } from '@/theme';

export default function PlacesStep() {
  const d = useDraft();
  const back = missingStep(d, 'places');
  if (back) return <Redirect href={back} />;
  return (
    <Screen
      footer={
        <Button
          title="Next"
          disabled={!d.home || !d.office}
          onPress={() => router.push('/schedule')}
        />
      }>
      <Progress step={2} of={4} />
      <View style={{ gap: space.sm }}>
        <AppText variant="title">Where you spend your day</AppText>
        <AppText muted>
          We use these two places to look up the air, nothing else. We never track you around
          the city.
        </AppText>
      </View>
      <PlacePicker title="Home" value={d.home} onChange={(home) => d.set({ home })} />
      <PlacePicker title="Work or college" value={d.office} onChange={(office) => d.set({ office })} />
    </Screen>
  );
}
