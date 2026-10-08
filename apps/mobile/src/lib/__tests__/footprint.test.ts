import type { FootprintOut } from '../api/types';
import { byMode, headline, kg, kgRange } from '../footprint';

const r = (low: number, central: number, high: number) => ({
  low,
  central,
  high,
});

function fp(over: Partial<NonNullable<FootprintOut['commute']>> = {}): FootprintOut {
  return {
    estimate: true,
    unit: 'kg CO2',
    commute: {
      mode: 'car',
      one_way_km: 10,
      days_per_week: 5,
      week_km: 100,
      week_kg: r(11.1, 14, 21.3),
      year_kg: r(533, 672, 1022),
      modes: [],
      vs_car_week_kg: null,
      suggestion: null,
      route: 'openrouteservice',
      ...over,
    },
    recorded: null,
    sources: [],
  };
}

describe('footprint words', () => {
  it('rounds like an estimate and never shows a negative', () => {
    expect(kg(0.04)).toBe('0');
    expect(kg(3.24)).toBe('3.2');
    expect(kg(12.6)).toBe('13');
    expect(kg(-2)).toBe('0');
    expect(kgRange(r(-1.2, 2, 6.44))).toBe('0–6.4');
  });

  it('names the way of travelling naturally', () => {
    expect(byMode('metro')).toBe('by metro');
    expect(byMode('two_wheeler')).toBe('by two-wheeler');
    expect(byMode('walk')).toBe('on foot');
    expect(byMode('cycle')).toBe('by bike');
  });

  it('leads with a clear swap', () => {
    const h = headline(
      fp({
        suggestion: {
          mode: 'bus',
          days_per_week: 2,
          week_kg_saved: r(3.2, 5, 8),
          year_kg_saved: r(155, 240, 384),
          clear: true,
        },
      }),
    );
    expect(h).toEqual({
      tone: 'good',
      text: 'Two days a week by bus would save about 5 kg a week (about 240 kg a year).',
    });
  });

  it('credits low-carbon commuters against driving', () => {
    const h = headline(fp({ mode: 'bus', vs_car_week_kg: r(17, 26.5, 43) }));
    expect(h?.text).toBe('Compared with driving alone, you avoid about 27 kg a week.');
  });

  it('is honest when the ranges overlap', () => {
    const h = headline(
      fp({
        mode: 'metro',
        suggestion: {
          mode: 'bus',
          days_per_week: 2,
          week_kg_saved: r(-0.5, 1.2, 2),
          year_kg_saved: r(-24, 58, 96),
          clear: false,
        },
      }),
    );
    expect(h?.tone).toBe('maybe');
    expect(h?.text).toContain('the estimates overlap');
  });

  it('never calls CO2 air pollution', () => {
    const texts = [
      headline(fp({ vs_car_week_kg: r(1, 2, 3), mode: 'bus' }))?.text,
      headline(fp())?.text,
    ].join(' ');
    expect(texts.toLowerCase()).not.toMatch(/pollution|pm2\.5|air quality/);
  });

  it('has nothing to say without a commute', () => {
    expect(headline({ ...fp(), commute: null })).toBeNull();
  });
});
