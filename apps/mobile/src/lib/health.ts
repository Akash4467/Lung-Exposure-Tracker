/**
 * Health Connect (Android): heart rate, steps and workouts from the phone or a watch, turned
 * into activity for Lung Load. Read-only; nothing is written to Health Connect.
 *
 * What is sent (POST /v1/me/activity, source "health_connect"), for the last 48 hours:
 *  - workouts (exercise sessions): their kind (run / walk / cycle / other) and, if the watch
 *    recorded heart rate during them, the average; indoor kinds (treadmill, gym bike) are
 *    marked indoors;
 *  - outside workouts, 5-minute stretches of raised heart rate (≥ resting + 25 bpm) and of
 *    brisk stepping (≥ 60 steps/min), so walks and runs nobody logged still count.
 * The server turns heart rate / steps into effort (MET) and replaces earlier Health Connect
 * data for the same hours, so syncing again never double counts.
 */
import { Platform } from 'react-native';

import { activityApi } from '@/lib/api/endpoints';
import type { ActivityIn } from '@/lib/api/types';

const WINDOW_MS = 47 * 3600_000; // the API accepts the last 48 hours
const BUCKET_MS = 5 * 60_000;
const MIN_STEPS_PER_MIN = 60;
const RAISED_HR = 25; // bpm above resting that counts as effort

export const HEALTH_PERMISSIONS = [
  { accessType: 'read', recordType: 'HeartRate' },
  { accessType: 'read', recordType: 'RestingHeartRate' },
  { accessType: 'read', recordType: 'Steps' },
  { accessType: 'read', recordType: 'ExerciseSession' },
] as const;

// Health Connect ExerciseType codes → our activity kinds (others count by heart rate only).
const RUN = new Set([56, 57]); // running, treadmill
const WALK = new Set([79, 37]); // walking, hiking
const CYCLE = new Set([8, 9]); // biking, stationary bike
const INDOOR = new Set([57, 9, 25, 53, 68, 69, 70, 74, 83]); // treadmill, gym machines, pool, yoga…

type HC = typeof import('react-native-health-connect');

async function hc(): Promise<HC | null> {
  if (Platform.OS !== 'android') return null;
  try {
    return await import('react-native-health-connect');
  } catch {
    return null; // a build without the native module
  }
}

export type HealthStatus = 'unsupported' | 'needs-install' | 'off' | 'on';

export async function healthStatus(): Promise<HealthStatus> {
  const m = await hc();
  if (!m) return 'unsupported';
  const sdk = await m.getSdkStatus();
  if (sdk !== m.SdkAvailabilityStatus.SDK_AVAILABLE) return 'needs-install';
  await m.initialize();
  const granted = await m.getGrantedPermissions();
  const need = new Set(['HeartRate', 'Steps', 'ExerciseSession']);
  const have = granted.filter((p) => 'recordType' in p && need.has(p.recordType)).length;
  return have >= need.size ? 'on' : 'off';
}

export async function connectHealth(): Promise<boolean> {
  const m = await hc();
  if (!m) return false;
  await m.initialize();
  const granted = await m.requestPermission([...HEALTH_PERMISSIONS]);
  return granted.length > 0;
}

export async function openHealthSettings(): Promise<void> {
  (await hc())?.openHealthConnectSettings();
}

/** Pure: Health Connect records → activity intervals. Exported for tests. */
export function toActivities(
  input: {
    sessions: { startTime: string; endTime: string; exerciseType: number }[];
    heartRate: { time: string; beatsPerMinute: number }[];
    steps: { startTime: string; endTime: string; count: number }[];
    restingHr?: number;
  },
  now: number,
): ActivityIn[] {
  const resting = input.restingHr ?? 70;
  const out: ActivityIn[] = [];
  const hr = input.heartRate
    .map((s) => ({ t: Date.parse(s.time), bpm: s.beatsPerMinute }))
    .filter((s) => now - s.t < WINDOW_MS && s.t <= now)
    .sort((a, b) => a.t - b.t);
  const avgHr = (from: number, to: number) => {
    const xs = hr.filter((s) => s.t >= from && s.t < to).map((s) => s.bpm);
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : undefined;
  };

  // 1) workouts
  const busy: [number, number][] = [];
  for (const s of input.sessions) {
    const a = Date.parse(s.startTime);
    const b = Math.min(Date.parse(s.endTime), now);
    if (b <= a || now - a > WINDOW_MS) continue;
    const kind = RUN.has(s.exerciseType)
      ? 'run'
      : WALK.has(s.exerciseType)
        ? 'walk'
        : CYCLE.has(s.exerciseType)
          ? 'cycle'
          : undefined;
    const heart = avgHr(a, b);
    if (!kind && heart === undefined) continue; // e.g. yoga with no heart data: nothing to say
    out.push({
      start: new Date(a).toISOString(),
      end: new Date(b).toISOString(),
      ...(kind ? { kind } : {}),
      ...(heart !== undefined ? { heart_rate: Math.round(heart) } : {}),
      ...(INDOOR.has(s.exerciseType) ? { outdoors: false } : {}),
      resting_hr: input.restingHr,
      source: 'health_connect',
    });
    busy.push([a, b]);
  }
  const inWorkout = (t: number) => busy.some(([a, b]) => t >= a && t < b);

  // 2) 5-minute buckets outside workouts: brisk stepping or raised heart rate
  const start = Math.floor((now - WINDOW_MS) / BUCKET_MS) * BUCKET_MS;
  const stepsIn = (from: number, to: number) =>
    input.steps.reduce((sum, r) => {
      const a = Date.parse(r.startTime);
      const b = Date.parse(r.endTime);
      const overlap = Math.min(b, to) - Math.max(a, from);
      return overlap > 0 && b > a ? sum + (r.count * overlap) / (b - a) : sum;
    }, 0);
  for (let t = start; t + BUCKET_MS <= now; t += BUCKET_MS) {
    if (inWorkout(t)) continue;
    const perMin = stepsIn(t, t + BUCKET_MS) / 5;
    const heart = avgHr(t, t + BUCKET_MS);
    const brisk = perMin >= MIN_STEPS_PER_MIN;
    const raised = heart !== undefined && heart >= resting + RAISED_HR;
    if (!brisk && !raised) continue;
    out.push({
      start: new Date(t).toISOString(),
      end: new Date(t + BUCKET_MS).toISOString(),
      ...(brisk ? { steps_per_min: Math.round(perMin) } : {}),
      ...(raised && !brisk ? { heart_rate: Math.round(heart!) } : {}),
      resting_hr: input.restingHr,
      source: 'health_connect',
    });
  }
  return mergeAdjacent(out);
}

