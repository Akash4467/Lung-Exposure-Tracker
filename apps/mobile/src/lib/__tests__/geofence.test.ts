/// <reference types="jest" />
/* eslint-disable @typescript-eslint/no-require-imports, import/first -- Jest mocks must be declared before the imports they replace */
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
jest.mock('expo-task-manager', () => ({ defineTask: jest.fn() }));
jest.mock('expo-location', () => ({
  GeofencingEventType: { Enter: 1, Exit: 2 },
  hasStartedGeofencingAsync: jest.fn(),
}));

import { applyEvent } from '../geofence';

const T0 = Date.parse('2026-10-05T02:30:00Z'); // 08:00 in Delhi
const min = (m: number) => T0 + m * 60_000;
const empty = { current: null, pending: [] };

test('a normal day becomes home → away → office → away → home visits', () => {
  let s = applyEvent(empty, 'home', true, min(0));
  s = applyEvent(s, 'home', false, min(30)); // leave home 08:30
  s = applyEvent(s, 'office', true, min(75)); // reach work 09:15
  s = applyEvent(s, 'office', false, min(600)); // leave work 18:00
  s = applyEvent(s, 'home', true, min(660)); // home 19:00
  expect(s.pending.map((v) => v.place)).toEqual(['home', 'away', 'office', 'away']);
  expect(s.pending[1]).toEqual({
    place: 'away',
    start: new Date(min(30)).toISOString(),
    end: new Date(min(75)).toISOString(),
  });
  expect(s.current).toEqual({ place: 'home', since: min(660) });
});

test('a flicker at the edge of a circle is not a visit', () => {
  let s = applyEvent(empty, 'home', true, min(0));
  s = applyEvent(s, 'home', false, min(60));
  s = applyEvent(s, 'home', true, min(61)); // back inside after 1 minute
  expect(s.pending.map((v) => v.place)).toEqual(['home']); // the 1-minute "away" is dropped
});

test('a missed exit is closed by the next enter', () => {
  let s = applyEvent(empty, 'home', true, min(0));
  s = applyEvent(s, 'office', true, min(90)); // never saw "exit home"
  expect(s.pending).toEqual([
    { place: 'home', start: new Date(min(0)).toISOString(), end: new Date(min(90)).toISOString() },
  ]);
  expect(s.current?.place).toBe('office');
});

test('a duplicate enter changes nothing', () => {
  const s1 = applyEvent(empty, 'office', true, min(0));
  const s2 = applyEvent(s1, 'office', true, min(5));
  expect(s2).toEqual(s1);
});

test('visits older than the API accepts are dropped', () => {
  let s = applyEvent(empty, 'home', true, min(0));
  s = applyEvent(s, 'home', false, min(60));
  expect(s.pending).toHaveLength(1);
  s = applyEvent(s, 'office', true, min(60 + 48 * 60)); // two days later
  expect(s.pending.map((v) => v.place)).toEqual(['away']); // the old home visit is gone
});
