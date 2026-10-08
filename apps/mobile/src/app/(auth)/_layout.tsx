import { Stack } from 'expo-router';

import { AreaGate } from '@/components/area-gate';
import { useColors } from '@/theme';

export default function AuthLayout() {
  const c = useColors();
  return (
    <AreaGate area="auth">
    <Stack
      screenOptions={{
        headerShadowVisible: false,
        headerTitle: '',
        headerStyle: { backgroundColor: c.background },
        headerTintColor: c.text,
        headerTitleStyle: { fontFamily: 'Fredoka_600SemiBold', fontSize: 20 },
        contentStyle: { backgroundColor: c.background },
      }}>
      <Stack.Screen name="sign-in" options={{ headerShown: false }} />
      <Stack.Screen name="sign-up" />
      <Stack.Screen name="forgot-password" />
    </Stack>
    </AreaGate>
  );
}
