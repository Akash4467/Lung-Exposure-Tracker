# Engine parameters: values, sources and reasoning

Every number lives in `apps/api/src/lung/engine/config.yaml`. This page says where each one comes from and how sure we are, so the team can answer "where do the numbers come from?" and know which values to re-check before launch.

**Status key**

- **Sourced:** the number is taken directly from a named standard or guideline.
- **Range-based:** chosen from inside a range reported in published studies. The exact number is our judgement.
- **Design choice:** a product decision, not a scientific constant.
- **Calibrated:** set so that default inputs reproduce the design-doc numbers.
- **Verify:** check against the primary source before public launch.

> The score is an *estimate of exposure*, not a measurement of lung health. Every screen says so.

**Principle:** every refinement is optional. A user who gives no extra details gets the design-doc behaviour exactly (the worked-example test proves it). Each detail they add makes the estimate more personal and **narrows its uncertainty range**.

## Formulas

```
breathed C  = (C_outdoor × F  +  C_sources) × mask
dose D      = Σ  breathed C × IR × t                  (µg)
reference   = Σ  15 × IR × t                          (µg; same day at the WHO guideline)
score       = 100 × D / reference × M
cigarettes  = 24 h time-weighted breathed C / 22
```

A score of 100 means "breathed exactly the WHO-guideline dose for this routine".
The reference dose has no indoor, cabin or mask benefit, so protecting yourself lowers the score.

## Anchors

| Parameter | Value | Status | Source |
| --- | --- | --- | --- |
| `who_guideline_ugm3` | 15 µg/m³ | Sourced | WHO Global Air Quality Guidelines (2021): PM2.5 24-hour guideline level |
| `bands.green_max` | 100 | Design choice | Score 100 = the WHO 24 h guideline dose |
| `bands.amber_max` | 400 | Sourced + design choice | India NAAQS (CPCB, 2009): PM2.5 24-hour standard 60 µg/m³ = 4 × 15 |
| `cigarette_ugm3` | 22 µg/m³ | Sourced (rule of thumb) | Berkeley Earth, Muller & Muller (2015), "Air Pollution and Cigarette Equivalence". A communication aid only |

## Breathing rate

### Without weight: table (`inhalation_m3_per_h`)

| Activity | Man | Woman | Child (3-11) | Status |
| --- | --- | --- | --- | --- |
| asleep | 0.45 | 0.38 | 0.35 | Range-based, **Verify** |
| light (indoors, seated, car, two-wheeler) | 0.80 | 0.70 | 0.60 | Range-based, **Verify** |
| walk (walking, bus and metro incl. walking to stops) | 1.40 | 1.20 | 1.00 | Range-based, **Verify** |
| cycle | 2.40 | 2.00 | 1.60 | Range-based, **Verify** |
| run (jogging/running, ~8 METs) | 3.00 | 2.60 | 2.00 | Range-based, **Verify** (EFH "high intensity" rows) |

- These values come from the design doc. Their size is in line with US EPA *Exposure Factors Handbook (EFH), 2011 Edition*, Chapter 6. Check them against that chapter's tables before launch.
- Ages 3-11 use the child column; 12 and over use the adult column for their sex. "Other" uses the average of man and woman.

### With weight: personal rate (`breathing_personal`) (refinement #5)

```
rate (m³/h) = BMR(kcal/day)/24 × MET × 0.209 L O2/kcal × 27 L air per L O2 / 1000
```

| Parameter | Value | Status | Source |
| --- | --- | --- | --- |
| `oxygen_l_per_kcal` | 0.209 | Sourced, **Verify** | EPA EFH method: H = 0.05 L O2 per kJ (× 4.184 kJ/kcal) |
| `ventilatory_equivalent` | 27 | Sourced, **Verify** | EPA EFH method: litres of air breathed per litre of O2 used |
| `bmr` equations | by sex and age band | Sourced, **Verify** | WHO/FAO/UNU (1985) BMR equations from body weight |
| `met` | asleep 0.95, light 2.0, walk 3.5, run 8.0, cycle 6.8 | Range-based | Compendium of Physical Activities (Ainsworth et al.): sleeping ≈ 0.95, light home activity ≈ 2, walking ≈ 3.5, jogging ≈ 7-8, cycling to work ≈ 6.8 |

Check: a 35-year-old, 70 kg man comes out at light 0.79 m³/h and walking 1.39 m³/h, which matches the table, so the two methods agree for a typical adult.

### Measured exertion (`activity`) (Lung Load)

