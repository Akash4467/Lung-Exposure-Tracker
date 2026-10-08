import {
  Fredoka_500Medium,
  Fredoka_600SemiBold,
  Fredoka_700Bold,
} from '@expo-google-fonts/fredoka';
import {
  Inter_300Light,
  Inter_400Regular,
  Inter_500Medium,
  Inter_600SemiBold,
  Inter_700Bold,
  useFonts,
} from '@expo-google-fonts/inter';
import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { DefaultTheme, SplashScreen, Stack, ThemeProvider } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { Button, Screen, AppText } from '@/components/ui';
import { authApi } from '@/lib/api/endpoints';
// Registers the geofencing background task. Must load at startup, in the global scope:
// Android may launch the app headless just to deliver an enter/exit event.
import { flushVisits } from '@/lib/geofence';
// Registers the opt-in trip recorder's background task (same reason as the geofence one).
import { flushTrack } from '@/lib/trip-recorder';
import { syncHealthIfDue } from '@/lib/health';
import { SessionProvider, useSession } from '@/lib/auth/session';
import { errorMessage, keys, queryClient } from '@/lib/query';
import { useColors } from '@/theme';

SplashScreen.preventAutoHideAsync();

export default function Root() {
  // Nothing renders until the typeface is ready (the splash covers it): Android measures text
  // once, so text laid out in the fallback font would stay cut off after Inter arrives.
  const [fontsLoaded, fontError] = useFonts({
    Inter_300Light,
    Inter_400Regular,
    Inter_500Medium,
    Inter_600SemiBold,
    Inter_700Bold,
    Fredoka_500Medium,
    Fredoka_600SemiBold,
    Fredoka_700Bold,
  });
  if (!fontsLoaded && !fontError) return null; // if loading fails, fall back to system text
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <ThemeProvider value={DefaultTheme}>
            <StatusBar style="dark" />
            <RootNavigator />
          </ThemeProvider>
        </SessionProvider>
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}

/**
 * Three areas; each group's layout lets in only users who belong there (AreaGate):
 *   signed out                 -> (auth)
 *   signed in, not onboarded   -> (onboarding)
 *   signed in and onboarded    -> (app): tabs + settings screens
 * "/" (index) sends everyone to the right one. The splash stays up for the first decision.
 */
function RootNavigator() {
  const c = useColors();
  const { status } = useSession();
  const signedIn = status === 'signedIn';
  const me = useQuery({ queryKey: keys.me, queryFn: authApi.me, enabled: signedIn });

  // The navigator always stays mounted (unmounting it mid sign-in breaks navigation). The
  // index and the area gates render nothing until the area is known; the splash covers that.
  const deciding = status === 'loading' || (signedIn && me.isPending);
  useEffect(() => {
    if (!deciding) SplashScreen.hide();
  }, [deciding]);

  // Upload any geofence visits queued while the app was closed (and on every return).
  useEffect(() => {
    if (!signedIn) return;
    void flushVisits();
    void flushTrack();
    void syncHealthIfDue();
    const sub = AppState.addEventListener('change', (s) => {
      if (s === 'active') {
        void flushVisits();
        void flushTrack();
        void syncHealthIfDue();
      }
    });
    return () => sub.remove();
  }, [signedIn]);

  if (signedIn && me.isError && !me.data && !me.isFetching) {
    return (
      <Screen scroll={false}>
        <AppText variant="title">Can't load your account</AppText>
        <AppText muted>{errorMessage(me.error)}</AppText>
        <Button title="Try again" onPress={() => me.refetch()} />
      </Screen>
    );
  }

  return (
    <Stack
      screenOptions={{
        headerShown: false,
        contentStyle: { backgroundColor: c.background },
      }}>
      <Stack.Screen name="index" />
      <Stack.Screen name="(auth)" />
      <Stack.Screen name="(onboarding)" />
      <Stack.Screen name="(app)" />
    </Stack>
  );
}
