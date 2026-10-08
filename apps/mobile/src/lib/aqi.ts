/**
 * AQI from PM2.5, on the scale the person chose (Settings): India's National AQI (CPCB,
 * default) or the US EPA AQI (used by IQAir, aqi.in and most international apps).
 *
 * AQI is a 0-500 index for OUTDOOR air. Both official scales are defined on 24-hour averages;
 * like most apps we apply them to the current hour too, so "AQI now" is indicative.
 * Only PM2.5 is used (the official AQI takes the worst of several pollutants; PM2.5 is the
 * deciding one on almost every Indian day).
 *
 * Sources: CPCB National Air Quality Index (2014) PM2.5 breakpoints; US EPA AQI technical
 * assistance document (PM2.5 breakpoints as revised in 2024).
 */
import AsyncStorage from '@react-native-async-storage/async-storage';
import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';

export type AqiScale = 'in' | 'us';

interface Band {
  cLo: number; // PM2.5 µg/m³
  cHi: number;
  iLo: number; // index
  iHi: number;
  label: string;
  color: string;
}

const INDIA: Band[] = [
  { cLo: 0, cHi: 30, iLo: 0, iHi: 50, label: 'Good', color: '#2E9E4F' },
  { cLo: 31, cHi: 60, iLo: 51, iHi: 100, label: 'Satisfactory', color: '#8BC34A' },
  { cLo: 61, cHi: 90, iLo: 101, iHi: 200, label: 'Moderate', color: '#E8B923' },
  { cLo: 91, cHi: 120, iLo: 201, iHi: 300, label: 'Poor', color: '#F08A24' },
  { cLo: 121, cHi: 250, iLo: 301, iHi: 400, label: 'Very poor', color: '#D93B30' },
  { cLo: 251, cHi: 380, iLo: 401, iHi: 500, label: 'Severe', color: '#8E1B1B' },
];

const US: Band[] = [
  { cLo: 0, cHi: 9.0, iLo: 0, iHi: 50, label: 'Good', color: '#2E9E4F' },
  { cLo: 9.1, cHi: 35.4, iLo: 51, iHi: 100, label: 'Moderate', color: '#E8B923' },
  { cLo: 35.5, cHi: 55.4, iLo: 101, iHi: 150, label: 'Unhealthy for sensitive groups', color: '#F08A24' },
  { cLo: 55.5, cHi: 125.4, iLo: 151, iHi: 200, label: 'Unhealthy', color: '#D93B30' },
  { cLo: 125.5, cHi: 225.4, iLo: 201, iHi: 300, label: 'Very unhealthy', color: '#8F3F97' },
  { cLo: 225.5, cHi: 325.4, iLo: 301, iHi: 500, label: 'Hazardous', color: '#7E0023' },
];

export interface Aqi {
  value: number;
  label: string;
  color: string;
  scale: AqiScale;
}

export function aqi(pm25: number, scale: AqiScale): Aqi {
  // Each scale truncates the concentration first: India to whole µg/m³, US to 0.1.
  const c = scale === 'in' ? Math.floor(Math.max(0, pm25)) : Math.floor(Math.max(0, pm25) * 10) / 10;
  const bands = scale === 'in' ? INDIA : US;
  const band = bands.find((b) => c <= b.cHi) ?? bands[bands.length - 1];
  const value =
    c > band.cHi
      ? band.iHi // beyond the top of the scale
      : Math.round(((band.iHi - band.iLo) / (band.cHi - band.cLo)) * (c - band.cLo) + band.iLo);
  return { value, label: band.label, color: band.color, scale };
}

/** The scale's bands for a legend: index range, label, colour. */
export function aqiBands(scale: AqiScale) {
  return (scale === 'in' ? INDIA : US).map((b) => ({ from: b.iLo, label: b.label, color: b.color }));
}

/** A MapLibre colour expression on PM2.5 that matches the chosen AQI scale's colours. */
export function aqiColorExpression(scale: AqiScale): unknown[] {
  const stops: (number | string)[] = [];
  for (const b of scale === 'in' ? INDIA : US) stops.push((b.cLo + b.cHi) / 2, b.color);
  return ['interpolate', ['linear'], ['get', 'pm25'], ...stops];
}

export const SCALE_NAME: Record<AqiScale, string> = { in: 'India AQI', us: 'US AQI' };

/** The person's chosen scale, remembered on the phone. */
export const useAqiScale = create<{ scale: AqiScale; setScale: (s: AqiScale) => void }>()(
  persist(
    (set) => ({ scale: 'in', setScale: (scale) => set({ scale }) }),
    { name: 'lung.aqi-scale', storage: createJSONStorage(() => AsyncStorage) },
  ),
);
