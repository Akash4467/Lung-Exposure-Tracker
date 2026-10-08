/**
 * Words for the commute footprint (GET /v1/me/footprint). Every figure is an estimate with a
 * range, and it is CO2 (climate), never "air pollution saved": PM2.5 is what Lung Load is about.
 */
import type { FootprintOut, KgRange } from './api/types';
import { MODES } from './labels';

export const modeName = (m: string) =>
  m === 'two_wheeler'
    ? 'two-wheeler'
    : (MODES.find((x) => x.value === m)?.label ?? m).toLowerCase();

/** "by metro", "on foot", "by bike"… */
export const byMode = (m: string) =>
  m === 'walk' ? 'on foot' : m === 'cycle' ? 'by bike' : `by ${modeName(m)}`;

/** 0.4 → "0.4", 12.3 → "12", 1234 → "1,234": precise enough for an estimate, no more. */
export function kg(v: number): string {
  const n = Math.max(0, v);
  if (n < 10) return (Math.round(n * 10) / 10).toString();
  return Math.round(n).toLocaleString('en-IN');
}

/** "2.4–6.4" (never below zero: a pessimistic saving of "-1 kg" reads as nonsense). */
export const kgRange = (r: KgRange) => `${kg(r.low)}–${kg(r.high)}`;

const DAYS = [
  '',
  'one day',
  'two days',
  'three days',
  'four days',
  'five days',
  'six days',
  'every day',
];

export type Headline = { text: string; tone: 'good' | 'maybe' | 'neutral' };

/** The one sentence under the weekly figure on the Trends card. */
export function headline(f: FootprintOut): Headline | null {
  const c = f.commute;
  if (!c) return null;
  const s = c.suggestion;
  if (s && s.clear) {
    return {
      tone: 'good',
      text:
        `${cap(DAYS[s.days_per_week] ?? `${s.days_per_week} days`)} a week ${byMode(s.mode)} ` +
        `would save about ${kg(s.week_kg_saved.central)} kg a week ` +
        `(about ${kg(s.year_kg_saved.central)} kg a year).`,
    };
  }
  if (c.vs_car_week_kg && c.vs_car_week_kg.central > 0) {
    return {
      tone: 'good',
      text: `Compared with driving alone, you avoid about ${kg(c.vs_car_week_kg.central)} kg a week.`,
    };
  }
  if (s) {
    return {
      tone: 'maybe',
      text:
        `${cap(DAYS[s.days_per_week] ?? `${s.days_per_week} days`)} a week ${byMode(s.mode)} ` +
        `might save around ${kg(s.week_kg_saved.central)} kg a week, but the estimates overlap.`,
    };
  }
  return {
    tone: 'neutral',
    text: 'None of the realistic alternatives would clearly cut this.',
  };
}

const cap = (t: string) => t.charAt(0).toUpperCase() + t.slice(1);