When the phone or a watch measures what the person was doing, that replaces the schedule's guess for those minutes (only for the past, never ahead of `now`). An interval carries a kind (`asleep`/`light`/`walk`/`run`/`cycle`) and optionally a measured MET. With a MET, the personal formula above is used; if no weight was given, a typical weight stands in (`breathing_personal.default_weight`).

| Input | Formula | Parameters | Status | Source |
| --- | --- | --- | --- | --- |
| Heart rate | MET = 1 + r × (METmax − 1), where r = (HR − HRrest) / (HRmax − HRrest) | HRmax = 208 − 0.7 × age; METmax = 15.3 × HRmax / HRrest / 3.5; HRrest default 70 | Sourced, **Verify** | Swain & Leutholtz 1997 (%HRR ≈ %VO2R); Tanaka et al. 2001 (HRmax); Uth et al. 2004 (VO2max ratio) |
| Steps per minute | linear between points | 0→1.3, 60→2.0, 100→3.0, 130→5.0, 160→8.0, 180→10.0 | Range-based, **Verify** | CADENCE-Adults (Tudor-Locke et al. 2019): 100 steps/min ≈ 3 METs, 130 ≈ 5 METs; upper points extrapolated for running |
| Kind from MET | walk ≥ 2.5, run ≥ 6.0 when moving | `activity.kind_thresholds` | Design choice | Moderate / vigorous cut-offs (3 / 6 METs) |
| Typical weight | adults: man 65, woman 55, other 60 kg; ≤5 y: 2 × age + 8; 6-17 y: min(adult, 3 × age + 7) | `breathing_personal.default_weight` | Range-based, **Verify** | Indian adult reference weights (ICMR-NIN 2020); child rule-of-thumb weight-for-age formulas |

**Exercise near home or work counts as outdoors.** A walk or run whose location is home or work is taken to be outside (factor 1.0, no indoor sources) unless the interval says `outdoors: false` (a treadmill or gym). Activity during the commute just changes the breathing rate; a measured walk/run/cycle on the commute uses outdoor air.

**What the score means with exercise.** The score compares the day's dose with the *same day, breathed at the same rates*, in WHO-guideline air. So a run in clean air barely moves the score, while a run in dirty air raises it (more of the day's breathing happens in bad, unfiltered air). The absolute dose (µg) and the air breathed (`air_m3`, shown as litres per minute) do rise with exercise in any air, and the result lists each activity's share of the dose (`by_activity`).

## Commute

### Per mode

| Mode | Activity | Factor | Why |
| --- | --- | --- | --- |
| walk | walk | 1.0 | Outdoors |
| cycle | cycle | 1.0 | Outdoors |
| bus, metro | walk | 1.0 | Walking to stops is a big part of the trip; metro platforms can be as bad as the street, so no benefit is claimed (one option until 8 Oct 2026; split for the commute footprint, same values) |
| two_wheeler | light | 1.0 | Seated, in open air. The design doc said "walk"; changed so the dose isn't overstated |
| car | light | 0.6 | Range-based, **Verify**: in-car studies report cabin PM2.5 well below outside with windows up. 0.6 assumes the fan on fresh air, which is cautious |

When the phone sees the person **walking or cycling**, the factor is 1.0 whatever their usual mode is.

### Route-aware (`road_factor`) (refinement #2)

The route comes from OpenRouteService once, when home and office are saved, as sample points along the way, each tagged with its road type. The commute time is split equally across the points, in travel order (reversed on the way home). Each piece uses its own cell's air × mode factor × road factor.

| Road type | Factor | Status |
| --- | --- | --- |
| motorway, trunk | 1.3 | Range-based, **Verify** |
| primary | 1.2 | Range-based, **Verify** |
| secondary | 1.1 | Range-based, **Verify** |
| tertiary | 1.05 | Range-based |
| residential, path, unknown | 1.0 | Design choice |

Near-road studies find PM2.5 raised next to busy roads, though by far less than traffic gases like NO2. The factors are deliberately modest. Without a route, the midpoint cell is used with factor 1.0.

### Masks (`mask_factor`)

| Mask | Factor | Status | Reasoning |
| --- | --- | --- | --- |
| n95 | 0.3 | Range-based | Filters at least 95% in the lab. OSHA gives fit-tested half masks a protection factor of 10, i.e. 0.1 (29 CFR 1910.134). The public is rarely fit-tested, so 0.3 |
| surgical | 0.7 | Range-based, **Verify** | Loose fit; leaks at the edges dominate |
| cloth | 0.8 | Range-based, **Verify** | Low filtration of fine particles, plus leaks |

