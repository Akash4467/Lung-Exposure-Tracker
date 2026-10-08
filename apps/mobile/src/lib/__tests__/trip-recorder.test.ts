/// <reference types="jest" />
/* eslint-disable import/first -- Jest mocks must be declared before the imports they replace */
jest.mock('expo-task-manager', () => ({ defineTask: jest.fn() }));
jest.mock('expo-location', () => ({ Accuracy: { Balanced: 3 } }));

import type { LocationObject } from 'expo-location';

import { appendPoints, bestActivity } from '../trip-recorder';

const NOW = Date.parse('2026-10-05T12:00:00Z');

const loc = (msAgo: number, speed: number | null = 1.3): LocationObject =>
  ({
    timestamp: NOW - msAgo,
    coords: { latitude: 28.6, longitude: 77.2, speed, accuracy: 12 },
  }) as unknown as LocationObject;

test('the most confident detected activity wins', () => {
  expect(
    bestActivity({
      walking: { detected: true, confidence: 'medium' },
      automotive: { detected: true, confidence: 'high' },
      running: { detected: false, confidence: 'low' },
    }),
  ).toEqual({ activity: 'automotive', confidence: 'high' });
  expect(bestActivity({ unknown: { detected: true, confidence: 'high' } })).toEqual({});
  expect(bestActivity(undefined)).toEqual({});
});

test('points carry the reading, drop bad speeds and age out after 47 hours', () => {
  const old = appendPoints([], [loc(48 * 3600_000)], {}, NOW);
  expect(old).toEqual([]);
  const q = appendPoints(
    [],
    [loc(60_000), loc(0, -1)],
    { activity: 'walking', confidence: 'high' },
    NOW,
  );
  expect(q).toHaveLength(2);
  expect(q[0]).toMatchObject({
    lat: 28.6,
    lon: 77.2,
    speed: 1.3,
    activity: 'walking',
  });
  expect(q[1].speed).toBeUndefined(); // the platform's "unknown" speed is not sent
});

test('the queue is capped at 3000 points, keeping the newest', () => {
  const many = Array.from({ length: 3100 }, (_, i) => loc(3100 - i));
  const q = appendPoints([], many, {}, NOW);
  expect(q).toHaveLength(3000);
  expect(q[q.length - 1].t).toBe(new Date(NOW - 1).toISOString());
});
