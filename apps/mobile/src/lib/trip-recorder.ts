/**
 * "Record my trips" (opt-in, off by default): the routes you actually travel, so the air on
 * the way is counted where you really were, with how you really moved.
 *
 * While on, Android shows a notification (a foreground service, required for background
 * location). GPS points are queued on the phone with the phone's own activity reading
 * (walking / running / cycling / in a vehicle) when it can give one, and uploaded in batches
 * to POST /v1/me/tracks. The server turns them into travel legs and does not keep the points.
 *
 * TaskManager.defineTask runs in the global scope (imported from the root layout), because
 * Android may start the app headless to deliver location updates.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import { API_URL } from '@/lib/api/client';
import { tracksApi } from '@/lib/api/endpoints';
import type { TrackPointIn } from '@/lib/api/types';
import { readItem } from '@/lib/auth/storage';

export const TRACK_TASK = 'lung-track';
const QUEUE_KEY = 'lung.track.queue';
const MAX_QUEUE = 3000;
const MAX_PER_UPLOAD = 500;
const UPLOAD_EVERY = 30; // points
const MAX_AGE_MS = 47 * 3600_000; // the API accepts the last 48 hours
const ACTIVITY_TIMEOUT_MS = 2500;

type Reading = Pick<TrackPointIn, 'activity' | 'confidence'>;

async function loadQueue(): Promise<TrackPointIn[]> {
  try {
    const raw = await AsyncStorage.getItem(QUEUE_KEY);
    return raw ? (JSON.parse(raw) as TrackPointIn[]) : [];
  } catch {
    return [];
  }
}

const saveQueue = (q: TrackPointIn[]) => AsyncStorage.setItem(QUEUE_KEY, JSON.stringify(q));

const CONFIDENCE_RANK = { low: 0, medium: 1, high: 2 } as const;

/** The phone's single best activity guess, from a MotionActivityObject. Exported for tests. */
export function bestActivity(
  activities: Partial<Record<string, { detected: boolean; confidence: unknown }>> | undefined,
): Reading {
  const allowed = ['walking', 'running', 'cycling', 'automotive', 'stationary'] as const;
  let best: Reading = {};
  for (const kind of allowed) {
    const a = activities?.[kind];
    if (!a?.detected) continue;
    const conf = String(a.confidence) as keyof typeof CONFIDENCE_RANK;
    if (!(conf in CONFIDENCE_RANK)) continue;
    if (!best.confidence || CONFIDENCE_RANK[conf] > CONFIDENCE_RANK[best.confidence]) {
      best = { activity: kind, confidence: conf };
    }
  }
  return best;
}

/** One quick activity reading; never blocks recording for long, never throws. */
async function readActivity(): Promise<Reading> {
  try {
    const perm = await Location.getMotionActivityPermissionsAsync();
    if (!perm.granted) return {};
    const reading = await Promise.race([
      Location.getMotionActivityAsync(),
      new Promise<null>((r) => setTimeout(() => r(null), ACTIVITY_TIMEOUT_MS)),
    ]);
    return reading ? bestActivity(reading.activities) : {};
  } catch {
    return {};
  }
}

/** Pure: new locations appended to the queue, trimmed to size and age. Exported for tests. */
export function appendPoints(
  queue: TrackPointIn[],
  locations: Location.LocationObject[],
  reading: Reading,
  now: number,
): TrackPointIn[] {
  const fresh = locations.map((l) => ({
    t: new Date(l.timestamp).toISOString(),
    lat: l.coords.latitude,
    lon: l.coords.longitude,
    speed: l.coords.speed !== null && l.coords.speed >= 0 ? l.coords.speed : undefined,
    accuracy: l.coords.accuracy ?? undefined,
    ...reading,
  }));
  return [...queue, ...fresh]
    .filter((p) => now - new Date(p.t).getTime() < MAX_AGE_MS)
    .slice(-MAX_QUEUE);
}

async function upload(points: TrackPointIn[], fromBackground: boolean): Promise<boolean> {
  if (!points.length) return true;
  try {
    if (!fromBackground) {
      await tracksApi.upload(points);
      return true;
    }
    const raw = await readItem('lung.session');
    const token = raw ? (JSON.parse(raw) as { access?: string }).access : undefined;
    if (!token) return false;
    const res = await fetch(`${API_URL}/v1/me/tracks`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ points }),
    });
    return res.ok; // an expired token waits for the app to open and refresh
  } catch {
    return false;
  }
}

/** Upload what's queued. From the background only once a batch has built up. */
export async function flushTrack(fromBackground = false): Promise<void> {
  const q = await loadQueue();
  if (!q.length || (fromBackground && q.length < UPLOAD_EVERY)) return;
  const batch = q.slice(0, MAX_PER_UPLOAD);
  if (await upload(batch, fromBackground)) {
    const after = await loadQueue(); // more points may have arrived meanwhile
    await saveQueue(after.slice(batch.length));
  }
}

if (Platform.OS !== 'web') {
  TaskManager.defineTask<{ locations: Location.LocationObject[] }>(
    TRACK_TASK,
    async ({ data, error }) => {
      if (error || !data?.locations?.length) return;
      const reading = await readActivity();
      await saveQueue(appendPoints(await loadQueue(), data.locations, reading, Date.now()));
      await flushTrack(true);
    },
  );
}

export type RecorderStatus = 'on' | 'off' | 'unsupported';

export async function recorderStatus(): Promise<RecorderStatus> {
  if (Platform.OS === 'web') return 'unsupported';
  return (await Location.hasStartedLocationUpdatesAsync(TRACK_TASK)) ? 'on' : 'off';
}

export class NeedsPermission extends Error {}

/** Asks for location "while using" then "all the time", and (optionally) physical activity,
 * then starts recording with Android's ongoing notification. */
export async function startRecording(): Promise<void> {
  const fg = await Location.requestForegroundPermissionsAsync();
  if (!fg.granted) throw new NeedsPermission('Location permission was not given.');
  const bg = await Location.requestBackgroundPermissionsAsync();
  if (!bg.granted) throw new NeedsPermission('Choose "Allow all the time" for location.');
  // Better labels for how you travel; recording still works on GPS speed without it.
  await Location.requestMotionActivityPermissionsAsync().catch(() => undefined);
  await Location.startLocationUpdatesAsync(TRACK_TASK, {
    accuracy: Location.Accuracy.Balanced,
    distanceInterval: 40, // metres between points
    timeInterval: 30_000,
    deferredUpdatesInterval: 60_000, // batch updates to save battery
    pausesUpdatesAutomatically: true,
    foregroundService: {
      notificationTitle: 'Recording your trips',
      notificationBody: 'Counting the air on your way. Turn off any time in Settings.',
      notificationColor: '#121417',
    },
  });
}

export async function stopRecording(): Promise<void> {
  if (await Location.hasStartedLocationUpdatesAsync(TRACK_TASK)) {
    await Location.stopLocationUpdatesAsync(TRACK_TASK);
  }
  await flushTrack(false).catch(() => undefined);
}