## Indoor air: mass-balance model (refinement #3)

```
indoor = P·a/(a+k+c) × outdoor  +  Σ E / (V·(a+k+c))
```

P is penetration, a is air exchange per hour (from the window state), k is deposition per hour, c is purifier removal per hour (= CADR / V), E is source emission in µg/h, and V is volume in m³.

| Parameter | Value | Status | Reasoning |
| --- | --- | --- | --- |
| `penetration` P | 0.8 | Range-based | Reviews (e.g. Chen & Zhao 2011, *Atmospheric Environment* 45: 275-288) report PM2.5 penetration close to 1 for leaky buildings and lower for tight ones |
| `deposition_per_h` k | 0.4 | Range-based | Within the published range for PM2.5 settling indoors (roughly 0.1-0.5 per hour) |
| `air_exchange_per_h` a | closed 0.4, normal 0.667, open 2.8 | Calibrated + range-based | Chosen so the indoor factor is exactly 0.4 / 0.5 / 0.7, as in the design doc. Values in the 0.3-3 per hour range are typical of naturally ventilated homes |
| `default_purifier_removal_per_h` | 1.067 | Calibrated | Normal windows + purifier = 0.25, as in the design doc. Used when CADR is unknown |
| `volume_m3` | 1rk 70, 1bhk 125, 2bhk 210, 3bhk 310, 4bhk+ 420, office 1000 | Design choice | Typical floor area × 2.8 m ceiling. Default 2BHK |

**Why steady state is enough:** for a first-order system, the total exposure from a burst of emitted mass M is M / (V·(a+k+c)), however the burst is spread over time. So applying the steady-state level while a source runs gives the right daily dose.

**Behaviour that changed from the simple model:** a purifier with open windows now gives 0.525, not 0.35, because a purifier can't keep up with an open window. With windows closed it gives 0.171.

### Indoor sources (`indoor.sources`, mg PM2.5 per minute while running)

| Source | mg/min | Status | Note |
| --- | --- | --- | --- |
| cooking_lpg | 1.0 | Range-based, **Verify** | Gas cooking studies report widely varying emissions; frying is the highest |
| cooking_electric | 0.5 | Range-based, **Verify** | Food itself emits, especially frying |
| cooking_kerosene | 5.0 | Range-based, **Verify** | |
| cooking_biomass | 15.0 | Range-based, **Verify** | Wood, dung or crop-residue stoves produce very high indoor PM2.5 |
| incense | 0.5 | Range-based, **Verify** | |
| mosquito_coil | 2.0 | Range-based, **Verify** | Liu et al. (2003), *Environmental Health Perspectives* 111: 1454: one coil's PM2.5 compares with 75-137 cigarettes |
| smoking | 1.7 | Range-based, **Verify** | About 12 mg per cigarette over about 7 minutes |
| candle | 0.1 | Range-based | |

### Tips for indoor sources (`indoor.source_tips`)

Each source kind has its own tip: the text, how much of its emission the action leaves (`scale`), and whether it's free. Closing windows is *not* suggested when indoor sources dominate, because less ventilation traps the smoke; the engine works this out by recalculating, not by a rule.

| Source | Tip | scale | Free | Status |
| --- | --- | --- | --- | --- |
| cooking (LPG, electric) | Run the kitchen exhaust or open a window while cooking | 0.5 | yes | Design choice, **Verify** against range-hood capture studies |
| cooking_kerosene | Open a window and run the exhaust while cooking | 0.5 | yes | Design choice |
| cooking_biomass | Cook outside or under a chimney hood when you can | 0.5 | no | Design choice |
| incense | Burn incense less often, or by an open window | 0.5 | yes | Design choice |
| mosquito_coil | Use a mosquito net or plug-in repellent instead of coils | 0 | no | Removes the source |
| smoking | Smoke outside, not indoors | 0 | yes | Removes the indoor source |
| candle | Light fewer candles indoors | 0.5 | yes | Design choice |

**Adding a new source** means adding a line here and in `config.yaml` (emission plus tip); no code changes. Sources only count while the person is at home, and they're time-windowed (for example cooking 19:30 for 45 minutes, or a coil from 22:00 overnight).

Example: LPG cooking in a default 2BHK with normal windows adds about **268 µg/m³ while cooking**.

## Sensitivity multiplier M

| Group | M | Status |
| --- | --- | --- |
| Adult | 1.0 | Design choice |
| Age 65 and over | 1.3 | Design choice |
| Child (11 or under), or self-declared respiratory condition | 1.5 | Design choice |