/** Join back-to-back buckets with the same signal into one interval (fewer, longer rows). */
function mergeAdjacent(xs: ActivityIn[]): ActivityIn[] {
  const sorted = [...xs].sort((a, b) => a.start.localeCompare(b.start));
  const out: ActivityIn[] = [];
  for (const x of sorted) {
    const last = out[out.length - 1];
    const sameKind =
      last &&
      !last.kind &&
      !x.kind &&
      (last.steps_per_min !== undefined) === (x.steps_per_min !== undefined) &&
      last.end === x.start;
    if (sameKind && last) {
      const w1 = Date.parse(last.end) - Date.parse(last.start);
      const w2 = Date.parse(x.end) - Date.parse(x.start);
      const avg = (p?: number, q?: number) =>
        p === undefined || q === undefined ? undefined : Math.round((p * w1 + q * w2) / (w1 + w2));
      last.end = x.end;
      if (last.steps_per_min !== undefined)
        last.steps_per_min = avg(last.steps_per_min, x.steps_per_min);
      if (last.heart_rate !== undefined) last.heart_rate = avg(last.heart_rate, x.heart_rate);
    } else {
      out.push({ ...x });
    }
  }
  return out;
}

/** Read the last 48 hours from Health Connect and send them. Returns how many intervals. */
export async function syncHealth(): Promise<number> {
  const m = await hc();
  if (!m) return 0;
  await m.initialize();
  const now = Date.now();
  const timeRangeFilter = {
    operator: 'between' as const,
    startTime: new Date(now - WINDOW_MS).toISOString(),
    endTime: new Date(now).toISOString(),
  };
  const read = async <T>(type: Parameters<HC['readRecords']>[0]): Promise<T[]> => {
    try {
      const all: T[] = [];
      let pageToken: string | undefined;
      do {
        const page = await m.readRecords(type, { timeRangeFilter, pageSize: 1000, pageToken });
        all.push(...(page.records as unknown as T[]));
        pageToken = page.pageToken || undefined;
      } while (pageToken && all.length < 20_000);
      return all;
    } catch {
      return []; // that permission wasn't granted: use what we can read
    }
  };
  const [sessions, hrRecords, steps, resting] = await Promise.all([
    read<{ startTime: string; endTime: string; exerciseType: number }>('ExerciseSession'),
    read<{ samples: { time: string; beatsPerMinute: number }[] }>('HeartRate'),
    read<{ startTime: string; endTime: string; count: number }>('Steps'),
    read<{ time: string; beatsPerMinute: number }>('RestingHeartRate'),
  ]);
  const latestResting = resting.sort((a, b) => b.time.localeCompare(a.time))[0]?.beatsPerMinute;
  const activities = toActivities(
    { sessions, heartRate: hrRecords.flatMap((r) => r.samples), steps, restingHr: latestResting },
    now,
  );
  for (let i = 0; i < activities.length; i += 500) {
    await activityApi.log(activities.slice(i, i + 500));
  }
  return activities.length;
}

let lastSync = 0;
const SYNC_EVERY_MS = 15 * 60_000;

/** Quiet background sync when the app opens: only if connected, at most every 15 minutes. */
export async function syncHealthIfDue(): Promise<void> {
  if (Date.now() - lastSync < SYNC_EVERY_MS) return;
  try {
    if ((await healthStatus()) !== 'on') return;
    lastSync = Date.now();
    await syncHealth();
  } catch {
    // never block or crash the app over a sync; the next opening tries again
  }
}
