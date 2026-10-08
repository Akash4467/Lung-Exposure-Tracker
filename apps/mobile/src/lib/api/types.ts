/**
 * Mirrors apps/api/src/lung/api/schemas/*.py field for field (snake_case, no renaming), so a
 * field has the same name on the server, on the wire and in the app.
 */
import type { Band } from '@/theme';

export type { Band };
export type Sex = 'man' | 'woman' | 'other';
export type Windows = 'closed' | 'normal' | 'open';
export type CommuteMode = 'walk' | 'cycle' | 'bus_metro' | 'two_wheeler' | 'car';
export type Mask = 'none' | 'cloth' | 'surgical' | 'n95';
export type Activity = 'asleep' | 'light' | 'walk' | 'run' | 'cycle';
export type HHMM = string; // "08:30", local wall-clock time

// ---------------------------------------------------------------- auth

export interface SessionOut {
  access_token: string;
  token_type: 'bearer';
  expires_at: string;
  refresh_token: string;
  user_id: string;
  is_new_user: boolean;
}

export interface MeOut {
  user_id: string;
  email: string | null;
  email_verified: boolean;
  has_password: boolean;
  google_linked: boolean;
  onboarded: boolean;
}

// ---------------------------------------------------------------- profile

export interface SourceIn {
  kind: string;
  start: HHMM;
  minutes: number;
}

export interface PlaceIn {
  label?: string | null;
  lat: number;
  lon: number;
  windows?: Windows;
  purifier?: boolean;
  purifier_cadr_m3h?: number | null;
  size?: string | null;
  sources?: SourceIn[];
}

export interface PlaceOut extends Required<Omit<PlaceIn, 'label'>> {
  label: string | null;
  cell_id: string;
}

export interface ScheduleIn {
  wake: HHMM;
  leave_home: HHMM;
  arrive_office: HHMM;
  leave_office: HHMM;
  arrive_home: HHMM;
  sleep: HHMM;
  commute_mode: CommuteMode;
  commute_mask?: Mask;
  office_days?: number[]; // ISO weekdays, 1 = Monday
}

export interface ProfileIn {
  age: number;
  sex: Sex;
  sensitive?: boolean;
  weight_kg?: number | null;
  timezone?: string;
  places: { home: PlaceIn; office: PlaceIn };
  schedule: ScheduleIn;
}

export interface ProfileOut {
  age: number;
  sex: Sex;
  sensitive: boolean;
  weight_kg: number | null;
  timezone: string;
  places: { home: PlaceOut; office: PlaceOut };
  schedule: Required<ScheduleIn>;
}

export interface IndoorIn {
  place: 'home' | 'office';
  windows?: Windows;
  purifier?: boolean;
  purifier_cadr_m3h?: number;
  clear_cadr?: boolean;
  size?: string;
  sources?: SourceIn[] | null;
}

export interface VisitIn {
  place: 'home' | 'office' | 'away';
  start: string; // ISO with offset
  end: string;
  activity?: Activity | null;
}

// ---------------------------------------------------------------- scores

export interface Tip {
  id: string;
  text: string;
  saves_pct: number;
  free: boolean;
}

export interface HourOut {
  start: string;
  pm25: number;
}

export interface ScoreOut {
  date: string;
  is_forecast: boolean;
  score: number;
  range: { p10: number; p90: number };
  band: Band;
  band_probability: Partial<Record<Band, number>>;
  dose_ug: number;
  cigarettes: number;
  avg_pm25: number;
  split: { home: number; commute: number; office: number };
  indoor_source_share: number;
  /** Share of the day's dose while asleep / light / walk / run / cycle. */
  by_activity: Partial<Record<Activity, number>>;
  breathing_lpm: number | null; // average litres of air per minute
  air_litres: number | null; // air breathed over the day
  ref_ug: number | null; // the same breathing at the WHO guideline (15 µg/m³)
  sensitivity: number | null; // >1 for children, 65+ or a lung condition
  times_who: number | null; // score ÷ 100
  trip: { id: number; label: string } | null; // this day is spent on a trip
  tips: Tip[];
  hours: HourOut[];
  worst_hours: HourOut[];
  best_outdoor_hours: HourOut[];
  fire_risk: 'none' | 'low' | 'medium' | 'high' | null;
  data_as_of: string;
  computed_at: string | null;
  engine_version: string;
  estimated: true;
  disclaimer: string;
}

// ---------------------------------------------------------------- lung load

export interface ActivityIn {
  start: string; // ISO with offset
  end: string;
  kind?: Activity;
  heart_rate?: number;
  resting_hr?: number; // from the watch, improves heart-rate effort
  steps_per_min?: number;
  met?: number;
  outdoors?: boolean | null;
  source?: 'manual' | 'activity_recognition' | 'health_connect';
}

