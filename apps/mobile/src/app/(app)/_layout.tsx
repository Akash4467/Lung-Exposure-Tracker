import { Stack } from 'expo-router';
import { useEffect } from 'react';

import { AreaGate } from '@/components/area-gate';
import { listenForTaps, refreshPushToken } from '@/lib/push';
import { useColors } from '@/theme';

export default function AppLayout() {
  const c = useColors();
  // Keep this device's alert token current (only if alerts were already allowed; the
  // permission is asked from the alerts card, never at launch) and open tapped alerts.
  useEffect(() => {
    void refreshPushToken();
    return listenForTaps();
  }, []);
  return (
    <AreaGate area="app">
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: '#E3F0F3' }, // the top of the sky
          headerShadowVisible: false,
          headerTintColor: c.text,
          headerTitleStyle: { fontFamily: 'Fredoka_600SemiBold', fontSize: 20 },
          headerBackButtonDisplayMode: 'minimal',
          contentStyle: { backgroundColor: c.background },
        }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="verify-email" options={{ presentation: 'modal', title: 'Verify email' }} />
        <Stack.Screen name="edit-profile" options={{ title: 'Profile' }} />
        <Stack.Screen name="indoor" options={{ title: 'Home & sources' }} />
        <Stack.Screen name="log-activity" options={{ title: 'Log activity' }} />
        <Stack.Screen name="simulate" options={{ title: 'What if…' }} />
        <Stack.Screen name="footprint" options={{ title: 'Commute footprint' }} />
      </Stack>
    </AreaGate>
  );
}
