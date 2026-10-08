import { aqi } from '@/lib/aqi';

describe('India National AQI (PM2.5)', () => {
  it.each([
    [0, 0, 'Good'],
    [30, 50, 'Good'],
    [45, 75, 'Satisfactory'],
    [67, 121, 'Moderate'], // Delhi on the map today
    [90, 200, 'Moderate'],
    [100, 232, 'Poor'],
    [127, 306, 'Very poor'],
    [300, 439, 'Severe'],
    [999, 500, 'Severe'], // capped at the top of the scale
  ])('%s µg/m³ -> %s (%s)', (pm25, value, label) => {
    const a = aqi(pm25, 'in');
    expect(a.value).toBe(value);
    expect(a.label).toBe(label);
  });

  it('truncates to whole µg/m³ first, as CPCB does', () => {
    expect(aqi(30.9, 'in').value).toBe(50);
  });
});

describe('US EPA AQI (PM2.5, 2024 breakpoints)', () => {
  it.each([
    [5, 28, 'Good'],
    [9.0, 50, 'Good'],
    [35.4, 100, 'Moderate'],
    [45, 124, 'Unhealthy for sensitive groups'], // the "AQI 124" seen online
    [67, 159, 'Unhealthy'],
    [150, 225, 'Very unhealthy'],
    [400, 500, 'Hazardous'],
  ])('%s µg/m³ -> %s (%s)', (pm25, value, label) => {
    const a = aqi(pm25, 'us');
    expect(a.value).toBe(value);
    expect(a.label).toBe(label);
  });

  it('the same air reads higher on the US scale', () => {
    expect(aqi(67, 'us').value).toBeGreaterThan(aqi(67, 'in').value);
  });
});
