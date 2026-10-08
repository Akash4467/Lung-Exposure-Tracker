/**
 * The onboarding draft: kept on the phone until the last step sends it in one request
 * (PUT /v1/me/profile). Also used to prefill "Edit profile".
 */
import { create } from 'zustand';

import type {
  CommuteMode,
  PlaceIn,
  ProfileIn,
  ProfileOut,
  ScheduleIn,
  Sex,
  SourceIn,
  Windows,
} from '@/lib/api/types';
import { deviceTimeZone, toMinutes } from '@/lib/time';

export interface PlaceDraft {
  label: string;
  detail?: string;
  lat: number;
  lon: number;
}

export interface Draft {
  age: string; // text while typing
  sex: Sex | null;
  sensitive: boolean;
  weight: string; // optional
  home: PlaceDraft | null;
  office: PlaceDraft | null;
  schedule: Required<Pick<ScheduleIn, 'wake' | 'leave_home' | 'arrive_office' | 'leave_office' | 'arrive_home' | 'sleep'>> & {
    commute_mode: CommuteMode;
    office_days: number[];
  };
  // optional details
  size: string | null;
  windows: Windows;
  purifier: boolean;
  cadr: string;
  sources: SourceIn[];
}

const initial: Draft = {
  age: '',
  sex: null,
  sensitive: false,
  weight: '',
  home: null,
  office: null,
  schedule: {
    wake: '07:00',
    leave_home: '08:30',
    arrive_office: '09:30',
    leave_office: '18:00',
    arrive_home: '19:00',
    sleep: '23:00',
    commute_mode: 'bus_metro',
    office_days: [1, 2, 3, 4, 5],
  },
  size: null,
  windows: 'normal',
  purifier: false,
  cadr: '',
  sources: [],
};

interface Store extends Draft {
  set: (patch: Partial<Draft>) => void;
  setSchedule: (patch: Partial<Draft['schedule']>) => void;
  fromProfile: (p: ProfileOut) => void;
  reset: () => void;
}

export const useDraft = create<Store>((set) => ({
  ...initial,
  set: (patch) => set(patch),
  setSchedule: (patch) => set((s) => ({ schedule: { ...s.schedule, ...patch } })),
  fromProfile: (p) =>
    set({
      age: String(p.age),
      sex: p.sex,
      sensitive: p.sensitive,
      weight: p.weight_kg ? String(p.weight_kg) : '',
      home: { label: p.places.home.label ?? 'Home', lat: p.places.home.lat, lon: p.places.home.lon },
      office: {
        label: p.places.office.label ?? 'Office',
        lat: p.places.office.lat,
        lon: p.places.office.lon,
      },
      schedule: {
        wake: p.schedule.wake,
        leave_home: p.schedule.leave_home,
        arrive_office: p.schedule.arrive_office,
        leave_office: p.schedule.leave_office,
        arrive_home: p.schedule.arrive_home,
        sleep: p.schedule.sleep,
        commute_mode: p.schedule.commute_mode,
        office_days: p.schedule.office_days,
      },
      size: p.places.home.size,
      windows: p.places.home.windows,
      purifier: p.places.home.purifier,
      cadr: p.places.home.purifier_cadr_m3h ? String(p.places.home.purifier_cadr_m3h) : '',
      sources: p.places.home.sources,
    }),
  reset: () => set(initial),
}));

// ---------------------------------------------------------------- validation (mirrors the API)

export function ageError(age: string): string | null {
  if (!age) return null;
  const n = Number(age);
  return Number.isInteger(n) && n >= 3 && n <= 110 ? null : 'Enter an age between 3 and 110';
}

export function weightError(w: string): string | null {
  if (!w) return null;
  const n = Number(w);
  return n >= 10 && n <= 300 ? null : 'Enter a weight between 10 and 300 kg';
}

export function scheduleError(s: Draft['schedule']): string | null {
  const order = [s.leave_home, s.arrive_office, s.leave_office, s.arrive_home].map(toMinutes);
  if (!(order[0] < order[1] && order[1] < order[2] && order[2] < order[3])) {
    return 'Trips must be in order: leave home, reach work, leave work, reach home.';
  }
  if (s.wake === s.sleep) return 'Wake-up and bedtime must be different.';
  return null;
}

export function toProfileIn(d: Draft): ProfileIn {
  if (!d.sex || !d.home || !d.office) throw new Error('incomplete draft');
  const home: PlaceIn = {
    label: d.home.label,
    lat: d.home.lat,
    lon: d.home.lon,
    windows: d.windows,
    purifier: d.purifier,
    purifier_cadr_m3h: d.purifier && d.cadr ? Number(d.cadr) : null,
    size: d.size,
    sources: d.sources,
  };
  return {
    age: Number(d.age),
    sex: d.sex,
    sensitive: d.sensitive,
    weight_kg: d.weight ? Number(d.weight) : null,
    timezone: deviceTimeZone(),
    places: {
      home,
      office: { label: d.office.label, lat: d.office.lat, lon: d.office.lon },
    },
    schedule: { ...d.schedule, commute_mask: 'none' },
  };
}

/** The first step whose answers are missing (e.g. after the app was restarted mid-way), so a
 * later step can send the user back there instead of failing at the end. */
export function missingStep(d: Draft, upTo: 'places' | 'schedule' | 'details'): '/profile' | '/places' | null {
  if (!d.age || ageError(d.age) || !d.sex || weightError(d.weight)) return '/profile';
  if (upTo !== 'places' && (!d.home || !d.office)) return '/places';
  return null;
}
