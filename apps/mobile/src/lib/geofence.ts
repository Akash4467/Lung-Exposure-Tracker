/**
 * "Use my real day": two geofences (home, office) instead of a declared schedule.
 *
 * Privacy by design: Android's geofencing service watches two circles and wakes the app only
 * on enter/exit. The app never reads or stores a GPS trail. Enter/exit events become visits
 * (home / office / away) that are queued on the phone and uploaded to POST /v1/me/visits,
 * where they replace the schedule for hours already past.
 *
 * TaskManager.defineTask must run in the global scope (it is imported from the root layout),
 * because Android may start the app headless just to deliver an event.
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Location from 'expo-location';
import * as TaskManager from 'expo-task-manager';
import { Platform } from 'react-native';

import { API_URL } from '@/lib/api/client';
import { meApi } from '@/lib/api/endpoints';
import type { VisitIn } from '@/lib/api/types';
import { readItem } from '@/lib/auth/storage';

export const GEOFENCE_TASK = 'lung-geofence';
const STATE_KEY = 'lung.geofence.state';
const RADIUS_M = 150; // big enough for GPS drift, small enough to tell home from the market
const MIN_VISIT_MS = 2 * 60_000; // ignore flickers at the edge of a circle
const MAX_AGE_MS = 47 * 3600_000; // the API only accepts the last 48 hours
const MAX_PER_UPLOAD = 200;

type PlaceName = 'home' | 'office';

interface State {
  current: { place: VisitIn['place']; since: number } | null;
  pending: VisitIn[];
}

async function load(): Promise<State> {
  try {
    const raw = await AsyncStorage.getItem(STATE_KEY);
    return raw ? (JSON.parse(raw) as State) : { current: null, pending: [] };
  } catch {
    return { current: null, pending: [] };
  }
}

const save = (s: State) => AsyncStorage.setItem(STATE_KEY, JSON.stringify(s));

function close(s: State, end: number) {
  if (s.current && end - s.current.since >= MIN_VISIT_MS) {
    s.pending.push({
      place: s.current.place,
      start: new Date(s.current.since).toISOString(),
      end: new Date(end).toISOString(),
    });
  }
}

/** Pure state transition, exported for tests. */
export function applyEvent(s: State, place: PlaceName, entered: boolean, at: number): State {
  const next: State = { current: s.current, pending: [...s.pending] };
  if (entered) {
    if (next.current?.place !== place) {
      close(next, at); // leaving "away" (or a missed exit from the other place)
      next.current = { place, since: at };
    }
  } else if (next.current?.place === place || next.current === null) {
    close(next, at);
    next.current = { place: 'away', since: at };
  }
  next.pending = next.pending.filter((v) => at - new Date(v.end).getTime() < MAX_AGE_MS);
  return next;
}

/** Upload queued visits. Used by the background task (raw fetch with the stored token) and by
 * the app on resume (through the API client, which can refresh an expired token). */
async function upload(visits: VisitIn[], fromBackground: boolean): Promise<boolean> {
  if (!visits.length) return true;
  try {
    if (!fromBackground) {
      await meApi.visits(visits);
      return true;
    }
    const raw = await readItem('lung.session');
    const token = raw ? (JSON.parse(raw) as { access?: string }).access : undefined;
    if (!token) return false;
    const res = await fetch(`${API_URL}/v1/me/visits`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ visits }),
    });
    return res.ok; // a 401 (expired token) waits for the app to open and refresh
  } catch {
    return false;
  }
}

export async function flushVisits(fromBackground = false): Promise<void> {
  const s = await load();
  const batch = s.pending.slice(0, MAX_PER_UPLOAD);
  if (batch.length && (await upload(batch, fromBackground))) {
    const after = await load(); // events may have arrived meanwhile
    after.pending = after.pending.slice(batch.length);
    await save(after);
  }
}

if (Platform.OS !== 'web') {
  TaskManager.defineTask<{ eventType: Location.GeofencingEventType; region: Location.LocationRegion }>(
    GEOFENCE_TASK,
    async ({ data, error }) => {
      if (error || !data?.region?.identifier) return;
      const place = data.region.identifier as PlaceName;
      if (place !== 'home' && place !== 'office') return;
      const entered = data.eventType === Location.GeofencingEventType.Enter;
      await save(applyEvent(await load(), place, entered, Date.now()));
      await flushVisits(true);
    },
  );
}

export type GeofenceStatus = 'on' | 'off' | 'unsupported';

export async function geofenceStatus(): Promise<GeofenceStatus> {
  if (Platform.OS === 'web') return 'unsupported';
  return (await Location.hasStartedGeofencingAsync(GEOFENCE_TASK)) ? 'on' : 'off';
}

export class NeedsAlwaysPermission extends Error {}

/** Asks for location "while using", then "all the time" (Android 10+ requires the second,
 * granted from the system settings screen), then starts the two geofences. */
export async function startGeofencing(home: { lat: number; lon: number }, office: { lat: number; lon: number }) {
  const fg = await Location.requestForegroundPermissionsAsync();
  if (!fg.granted) throw new NeedsAlwaysPermission('Location permission was not given.');
  const bg = await Location.requestBackgroundPermissionsAsync();
  if (!bg.granted) throw new NeedsAlwaysPermission('Choose "Allow all the time" for location.');
  await Location.startGeofencingAsync(GEOFENCE_TASK, [
    { identifier: 'home', latitude: home.lat, longitude: home.lon, radius: RADIUS_M, notifyOnEnter: true, notifyOnExit: true },
    { identifier: 'office', latitude: office.lat, longitude: office.lon, radius: RADIUS_M, notifyOnEnter: true, notifyOnExit: true },
  ]);
}

export async function stopGeofencing() {
  if (await Location.hasStartedGeofencingAsync(GEOFENCE_TASK)) {
    await Location.stopGeofencingAsync(GEOFENCE_TASK);
  }
  await AsyncStorage.removeItem(STATE_KEY);
}