export interface ActivityOut {
  id: number;
  start: string;
  end: string;
  kind: Activity;
  met: number | null;
  outdoors: boolean | null;
  source: string;
  heart_rate: number | null;
  steps_per_min: number | null;
}

export interface ActivityDayOut {
  date: string;
  activities: ActivityOut[];
}

export interface DayOut {
  date: string;
  score: number;
  band: Band;
  dose_ug: number;
  avg_pm25: number;
  breathing_lpm: number | null;
  by_activity: Partial<Record<Activity, number>>;
}

export interface Insights {
  days: number;
  avg_score_7d: number | null;
  avg_score_prev_7d: number | null;
  change_pct: number | null; // negative = better than last week
  bands: Record<Band, number>;
  worst_day: { date: string; score: number } | null;
  best_day: { date: string; score: number } | null;
  exercise_share: number;
  avg_breathing_lpm: number | null;
}

export interface HistoryOut {
  days: DayOut[];
  insights: Insights;
  estimated: true;
  disclaimer: string;
}

// ---------------------------------------------------------------- map

export interface GridOut {
  step: number; // degrees between points
  points: { lat: number; lon: number; pm25: number }[];
  source: string;
  estimated: true;
}

export interface PlaceAirOut {
  lat: number;
  lon: number;
  utc_offset_s: number;
  now: { pm25: number; pm10: number | null; hour: string } | null;
  hours: { hour: string; pm25: number; is_forecast: boolean }[];
  days: { date: string; avg_pm25: number; max_pm25: number; best_hours: string[] }[];
  source: string;
  estimated: true;
}

export interface CommuteLeg {
  depart: string; // UTC hour
  avg_pm25: number | null;
  points: { lat: number; lon: number; road_class: string; pm25: number | null }[];
}

export interface CommuteOut {
  mode: CommuteMode;
  mask: Mask;
  source: string | null;
  distance_km: number | null;
  home: { lat: number; lon: number; label: string | null };
  office: { lat: number; lon: number; label: string | null };
  morning: CommuteLeg;
  evening: CommuteLeg;
  modes: {
    mode: CommuteMode;
    inside_pm25: number;
    breathing_m3_per_h: number;
    ug_per_hour: number;
    current: boolean;
  }[];
  estimated: true;
}

export interface TripIn {
  label: string;
  lat: number;
  lon: number;
  start_date: string; // YYYY-MM-DD, inclusive
  end_date: string;
}

export interface TripOut extends TripIn {
  id: number;
  days: number;
  status: 'now' | 'upcoming';
}

export type LocationIn =
  | { kind: 'home' }
  | { kind: 'place'; label: string; lat: number; lon: number };

export type LocationOut = { kind: 'home' } | { kind: 'trip'; trip: TripOut };

export interface TrackPointIn {
  t: string; // ISO
  lat: number;
  lon: number;
  speed?: number; // m/s
  accuracy?: number; // metres
  activity?: 'walking' | 'running' | 'cycling' | 'automotive' | 'stationary';
  confidence?: 'low' | 'medium' | 'high';
}

export interface TravelLegOut {
  id: number;
  start: string;
  end: string;
  mode: 'walk' | 'run' | 'cycle' | 'bus_metro' | 'two_wheeler' | 'car';
  distance_m: number;
  path: [number, number][]; // [lat, lon], simplified
  source: 'gps' | 'gps+activity';
}

export interface RouteOptionOut {
  id: string;
  profile: 'driving-car' | 'cycling-regular' | 'foot-walking';
  distance_km: number;
  duration_min: number;
  avg_pm25: number | null;
  path: [number, number, number | null][]; // [lat, lon, roadside pm2.5]
  fastest: boolean;
  cleanest: boolean;
}

export interface RoutePlanOut {
  from: { lat: number; lon: number };
  to: { lat: number; lon: number };
  options: RouteOptionOut[];
  modes: {
    mode: CommuteMode;
    option_id: string;
    duration_min: number;
    inside_pm25: number;
    dose_ug: number;
  }[];
  cleaner_by_pct: number;
  routes_from: 'openrouteservice' | 'straight_line';
  estimated: true;
}

export interface SimulateIn {
  commute_shift_minutes?: number;
  mitigations?: string[];
}

export interface Brief {
  score: number;
  band: Band;
  dose_ug: number;
  cigarettes: number;
}

export interface SimulateOut {
  before: Brief;
  after: Brief;
  saves_pct: number;
  as_workday: boolean;
  estimated: true;
}

export interface Catalog {
  indoor_sources: { kind: string; tip: string | null }[];
  home_sizes: string[];
  windows: Windows[];
  commute_modes: CommuteMode[];
  masks: Mask[];
  mitigations: string[];
  bands: { green_max: number; amber_max: number };
  disclaimer: string;
  engine_version: string;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: { field: string; message: string }[] };
}
