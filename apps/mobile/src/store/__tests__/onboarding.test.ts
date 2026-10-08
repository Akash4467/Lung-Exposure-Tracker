/// <reference types="jest" />
import { addMinutes, display, fromMinutes, toMinutes } from '@/lib/time';

import { ageError, type Draft, missingStep, scheduleError, toProfileIn, weightError } from '../onboarding';

const base: Draft = {
  age: '29',
  sex: 'woman',
  sensitive: true,
  weight: '55',
  home: { label: 'Home', lat: 28.63, lon: 77.22 },
  office: { label: 'Office', lat: 28.62, lon: 77.37 },
  schedule: {
    wake: '07:00',
    leave_home: '08:30',
    arrive_office: '09:30',
    leave_office: '18:00',
    arrive_home: '19:00',
    sleep: '23:00',
    commute_mode: 'two_wheeler',
    office_days: [1, 2, 3, 4, 5, 6],
  },
  size: '2bhk',
  windows: 'closed',
  purifier: true,
  cadr: '250',
  sources: [{ kind: 'cooking_lpg', start: '19:30', minutes: 45 }],
};

test.each([
  ['', null],
  ['2', 'Enter an age between 3 and 110'],
  ['3', null],
  ['110', null],
  ['111', 'Enter an age between 3 and 110'],
])('age %p', (age, err) => expect(ageError(age)).toBe(err));

test('weight is optional but bounded', () => {
  expect(weightError('')).toBeNull();
  expect(weightError('9')).not.toBeNull();
  expect(weightError('72.5')).toBeNull();
});

test('schedule order mirrors the API rule', () => {
  expect(scheduleError(base.schedule)).toBeNull();
  expect(scheduleError({ ...base.schedule, arrive_home: '17:00' })).toMatch(/in order/);
  expect(scheduleError({ ...base.schedule, sleep: '07:00' })).toMatch(/different/);
});

test('missing earlier answers send the user back', () => {
  expect(missingStep(base, 'details')).toBeNull();
  expect(missingStep({ ...base, sex: null }, 'details')).toBe('/profile');
  expect(missingStep({ ...base, office: null }, 'details')).toBe('/places');
  expect(missingStep({ ...base, office: null }, 'places')).toBeNull();
});

test('the request body matches the API schema', () => {
  const body = toProfileIn(base);
  expect(body).toMatchObject({
    age: 29,
    sex: 'woman',
    sensitive: true,
    weight_kg: 55,
    places: {
      home: { purifier: true, purifier_cadr_m3h: 250, size: '2bhk', windows: 'closed' },
      office: { label: 'Office' },
    },
    schedule: { commute_mode: 'two_wheeler', commute_mask: 'none', office_days: [1, 2, 3, 4, 5, 6] },
  });
  expect(typeof body.timezone).toBe('string');
  // No purifier: no CADR sent even if one was typed earlier.
  expect(toProfileIn({ ...base, purifier: false }).places.home.purifier_cadr_m3h).toBeNull();
});

test('time helpers wrap around midnight', () => {
  expect(addMinutes('23:45', 30)).toBe('00:15');
  expect(addMinutes('00:00', -15)).toBe('23:45');
  expect(fromMinutes(toMinutes('08:30'))).toBe('08:30');
  expect(display('00:05')).toBe('12:05 am');
  expect(display('13:30')).toBe('1:30 pm');
});
