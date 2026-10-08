/**
 * Push alerts through Firebase Cloud Messaging. The server (alert_service) sends calm,
 * specific alerts such as "Tomorrow's air looks poor", with data { screen: 'tomorrow' }.
 *
 * Needs google-services.json in the build (see app.config.js). Without it, getting a token
 * fails and push simply stays off; nothing else in the app is affected.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Device from 'expo-device';
import * as Notifications from 'expo-notifications';
import { router } from 'expo-router';
import { Platform } from 'react-native';

import { meApi } from '@/lib/api/endpoints';

const TOKEN_KEY = 'lung.push.token';

if (Platform.OS !== 'web') {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: false,
      shouldSetBadge: false,
    }),
  });
}

export type PushStatus = 'on' | 'denied' | 'unavailable';

/** Current state without asking anything. */
export async function pushPermission(): Promise<'granted' | 'undetermined' | 'denied'> {
  if (Platform.OS === 'web') return 'denied';
  const p = await Notifications.getPermissionsAsync();
  return p.granted ? 'granted' : p.canAskAgain ? 'undetermined' : 'denied';
}

/** At startup: re-register silently if alerts were already allowed. Never prompts. */
export async function refreshPushToken(): Promise<void> {
  if ((await pushPermission()) === 'granted') await registerForPush();
}

/** When the user turns alerts on: ask (Android 13+ shows the prompt), then register
 * this device's FCM token. */
export async function registerForPush(): Promise<PushStatus> {
  if (Platform.OS === 'web' || !Device.isDevice) return 'unavailable';
  if (Platform.OS === 'android') {
    // Creating the channel is what triggers the permission prompt on Android 13+.
    await Notifications.setNotificationChannelAsync('alerts', {
      name: 'Air alerts',
      importance: Notifications.AndroidImportance.HIGH,
    });
  }
  let perm = await Notifications.getPermissionsAsync();
  if (!perm.granted && perm.canAskAgain) perm = await Notifications.requestPermissionsAsync();
  if (!perm.granted) return 'denied';

  try {
    const { data: token } = await Notifications.getDevicePushTokenAsync();
    await meApi.registerDevice(String(token), Platform.OS === 'ios' ? 'ios' : 'android');
    await AsyncStorage.setItem(TOKEN_KEY, String(token));
    return 'on';
  } catch {
    return 'unavailable'; // no google-services.json yet, or no Play Services
  }
}

/** On sign-out: stop alerts for this device (best effort). */
export async function unregisterPush(): Promise<void> {
  const token = await AsyncStorage.getItem(TOKEN_KEY);
  if (!token) return;
  await meApi.removeDevice(token).catch(() => undefined);
  await AsyncStorage.removeItem(TOKEN_KEY);
}

/** Tapping an alert opens the screen it names. */
export function listenForTaps(): () => void {
  if (Platform.OS === 'web') return () => {};
  const sub = Notifications.addNotificationResponseReceivedListener((r) => {
    const screen = r.notification.request.content.data?.screen;
    if (screen === 'tomorrow') router.push('/tomorrow');
  });
  return () => sub.remove();
}
