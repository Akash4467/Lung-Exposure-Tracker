# How the numbers work

Every number the app shows, where it comes from, and the exact formula. Constants live in
`apps/api/src/lung/engine/config.yaml` (sources and reasoning: [engine-parameters.md](engine-parameters.md)).
Code paths are given so each formula can be checked against the implementation.

Units: PM2.5 in **µg/m³** (micrograms per cubic metre of air); doses in **µg** (micrograms
inhaled); breathing in **m³/h** (or L/min on screen; 1 m³/h = 16.7 L/min).

---

## 1. The big picture

```
air data (Open-Meteo, hourly, per ~10 km cell)
      │
      ▼
your day as segments ── where you are, what you're doing, minute by minute
      │                  (schedule → geofence visits → logged activity)
      ▼
for each segment:  air you breathe  =  outdoor PM2.5 × place factor × mask  +  indoor smoke × mask
                   dose (µg)        =  air you breathe × breathing rate × hours
      │
      ▼
Lung Load  =  100 × (your dose ÷ the same breathing in WHO-limit air) × sensitivity
```

**Two different questions:**

| | Answers | Covers | Shown as |
| --- | --- | --- | --- |
| **AQI** | How dirty is the air outside, right now? | Outdoor air, one place, one hour | "AQI 118 · Moderate" |
| **Lung Load** | How much did my lungs take in today, compared with clean (WHO-limit) air? | Your whole day: indoors, commute, work, outdoors, smoke at home, how hard you breathe | "665 · 6.7× the WHO limit" |

They usually don't match, and they shouldn't: a day with moderate outdoor air can still be a heavy Lung Load day because of a mosquito coil at night or a long roadside commute.

---

## 2. Air data

| What | Value | Code |
| --- | --- | --- |
| Source | Open-Meteo air-quality API (CAMS global model), hourly PM2.5 and PM10; wind from Open-Meteo weather | `integrations/open_meteo.py` |
| Grid cell | 0.1° × 0.1° (about 11 km), named like `28.6_77.2` | `domain/geo.py` (`cell_id`) |
| Window kept | yesterday + today + tomorrow (refreshed by the worker) | `services/ingest_service.py` |
| Missing hours | filled from the nearest reading up to 6 h away (earlier first) | `score_service.fill_gaps` |
| Your cells | home, work, and every sampled point along your commute route | `services/plan.py` |

**Local time vs UTC.** Readings are hourly in UTC; India is UTC+5:30, so a local hour spans two UTC hours. Every segment's outdoor PM2.5 is the **time-weighted average** of the UTC hours it overlaps:

```
outdoor(segment) = Σ  PM2.5(hour) × seconds of overlap  ÷  segment length in seconds
```

(`engine/dose.py: outdoor_pm25`)

**Station correction** (built, switched on when ground stations are added in layer 7): the model is scaled towards nearby stations within 30 km, weighting each by 1/distance²; one station at 10 km gets 50 % trust; the scale is capped between ×¼ and ×4 (`engine/airdata.py`).

---

## 3. Your day as segments

The engine paints your local day **minute by minute** (`engine/day.py: build_day`), in layers:

1. **Schedule** (from onboarding): asleep at home, awake at home, commute out, at work, commute back. On a day off: all at home.
2. **Geofence visits** (if "Use my real day" is on): when the phone says you were at home / work / away, that replaces the guess (only for the past). "Away" is treated as travel and uses commute air.
3. **Logged activity** (Lung Load): walking, running, cycling, or heart-rate / step data replace what you were doing for those minutes. Moving near home or work counts as **outdoors** there (unless marked indoors, e.g. a treadmill).
4. **Indoor sources** (cooking, coils, incense…): painted on their own layer, only while you're at home.

Minutes with the same place, activity, exertion, sources and "observed" flag merge into one **segment**. Commute segments are then split evenly along the route's sample points (about every km, up to 20), each with its own grid cell and road type.

---

### Recorded trips (opt-in "Record my trips")

When recording is on, the minutes you were actually travelling replace the guessed day. Each recorded leg has a way of travelling (walk, run, cycle, bus/metro, two-wheeler, car) and the grid cell it went through:

```
leg air you breathe = PM2.5 of the leg's cell × (1.0 on foot or bike, else the vehicle factor) × mask
leg dose            = that × breathing rate for the way of travelling × hours
```

