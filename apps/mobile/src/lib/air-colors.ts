/**
 * Outdoor PM2.5 (µg/m³) → colour and words, for the map and place cards. The steps follow
 * the WHO 24-hour guideline (15) and the usual AQI breakpoints (35 / 55 / 150 / 250).
 * This is about the air outside, not the Lung Load score.
 */
export const AIR_STEPS = [
  { max: 15, color: '#3BB273', label: 'Clean', hint: 'Within the WHO guideline' },
  { max: 35, color: '#A3C653', label: 'Fair', hint: 'Fine for most people' },
  { max: 55, color: '#F2C14E', label: 'Moderate', hint: 'Sensitive people may notice' },
  { max: 150, color: '#EE7F45', label: 'Poor', hint: 'Limit long, hard outdoor exercise' },
  { max: 250, color: '#D64545', label: 'Very poor', hint: 'Keep outdoor time short' },
  { max: Infinity, color: '#8E3BA8', label: 'Severe', hint: 'Stay indoors if you can' },
] as const;

export function airStep(pm25: number) {
  return AIR_STEPS.find((s) => pm25 <= s.max) ?? AIR_STEPS[AIR_STEPS.length - 1];
}