This is a **UX weighting, not a clinical risk factor**. When more than one applies, the highest is used.

## Air data correction with stations (`air_correction`) (refinement #1)

For each hour and cell: ratio = observed / model at each nearby station. Ratios are averaged in log space with weights of 1/distance², then shrunk towards "no correction" by trust = Σw / (Σw + prior), and clamped to ×¼ … ×4.

| Parameter | Value | Status | Why |
| --- | --- | --- | --- |
| `radius_km` | 30 | Design choice | Beyond this a station says little about the cell |
| `distance_floor_km` | 1 | Design choice | Avoids infinite weight |
| `prior_weight` | 0.01 | Design choice | One station at 10 km gets 50% trust; 3 km gets about 92% |
| `max_ratio` | 4 | Design choice | Guards against a broken station |

Stations come from OpenAQ / CPCB (layer 7). Until then, cells are uncorrected and the uncertainty range stays wider.

## Time-in-place from geofences (refinement #4)

Phone visits (home, office, or away = outside both) replace the declared schedule **only for minutes already past**; the rest of the day stays declared. Rules:

- At home during declared sleep counts as asleep, unless activity recognition says otherwise.
- "Away" uses the commute air. A trip between home and office follows the route; an errand from home and back uses the home cell's air.
- Walking or cycling seen by the phone counts as outdoor air (factor 1.0), even for car commuters.

## Forecast (refinement #7)

| Parameter | Value | Status | Why |
| --- | --- | --- | --- |
| `nowcast_tau_h` | 6 h | Design choice, **calibrate** | The model's current error (observed / model) carries forward and fades as exp(−lead/τ) in log space |
| `nowcast_max_ratio` | 4 | Design choice | Clamp |
| `fire_risk_upwind_count` | low ≥ 1, medium ≥ 25, high ≥ 100 | Design choice, **calibrate** | Upwind FIRMS detections in the last 48 h |
| `fire_pm25_uplift_per_fire` | **0** | Design choice | Fire raises a **risk flag only** until we can fit an uplift to real data. We never invent a PM2.5 number |

## Uncertainty range (refinement #8)

200 Monte Carlo runs. In each run the uncertain inputs are multiplied by a log-normal draw (median 1, spread σ), the day is recomputed, and we report the 10th, 50th and 90th percentiles of the score plus the chance of each band. The random generator is seeded, so the same input always gives the same range.

| Input | σ (unknown) | σ (known) | Known when |
| --- | --- | --- | --- |
| Outdoor air (one draw for all cells) | 0.45 | 0.2 | the cell is station-corrected |
| Breathing | 0.25 (table) | 0.15 (personal) | weight is given |
| Home volume | 0.35 | 0.1 | home size is given |
| Purifier strength | 0.4 | 0.15 | CADR is given |
| Penetration / deposition / air exchange | 0.1 / 0.3 / 0.4 | — | always uncertain |
| Source emissions | 0.6 | — | always uncertain |
| Mask fit | 0.3 | — | always uncertain |
| Road factor (excess over 1) | 0.1 | — | |

All σ values are **Design choice, calibrate**: once the validation study exists, set them so that about 80% of measured days fall inside the p10-p90 range.

Worked example: score 622 (central), likely range about **320-1,110**, red with about 78% probability. The range is wide because, with no station nearby, the outdoor air data is the biggest unknown.

## Engine behaviour decisions

- **Hours that don't line up:** readings are stored by UTC hour, and India is UTC+5:30. Every concentration is time-weighted by overlapping minutes, never looked up by local hour.
- **Missing data:** a needed hour with no reading raises `MissingReadingError`. The service decides on a fallback and reports `data_as_of`.
- **Tips:** the same day recalculated with one change each. Up to 3 tips, each saving at least 3%, always including at least one free action. One commute shift is offered, the smallest among near-ties.
- **Cigarette equivalent:** uses the concentration actually breathed, including indoor sources, so the indoor sources and protective actions both show up in it.

## Validation still to do

1. Check the breathing table, EFH H/VQ and the BMR equations against the primary sources.
2. Cite primary studies for the car-cabin, road, deposition and source-emission values.
3. Compare Open-Meteo with CPCB/OpenAQ stations for the demo city over 2-3 days, and report the mean difference.
4. **Personal-monitor study:** a few volunteers carry a calibrated monitor for a week. Compare measured and estimated exposure, then tune the config and the σ values so about 80% of days fall inside p10-p90.
5. Store an `engine_version` with every saved score, so scores stay comparable after tuning.
