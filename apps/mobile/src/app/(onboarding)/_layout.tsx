import { Stack } from 'expo-router';

import { AreaGate } from '@/components/area-gate';
import { useColors } from '@/theme';

export default function OnboardingLayout() {
  const c = useColors();
  return (
    <AreaGate area="onboarding">
      <Stack
        screenOptions={{
          headerShadowVisible: false,
          headerTitle: '',
          headerStyle: { backgroundColor: c.background },
          headerTintColor: c.text,
          headerTitleStyle: { fontFamily: 'Fredoka_600SemiBold', fontSize: 20 },
          contentStyle: { backgroundColor: c.background },
        }}
      />
    </AreaGate>
  );
}