How the way of travelling is decided: the phone's activity reading when it is fairly sure; otherwise speed: under 2.5 m/s (9 km/h) walking, under 4.5 (16 km/h) running, under 8.5 cycling if you cycle to work, else a vehicle; faster is a vehicle (your declared one).

### Trips and "where are you today"

On a trip day (planned from the map, or chosen with the location switch on Today) the day is worked out **at the destination**: a day off there, indoors in a typical room (normal windows: factor 0.5, no purifier, none of your home's smoke sources), with your usual sleep and wake times. The destination's grid cell gives the outdoor air. Choosing **Home** brings back your usual day (home, commute, work).

## 4. The air you actually breathe in each place

```
breathed PM2.5 = outdoor PM2.5 × factor × mask  +  indoor-source PM2.5 × mask
```

(`engine/dose.py: breathed_parts`)

### 4.1 Indoors (home and work): mass-balance model

Outdoor particles leak in, settle, get flushed out or filtered. At steady state:

```
indoor factor  =  P × a  ÷  (a + k + c)
```

| Symbol | Meaning | Value |
| --- | --- | --- |
| P | penetration: share of outdoor particles that make it through gaps | 0.8 |
| a | air exchange per hour, from your windows setting | closed 0.4 · normal 0.667 · open 2.8 |
| k | deposition (particles settling) per hour | 0.4 |
| c | purifier removal per hour = CADR ÷ room volume; if CADR unknown, 1.067 | 0 without a purifier |

Resulting factors: **closed 0.40, normal 0.50, open 0.70, normal + purifier 0.25** (`engine/indoor.py: indoor_factor`).

Room volume = floor area × 2.8 m ceiling: 1RK 70 m³, 1BHK 125, 2BHK 210, 3BHK 310, 4BHK+ 420, office 1000.

### 4.2 Smoke made inside the home

While a source is running and you're at home:

```
added PM2.5 = emission (mg/min) × 60,000  ÷  (room volume × (a + k + c))
```

| Source | Emission (mg PM2.5 / min) |
| --- | --- |
| Cooking on gas (LPG) | 1.0 |
| Cooking electric / induction | 0.5 |
| Kerosene | 5.0 |
| Wood / dung / chulha | 15.0 |
| Incense | 0.5 |
| Mosquito coil | 2.0 |
| Smoking indoors | 1.7 |
| Candle | 0.1 |

**Example:** a mosquito coil in a 2BHK with normal windows: 2 × 60,000 ÷ (210 × 1.067) ≈ **536 µg/m³ extra** while it burns. With windows closed the removal rate drops to 0.8/h, so it's ≈ **714 µg/m³**: closing windows helps against outdoor smoke but traps indoor smoke (which is why the app never suggests closing windows when indoor smoke dominates).

### 4.3 Commute

```
commute factor = vehicle factor × road factor      (per route point)
```

| Vehicle | Share of outside air that reaches you | Body activity (for breathing) |
| --- | --- | --- |
| Walk | 1.0 | walk |
| Cycle | 1.0 | cycle |
| Bus / metro | 1.0 (open buses, busy platforms; includes walking to stops) | walk |
| Two-wheeler | 1.0 | light (seated) |
| Car | 0.6 (windows up, fan on fresh air) | light |

| Road type at the route point | Roadside PM2.5 vs area average |
| --- | --- |
| Motorway, trunk | × 1.3 |
| Primary | × 1.2 |
| Secondary | × 1.1 |
| Tertiary | × 1.05 |
| Residential, path, unknown | × 1.0 |

Road types come from OpenRouteService's route (OpenStreetMap road classes).

### 4.4 Masks

Share of PM2.5 still inhaled through a mask as people actually wear it: none 1.0, cloth 0.8, surgical 0.7, **N95 0.3**. Applied to everything breathed during that segment (masks are only modelled on the commute).

---

## 5. How much air you breathe

`engine/dose.py: breathing_rate`, in m³/h. Three ways, best available first:

**a) Measured effort** (heart rate or steps from a log, later the phone/watch): personal formula with that MET.

**b) Weight known:** the US EPA Exposure Factors Handbook method:

```
breathing (m³/h) = BMR (kcal/day) ÷ 24 × MET × 0.209 L O₂ per kcal × 27 L air per L O₂ ÷ 1000
```

