/** Every endpoint the app uses, one function each. Paths match the API's /v1 routes. */
import { api } from './client';
import type {
  ActivityDayOut,
  ActivityIn,
  Catalog,
  CommuteOut,
  GridOut,
  HistoryOut,
  LocationIn,
  LocationOut,
  PlaceAirOut,
  RoutePlanOut,
  IndoorIn,
  MeOut,
  PlaceOut,
  ProfileIn,
  ProfileOut,
  ScoreOut,
  SessionOut,
  SimulateIn,
  SimulateOut,
  TrackPointIn,
  TravelLegOut,
  TripIn,
  TripOut,
  VisitIn,
} from './types';

const post = <T>(path: string, body?: unknown, auth = true) =>
  api<T>(path, { method: 'POST', body: body ?? {}, auth });

export const authApi = {
  register: (email: string, password: string) =>
    post<SessionOut>('/v1/auth/register', { email, password }, false),
  login: (email: string, password: string) =>
    post<SessionOut>('/v1/auth/login', { email, password }, false),
  google: (id_token: string) => post<SessionOut>('/v1/auth/google', { id_token }, false),
  logout: (refresh_token: string) => post<void>('/v1/auth/logout', { refresh_token }, false),
  me: () => api<MeOut>('/v1/auth/me'),
  verifyEmail: (code: string) => post<void>('/v1/auth/verify-email', { code }),
  resendCode: () => post<void>('/v1/auth/verify-email/resend'),
  forgot: (email: string) => post<void>('/v1/auth/password/forgot', { email }, false),
  reset: (email: string, code: string, new_password: string) =>
    post<void>('/v1/auth/password/reset', { email, code, new_password }, false),
  changePassword: (current_password: string, new_password: string) =>
    post<SessionOut>('/v1/auth/password/change', { current_password, new_password }),
};

export const meApi = {
  profile: () => api<ProfileOut>('/v1/me/profile'),
  saveProfile: (p: ProfileIn) => api<ProfileOut>('/v1/me/profile', { method: 'PUT', body: p }),
  saveIndoor: (i: IndoorIn) => api<PlaceOut>('/v1/me/indoor', { method: 'PUT', body: i }),
  visits: (visits: VisitIn[]) => post<{ accepted: number }>('/v1/me/visits', { visits }),
  registerDevice: (fcm_token: string, platform: 'android' | 'ios') =>
    post<void>('/v1/me/devices', { fcm_token, platform }),
  removeDevice: (token: string) =>
    api<void>(`/v1/me/devices/${encodeURIComponent(token)}`, { method: 'DELETE' }),
  deleteAccount: () => api<void>('/v1/me', { method: 'DELETE' }),
  commute: () => api<CommuteOut>('/v1/me/commute'),
};

export const scoreApi = {
  today: () => api<ScoreOut>('/v1/me/score/today'),
  forecast: () => api<ScoreOut>('/v1/me/score/forecast'),
  simulate: (s: SimulateIn) => post<SimulateOut>('/v1/me/score/simulate', s),
  history: (days = 14) => api<HistoryOut>(`/v1/me/score/history?days=${days}`),
};

export const mapApi = {
  grid: (b: { south: number; west: number; north: number; east: number }) =>
    api<GridOut>(
      `/v1/map/grid?south=${b.south}&west=${b.west}&north=${b.north}&east=${b.east}`,
    ),
  place: (lat: number, lon: number) => api<PlaceAirOut>(`/v1/map/place?lat=${lat}&lon=${lon}`),
  route: (from: { lat: number; lon: number }, to: { lat: number; lon: number }) =>
    post<RoutePlanOut>('/v1/map/route', {
      from_lat: from.lat,
      from_lon: from.lon,
      to_lat: to.lat,
      to_lon: to.lon,
    }),
};

export const locationApi = {
  get: () => api<LocationOut>('/v1/me/location'),
  set: (l: LocationIn) => post<LocationOut>('/v1/me/location', l),
};

export const tracksApi = {
  upload: (points: TrackPointIn[]) => post<{ points: number; legs: number }>('/v1/me/tracks', { points }),
  today: () => api<{ date: string; legs: TravelLegOut[] }>('/v1/me/tracks'),
  deleteAll: () => api<{ deleted: number }>('/v1/me/tracks', { method: 'DELETE' }),
};

export const tripsApi = {
  list: () => api<{ trips: TripOut[] }>('/v1/me/trips'),
  add: (t: TripIn) => post<TripOut>('/v1/me/trips', t),
  remove: (id: number) => api<void>(`/v1/me/trips/${id}`, { method: 'DELETE' }),
};

export const activityApi = {
  log: (activities: ActivityIn[]) => post<{ ids: number[] }>('/v1/me/activity', { activities }),
  day: () => api<ActivityDayOut>('/v1/me/activity'),
  remove: (id: number) => api<void>(`/v1/me/activity/${id}`, { method: 'DELETE' }),
};

export const metaApi = {
  catalog: () => api<Catalog>('/v1/catalog', { auth: false }),
};
