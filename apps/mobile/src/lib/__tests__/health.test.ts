/// <reference types="jest" />
import { toActivities } from '../health';

const NOW = Date.parse('2026-10-05T12:00:00Z');
const at = (minAgo: number) => new Date(NOW - minAgo * 60_000).toISOString();

test('a run session becomes one run, with the heart rate during it', () => {
  const out = toActivities(
    {
      sessions: [{ startTime: at(90), endTime: at(60), exerciseType: 56 }],
      heartRate: [
        { time: at(80), beatsPerMinute: 150 },
        { time: at(70), beatsPerMinute: 160 },
      ],
      steps: [],
      restingHr: 58,
    },
    NOW,
  );
  expect(out).toEqual([
    {
      start: at(90),
      end: at(60),
      kind: 'run',
      heart_rate: 155,
      resting_hr: 58,
      source: 'health_connect',
    },
  ]);
});

test('treadmill runs are indoors; yoga without heart data is skipped', () => {
  const out = toActivities(
    {
      sessions: [
        { startTime: at(200), endTime: at(170), exerciseType: 57 },
        { startTime: at(120), endTime: at(100), exerciseType: 83 },
      ],
      heartRate: [],
      steps: [],
    },
    NOW,
  );
  expect(out).toHaveLength(1);
  expect(out[0]).toMatchObject({ kind: 'run', outdoors: false });
});

test('an unlogged brisk walk shows up from steps, merged into one interval', () => {
  // 1500 steps over 15 minutes = 100 steps/min
  const out = toActivities(
    { sessions: [], heartRate: [], steps: [{ startTime: at(30), endTime: at(15), count: 1500 }] },
    NOW,
  );
  expect(out).toHaveLength(1);
  expect(out[0]).toMatchObject({ steps_per_min: 100, source: 'health_connect' });
  expect(Date.parse(out[0].end) - Date.parse(out[0].start)).toBe(15 * 60_000);
});

test('raised heart rate without steps counts (e.g. cycling); resting heart rate does not', () => {
  const out = toActivities(
    {
      sessions: [],
      heartRate: [
        { time: at(52), beatsPerMinute: 135 },
        { time: at(47), beatsPerMinute: 132 },
        { time: at(20), beatsPerMinute: 72 },
      ],
      steps: [],
      restingHr: 65,
    },
    NOW,
  );
  expect(out).toHaveLength(1);
  expect(out[0].heart_rate).toBeGreaterThanOrEqual(130);
  expect(out[0].steps_per_min).toBeUndefined();
});

test('nothing older than 47 hours is sent', () => {
  const out = toActivities(
    {
      sessions: [{ startTime: at(48 * 60), endTime: at(47.5 * 60), exerciseType: 56 }],
      heartRate: [],
      steps: [],
    },
    NOW,
  );
  expect(out).toEqual([]);
});