- **BMR** from the WHO/FAO/UNU equations: `slope × weight + intercept`, by sex and age band (e.g. man 30-59: 11.6 × kg + 879; woman 18-29: 14.7 × kg + 496). "Other" averages the man and woman values.
- **MET** (how many times resting energy) by activity: asleep 0.95, light 2.0, walk 3.5, cycling 6.8, running 8.0.

Example: 35-year-old man, 70 kg, sitting: BMR = 11.6 × 70 + 879 = 1691 kcal/day → 1691 ÷ 24 × 2.0 × 0.209 × 27 ÷ 1000 = **0.79 m³/h** (13.2 L/min).

**c) Otherwise, the table** (m³/h):

| Activity | Man | Woman | Child (3-11) |
| --- | --- | --- | --- |
| Asleep | 0.45 | 0.38 | 0.35 |
| Light (sitting, home, office, car, two-wheeler) | 0.80 | 0.70 | 0.60 |
| Walking (also bus/metro) | 1.40 | 1.20 | 1.00 |
| Cycling | 2.40 | 2.00 | 1.60 |
| Running | 3.00 | 2.60 | 2.00 |

### 5.1 Effort from heart rate

```
HRmax  = 208 − 0.7 × age                         (Tanaka)
METmax = 15.3 × HRmax ÷ HRrest ÷ 3.5             (Uth; 1 MET = 3.5 ml O₂/kg/min)
share  = (HR − HRrest) ÷ (HRmax − HRrest)        clamped 0…1
MET    = 1 + share × (METmax − 1)
```

HRrest defaults to 70. Example: age 30, 160 bpm → HRmax 187, share 0.77, METmax 11.7 → **MET ≈ 9.2** (a run).

### 5.2 Effort from steps per minute

Straight lines between: 0 → 1.3, 60 → 2.0, **100 → 3.0**, **130 → 5.0**, 160 → 8.0, 180 → 10.0 MET (CADENCE-Adults). Example: 115 steps/min → 4.0 MET.

When only effort is known, it's labelled walk (≥ 2.5 MET, with steps) or run (≥ 6.0). If no weight was given, a typical weight is used: adults man 65 / woman 55 / other 60 kg; children 2 × age + 8 (up to 5), then 3 × age + 7 (capped at the adult value).

---

## 6. Dose and Lung Load

For every segment (`engine/score.py: compute`):

```
dose (µg)  = breathed PM2.5 × breathing rate × hours
reference  = 15 µg/m³ × breathing rate × hours        (same day, WHO-guideline air, no walls, no mask)

Lung Load  = 100 × Σ dose ÷ Σ reference × M
```

- **15 µg/m³** is the WHO 2021 24-hour guideline.
- **M (sensitivity):** 1.0 for adults; 1.3 if 65+; 1.5 for children (≤ 11) or a declared lung condition (highest one applies). A display weighting, not a medical risk score.
- **100 = a day breathing WHO-limit air.** 665 = 6.7× that.

Because the reference uses your own breathing, exercise in **clean** air barely moves Lung Load (both sides grow), while exercise in **dirty** air raises it (more of your breathing happens in bad, unfiltered air). The µg dose and the litres breathed always grow with exercise.

