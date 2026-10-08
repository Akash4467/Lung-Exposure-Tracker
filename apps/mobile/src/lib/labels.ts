/** Human names for the API's machine values. Unknown values (e.g. a new indoor source
 * added to the server's config.yaml) still get a readable fallback, so the catalog can grow
 * without an app update. */
import type { CommuteMode, Windows } from './api/types';

export const MODES: readonly { value: CommuteMode; label: string }[] = [
  { value: 'walk', label: 'Walk' },
  { value: 'cycle', label: 'Cycle' },
  { value: 'bus_metro', label: 'Bus / metro' },
  { value: 'two_wheeler', label: 'Two-wheeler' },
  { value: 'car', label: 'Car' },
];

export const WINDOWS: readonly { value: Windows; label: string }[] = [
  { value: 'closed', label: 'Mostly closed' },
  { value: 'normal', label: 'Sometimes open' },
  { value: 'open', label: 'Mostly open' },
];

const SIZES: Record<string, string> = {
  '1rk': '1 RK',
  '1bhk': '1 BHK',
  '2bhk': '2 BHK',
  '3bhk': '3 BHK',
  '4bhk_plus': '4 BHK+',
};

const SOURCES: Record<string, { label: string; start: string; minutes: number }> = {
  cooking_lpg: { label: 'Cooking on gas (LPG)', start: '19:30', minutes: 45 },
  cooking_electric: { label: 'Cooking on electric / induction', start: '19:30', minutes: 45 },
  cooking_kerosene: { label: 'Cooking on kerosene', start: '19:30', minutes: 45 },
  cooking_biomass: { label: 'Cooking on wood / dung / chulha', start: '19:00', minutes: 60 },
  incense: { label: 'Incense / agarbatti', start: '07:00', minutes: 20 },
  mosquito_coil: { label: 'Mosquito coil', start: '22:00', minutes: 480 },
  smoking: { label: 'Smoking indoors', start: '21:00', minutes: 7 },
  candle: { label: 'Candles', start: '19:00', minutes: 60 },
};

const humanize = (v: string) => v.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

export const sizeLabel = (v: string) => SIZES[v] ?? humanize(v);
export const sourceLabel = (kind: string) => SOURCES[kind]?.label ?? humanize(kind);
export const sourceDefaults = (kind: string) =>
  SOURCES[kind] ?? { label: humanize(kind), start: '20:00', minutes: 30 };

export function minutesLabel(m: number): string {
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  return r ? `${h} h ${r} min` : `${h} h`;
}
