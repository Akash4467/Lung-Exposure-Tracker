/**
 * "Glass and air": a light, airy base (off-white with soft pastel light), frosted glass
 * surfaces, near-black pill buttons and big light headings. Behind the glass, the air itself
 * is drawn (components/air-backdrop.tsx): a breeze on clean days, smoke on polluted ones.
 * Light only for now (decided 2026-10-05); dark can be added later.
 */
export type Band = 'green' | 'amber' | 'red';

const light = {
  background: '#F3F4F6',
  surface: '#FFFFFF',
  surfaceMuted: '#ECEDEF',
  border: '#E1E3E7',
  text: '#121417',
  textMuted: '#61666F',
  primary: '#121417', // black pill buttons, selected states
  primaryText: '#FFFFFF',
  accent: '#2F8F6A', // links, "free" labels, breeze green
  danger: '#B3261E',
  dangerSurface: '#FBEAE8',
  // Frosted glass: translucent white over the air, with a bright hairline edge.
  glass: 'rgba(255,255,255,0.66)',
  glassStrong: 'rgba(255,255,255,0.86)',
  glassBorder: 'rgba(255,255,255,0.9)',
  glassShadow: 'rgba(30,40,60,0.10)',
  field: 'rgba(236,237,240,0.92)', // input fields
  band: {
    green: { fg: '#1E7A4C', bg: 'rgba(214,240,225,0.9)' },
    amber: { fg: '#94600A', bg: 'rgba(251,236,206,0.9)' },
    red: { fg: '#B3261E', bg: 'rgba(250,222,218,0.92)' },
  },
  split: { home: '#3E8E6E', commute: '#D09A34', office: '#6A7FB8' },
  activity: {
    asleep: '#8E96B8',
    light: '#A7B0A9',
    walk: '#3E8E6E',
    run: '#E07B39',
    cycle: '#4C8DC9',
  },
};

export type Colors = typeof light;

export function useColors(): Colors {
  return light;
}

export const space = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, xxl: 32 } as const;
export const radius = { sm: 10, md: 16, lg: 24, pill: 999 } as const;

export const type = {
  hero: { fontSize: 68, lineHeight: 76, fontWeight: '700', letterSpacing: -0.5 },
  display: { fontSize: 44, lineHeight: 50, fontWeight: '600', letterSpacing: -0.3 },
  title: { fontSize: 32, lineHeight: 38, fontWeight: '600' },
  heading: { fontSize: 20, lineHeight: 26, fontWeight: '500' },
  body: { fontSize: 16, lineHeight: 22, fontWeight: '400' },
  label: { fontSize: 14, lineHeight: 20, fontWeight: '600' },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: '400' },
  overline: { fontSize: 12, lineHeight: 16, fontWeight: '600', letterSpacing: 1 },
} as const;

/**
 * The app ships its own typefaces so it looks the same on every phone, whatever font the
 * phone's theme uses:
 *   - Fredoka for headings and big numbers: chunky, rounded and playful;
 *   - Inter for body text, labels and inputs: plain and easy to read.
 * Android needs one font file per weight, so text picks the family from its variant and
 * weight (AppText does this).
 */
export const DISPLAY_FONTS = {
  '300': 'Fredoka_500Medium',
  '400': 'Fredoka_500Medium',
  '500': 'Fredoka_500Medium',
  '600': 'Fredoka_600SemiBold',
  '700': 'Fredoka_700Bold',
} as const;

export const DISPLAY_VARIANTS: ReadonlySet<string> = new Set(['hero', 'display', 'title', 'heading']);

export const FONTS = {
  '300': 'Inter_300Light',
  '400': 'Inter_400Regular',
  '500': 'Inter_500Medium',
  '600': 'Inter_600SemiBold',
  '700': 'Inter_700Bold',
} as const;

export function fontFor(weight?: string | number, display = false): string {
  const w = weight === 'bold' ? '700' : weight === 'normal' || weight == null ? '400' : String(weight);
  const set = display ? DISPLAY_FONTS : FONTS;
  return set[w as keyof typeof set] ?? (Number(w) >= 600 ? set['600'] : set['400']);
}

export const BAND_LABEL: Record<Band, string> = {
  green: 'Low',
  amber: 'Elevated',
  red: 'High',
};