**Bands:** Low (green) ≤ 100 · Elevated (amber) ≤ 400 (≈ India's 60 µg/m³ 24 h standard) · High (red) > 400.

### Worked example (test account, 5 Oct 2026)

| Step | Number |
| --- | --- |
| Air breathed over the day | 12,146 L (12.1 m³) |
| PM2.5 that came with it | 1,211 µg (56 % from indoor smoke at home) |
| Same breathing at 15 µg/m³ | 12.1 × 15 = 182 µg |
| Ratio | 1,211 ÷ 182 = 6.65 |
| Lung Load | 6.65 × 100 × 1.0 = **665** (High) |

The "How is 665 worked out?" card on Today shows exactly these steps with your numbers (API fields `dose_ug`, `ref_ug`, `air_litres`, `sensitivity`, `times_who`).

---

## 7. Every number on the screens

### Today

| On screen | Formula / meaning |
| --- | --- |
| **Outside your home now: AQI 118 · Moderate, PM2.5 66** | Open-Meteo's current PM2.5 at your home (~5 km square), converted with the AQI formula (§8) on the scale chosen in Settings |
| **Lung Load 665** | §6 |
| **6.7× the WHO limit** | Lung Load ÷ 100 |
| **High** badge, ring colour | band from §6 |
| **Likely between 409 and 1134 · 91 % chance it's high** | 200 Monte Carlo runs (§9): the 10th-90th percentile, and the share of runs that land in the shown band |
| **Breathing 8.4 L/min** | air breathed ÷ minutes covered (12,146 L ÷ 1,440 min) |
| **Your air 127 µg/m³ avg** | time-weighted average of the PM2.5 you were breathing (after walls, car, mask, plus indoor smoke) across the day |
| **Like 5.8 cigarettes** | your-air average ÷ 22 (Berkeley Earth rule of thumb: 22 µg/m³ for 24 h ≈ one cigarette). A comparison aid, not a health claim |
| **What you were doing: Asleep 49 %, Resting 51 %** | share of the day's dose while in each activity |
| **About 12,146 litres of air** | Σ breathing rate × hours |
| **Where it came from: Home / Commute / Work %** | share of the day's dose in each place |
| **56 % came from smoke or fumes inside your home** | indoor-source part of the dose ÷ total dose (shown when ≥ 5 %) |
| **What would help most: −56 %, −10 %, −8 %** | each tip is the whole day re-simulated with that change: `(dose before − dose after) ÷ dose before` (§10) |

### Tomorrow

| On screen | Formula / meaning |
| --- | --- |
| **Forecast Lung Load 588** | §6 on tomorrow's forecast air and your schedule for that weekday |
| **Outdoor air, hour by hour** bars | outdoor PM2.5 at home for each local hour (time-weighted across UTC hours) |
| **Best to be outside** | the 3 cleanest hours between 6 am and 9 pm |
| **Worst** | the 3 most polluted hours |
| **Smoke risk** | upwind fire count in the last 48 h: ≥ 1 low, ≥ 25 medium, ≥ 100 high (fire data arrives with layer 7; it's a flag only and never changes the number) |

Forecast refinement (**nowcast**, when stations are connected): today's model error `observed ÷ model` is carried forward and fades: `forecast × ratio^(e^(−hours ahead ÷ 6))`, capped at ×¼…×4.

### Trends

| On screen | Formula |
| --- | --- |
| **This week 582 average Lung Load** | mean of the stored daily Lung Loads in the last 7 days |
| **↓ 12 % lighter than last week** | `(this week − last week) ÷ last week` (shown once there are two weeks) |
| Bars | one per day, coloured by band; dashed line at 100 = WHO-limit air |
| **Easiest / Heaviest day** | lowest / highest daily Lung Load in the period |
| **Average breathing** | mean of the daily L/min |
| **Dose while walking, running or cycling** | mean over the days of (walk + run + cycle share of the dose) |
| **Days by level** | how many days were Low / Elevated / High |

### Map

| On screen | Formula / meaning |
| --- | --- |
| Coloured haze | current PM2.5 at points of a fixed world grid: 0.1° apart in a city, coarser when zoomed out (0.25° … 30°), at most ~11 × 11 points; each drawn as a soft circle coloured by the AQI scale's colours |
| **Legend** | the chosen AQI scale's bands (e.g. India: 0 Good, 51 Satisfactory, 101 Moderate, 201 Poor, 301 Very poor, 401 Severe) |
| **Place card: AQI now** | that place's current PM2.5 → AQI (§8) |
| **Next days bars** | each local day's average PM2.5 → AQI |
| **Cleanest hours today** | the 3 cleanest hours between 7 am and 9 pm, in that place's own time zone |
| **Commute line colour** | each route segment coloured by roadside PM2.5 at your departure hour (cell PM2.5 × road factor) |
| **Your commute: beside the road AQI …** | average roadside PM2.5 along the route at that departure hour |
| **Per hour of travel: Car 48 µg/h …** | `roadside PM2.5 × vehicle factor × mask × breathing rate for that vehicle's activity` (per hour, because trip times differ by vehicle) |

Example (test account, 22 km, roadside ≈ 130 µg/m³, no mask; this profile's breathing from §5 is ≈ 0.62 m³/h sitting, 1.07 walking, 2.08 cycling):

| Vehicle | Calculation | µg per hour |
| --- | --- | --- |
| Car | 130 × 0.6 × 0.62 | ≈ 48 |
| Two-wheeler | 130 × 1.0 × 0.62 | ≈ 80 |
| Walk, bus/metro | 130 × 1.0 × 1.07 | ≈ 139 |
| Cycle | 130 × 1.0 × 2.08 | ≈ 270 |

### What if

Same as tips: the day re-simulated with your chosen changes (commute ±1-3 h, purifier at home or work, closed windows, N95 on the commute, cutting a source). Shows Lung Load before → after and the % saved. On a day off, commute changes are tried as if it were a workday (and the screen says so).

---

## 8. AQI from PM2.5

`apps/mobile/src/lib/aqi.ts`. Both official scales are linear inside each band:

```
AQI = (I_hi − I_lo) ÷ (C_hi − C_lo) × (C − C_lo) + I_lo
```

C is PM2.5 (India: truncated to whole µg/m³; US: to 0.1).

**India National AQI (CPCB), PM2.5:**

| PM2.5 µg/m³ | AQI | Category |
| --- | --- | --- |
| 0-30 | 0-50 | Good |
| 31-60 | 51-100 | Satisfactory |
| 61-90 | 101-200 | Moderate |
| 91-120 | 201-300 | Poor |
| 121-250 | 301-400 | Very poor |
| 251-380 | 401-500 | Severe |

**US EPA AQI (2024 PM2.5 breakpoints):**

| PM2.5 µg/m³ | AQI | Category |
| --- | --- | --- |
| 0-9.0 | 0-50 | Good |
| 9.1-35.4 | 51-100 | Moderate |
| 35.5-55.4 | 101-150 | Unhealthy for sensitive groups |
| 55.5-125.4 | 151-200 | Unhealthy |
| 125.5-225.4 | 201-300 | Very unhealthy |
| 225.5-325.4 | 301-500 | Hazardous |

Examples: 67 µg/m³ → **India 121** (Moderate) / **US 159** (Unhealthy). 45 µg/m³ → **US 124**.

Notes: official AQI uses 24-hour averages and the worst of several pollutants; the app uses PM2.5 only and applies the formula to the current hour too, like most apps. So "AQI now" is indicative.

---

## 9. The "likely between" range

`engine/uncertainty.py`. The day is recomputed **200 times**, each time multiplying the uncertain inputs by a random log-normal factor (median 1). Inputs you told us use the tighter spread, so every detail you add narrows the range.

| Input | Spread (σ of ln) |
| --- | --- |
| Air model, no station nearby / station-corrected | 0.45 / 0.20 |
| Breathing table / personal (weight known) | 0.25 / 0.15 |
| Penetration · deposition · air exchange | 0.10 · 0.30 · 0.40 |
| Home size unknown / known | 0.35 / 0.10 |
| Purifier CADR unknown / known | 0.40 / 0.15 |
| Indoor source emission | 0.60 |
| Mask · road factor | 0.30 · 0.10 |

One air draw per run for all cells (model errors move together). Range = 10th and 90th percentile of the 200 Lung Loads; band chance = share of runs in each band. The random seed comes from your user id and the date, so the range is stable for the day.

---

## 10. Tips and what-ifs

`engine/tips.py`. Candidates: run a purifier at home / at work, close windows (not when indoor smoke dominates), N95 on the commute, leave 1 or 2 hours earlier or later (both ways), and each indoor source's own fix (e.g. coil → net or plug-in repellent = emission × 0; exhaust while cooking = × 0.5).

For each, the whole day is re-simulated: `saves % = (dose − dose with change) ÷ dose × 100`.

Rules: keep at most **3**, each saving at least **3 %**; offer only one commute shift (the best, preferring the smallest change among near-ties); include a free tip if one also clears 3 %.

---

## 11. Limits worth knowing

- **Model resolution:** Open-Meteo's global model is about 10-40 km per square: right for city-level and route-level differences, not for one street vs the next. Ground stations (OpenAQ, layer 7) will sharpen it where they exist.
- **Population averages:** breathing rates, indoor factors, emissions and masks are averages from published studies (see [engine-parameters.md](engine-parameters.md) for each source and which still need checking against primary sources). Your real day varies.
- **Estimates, not measurements, and not medical advice.** Lung Load ranks days and shows what would help; it says nothing about the health of anyone's lungs.
- The cigarette comparison and the sensitivity multiplier are communication aids, not clinical numbers.
