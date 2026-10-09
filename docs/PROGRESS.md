# Progress

The build log for the Lung Exposure Tracker backend and app. This file is updated every time a layer is finished.

**Last updated:** 2026-10-05
**Current focus:** M4 + L4 phone check, then L5 (Health Connect), then Layer LL (Lung Load: personal breathing from age, sex and measured activity) — L1 engine, L2 API and L3 app screens (with the new "glass and air" look) done; L4 Activity Recognition next. Then 5d (native: APK build, geofencing, FCM push, Google sign-in). AWS deploy (runbook in [deployment.md](deployment.md)) whenever you're ready

## Status at a glance

| # | Layer | Status | Verified by |
| --- | --- | --- | --- |
| 1 | Foundation: monorepo, uv, Docker, local stack | ✅ Done | `make check`; containers healthy; API image serves `/health` |
| 2 | Scoring engine | ✅ Done | Worked example + formula tests |
| 2b | Engine accuracy refinements (7 of 8; sensor deferred) | ✅ Done | 74 engine tests in total; defaults still reproduce the worked example |
| 3 | Data: schema, repositories, Open-Meteo + OpenRouteService, services, SQS worker | ✅ Done | 99 unit + 20 integration tests; live run against Open-Meteo |
| 4 | Auth + API: email/password, Google, JWT, Brevo, FCM, rate limits, `/v1` endpoints | ✅ Done | 119 unit + 51 integration tests; live run through the API container |
| LL | Lung Load: activity-aware breathing (running, walking, heart rate, steps), trends | 🟡 L1-L3 done; L4 next | 136 unit + 55 integration API tests; 35 Jest tests; screens checked in the browser |
| MAP | World air map: pollution layer, search, any place, commute route; trips + opt-in route recording next | 🟡 M1-M4 built; M4 phone check pending | 140 unit + 68 integration API tests; M1-M2 and trip planning checked on the phone |
| 5 | Mobile: Expo / React Native app | 🟡 5a-5c done, 5d after Lung Load | 20 Jest tests, lint, strict types; full flow run in the browser against the API |
| 6 | Infra + CI/CD: OpenTofu, Caddy, production compose, GHCR, SSM deploy, backups, alarms | ✅ Done (local) | tofu validate + 6 security tests, shellcheck, actionlint, production stack run locally: load balancing 20/20, 0/272 failures while redeploying |
| 7 | FIRMS fires (live), OpenAQ stations, monitoring | ✅ done | 165 unit + 81 integration + 3 tofu monitoring tests; live FIRMS, OpenAQ, push and `/status` |

Backend first, UI after (decided 2026-10-03).

---

## Layer 1: Foundation ✅

**Goal:** one command brings up everything the backend needs on a laptop, and the API image builds and runs.

### Built

| Item | Where | Notes |
| --- | --- | --- |
| Monorepo skeleton | repo root | Layout in [architecture.md](architecture.md#repository-layout) |
| Python project (uv, Python 3.12) | `apps/api/pyproject.toml`, `uv.lock` | Ruff, strict mypy and pytest are configured in the same file |
| Settings from environment variables | `apps/api/src/lung/settings.py` | Read once, cached; `.env` locally |
| Structured logging | `apps/api/src/lung/infra/logging.py` | JSON in production (for CloudWatch), readable lines locally |
| App factory + `/health` | `apps/api/src/lung/main.py`, `api/health.py` | `/docs` and the OpenAPI schema are switched off in production |
| Alembic (async) | `apps/api/alembic.ini`, `migrations/env.py` | Hand-written SQL migrations; URL comes from `DATABASE_URL` |
| API/worker image | `apps/api/Dockerfile` | Two-stage uv build, non-root `app` user, health check, 277 MB |
| Postgres 17 + PostGIS 3.6 image | `deploy/postgres/` | Built from the official image plus PostGIS from apt, because `postgis/postgis` has no ARM build and production runs on ARM (t4g) |
| Local SQS stand-in | `deploy/elasticmq/elasticmq.conf` | `ingest-jobs` and `user-jobs`, each with a DLQ (5 receives, 60 s visibility), matching production |
| Local stack | `docker-compose.yml` | postgres, valkey, elasticmq; `api` behind the `app` profile |
| Tasks | `Makefile` | `up down api migrate test test-int lint fmt typecheck check image` |
| Repo hygiene | `.gitignore`, `.gitattributes`, `.editorconfig` | Line endings are forced to LF so scripts work on Linux EC2; secrets are ignored |

### Verified

- `make check`: ruff, mypy (strict) and pytest all pass.
- `make up`: all three services are healthy. PostGIS 3.6.4 is loaded, Valkey answers `PONG`, and the 4 queues exist.
- `make migrate`: Alembic connects (no migrations yet).
- `docker compose --profile app up api`: the container is healthy, runs as `app`, all imports load, and `/health` returns `{"status":"ok"}` on port 18000.

### Issues hit and fixed

| Problem | Fix |
| --- | --- |
| `elasticmq-native:1.6.x` tag doesn't exist | Pinned to `1.7.1` |
| Host port 5432 was used by another project's container (`autostream-postgres`) | Moved to a host port set by a variable, `PG_HOST_PORT` |
| Host port 5433 was used by a Windows PostgreSQL 18 service (it answered with "password failed") | Default host port is now **55432** |
| Host port 8000 was used by `autostream-api` | API host port is **18000** (`API_HOST_PORT`, `API_PORT`) |
| `ghcr.io/astral-sh/uv:0.11-python3.12-bookworm-slim` tag doesn't exist | Use `python:3.12-slim-bookworm` and copy `/uv` from `ghcr.io/astral-sh/uv:0.11` |

---

## Layer 2: Scoring engine ✅

**Goal:** a pure, tested implementation of the dose, score, tips, simulator and forecast from the design docs.

### Built (`apps/api/src/lung/engine/`)

| File | What it does |
| --- | --- |
| `models.py` | Plain data types: Profile, Schedule, DayPlan, IndoorState, Segment, Result, Change |
| `config.yaml` | Every number the engine uses. Sources are in [engine-parameters.md](engine-parameters.md) |
| `config.py` | Typed `EngineConfig` and `parse_config()`. Reading the file is done in `infra/engine_config.py`, so the engine itself does no I/O |
| `day.py` | Schedule + local date → segments. Handles sleep after midnight, days off, validation, and `apply_change` for what-ifs |
| `dose.py` | Breathing rate; outdoor PM2.5 time-weighted across UTC hours; breathed concentration; dose |
| `indoor.py` | Window factor × purifier multiplier |
| `score.py` | Reference dose, sensitivity M (highest, not the product), band, `compute()` |
| `cigarettes.py` | 24 h average ÷ 22 |
| `tips.py` | `simulate()` and `tips()`: re-run with one change; top 3; always at least one free action; one commute shift (smallest among near-ties) |
| `forecast.py` | Tomorrow's result, plus the worst hours and the best outdoor hours |

### Verified

- **Worked example matches the design doc exactly:** dose 1,619.5 µg, reference 260.25 µg, score 622.3, red, split 53.1% home / 29.6% office / 17.3% commute, average 89.6 µg/m³, 4.07 cigarettes. A home purifier saves 26.5% and brings the score to about 457.
- 42 engine tests: formulas, bands, indoor factors, partial-hour weighting, missing readings, day building, tips and forecast.

### Bug caught by the tests

India is UTC+5:30, so local hours never line up with the UTC hours readings are stored under. The forecast was looking up keys like `01:30Z` and returning no hours. Every local hour is now time-weighted across the UTC hours it overlaps, and a regression test covers it.

### Decisions that differ from the design docs

| Topic | Design docs | Now | Why |
| --- | --- | --- | --- |
| Purifier | Replaces F with 0.25 | ~~Multiplies the window factor by 0.5~~ → superseded in layer 2b by the mass-balance model | Still 0.25 for normal windows, so the worked example is unchanged |
| Two-wheeler breathing | walk | light | The rider is seated |
| Car commute | F = 1 | Cabin factor 0.6 | Windows up; see the parameters doc |
| Masks | Not in config | n95 0.3, surgical 0.7, cloth 0.8 | Needed for tips and the simulator |
| Schedule | 4 trip times | + wake and sleep | Needed to split home time into asleep and awake |
| Schedule → segments | Service layer | Engine (`day.py`) | Tips and the simulator must rebuild the day, so it has to be pure |
| Engine imports | "stdlib only" | stdlib only; the YAML loader lives in `infra/` | Keeps the rule |

---

## Layer 2b: Engine accuracy refinements ✅

**Goal:** make the estimate more accurate and more personal without breaking the design-doc numbers. Every refinement is optional input. With none given, the engine gives exactly the old results; each detail a user adds narrows their uncertainty range. Details are in [engine-parameters.md](engine-parameters.md).

| # | Refinement | Where | What it does | Data arrives in |
| --- | --- | --- | --- | --- |
| 1 | Station correction | `engine/airdata.py` | Bends the gridded model towards nearby stations: log-ratio, 1/d² weights, shrinkage, clamp | Layer 7 (OpenAQ/CPCB) |
| 2 | Route-aware commute | `engine/day.py` | Commute split along route points, each with its own cell and a road-type factor; reversed on the way home | OpenRouteService integration (layer 3/4) |
| 3 | Physics-based indoor model | `engine/indoor.py` | Mass balance (penetration, air exchange, deposition, purifier CADR/volume) + indoor sources (cooking by fuel, incense, coil, smoking, candle) as time windows | Onboarding inputs (layer 4) |
| 4 | Geofence time-in-place | `engine/day.py` | Observed visits replace the schedule for past minutes; walking seen by the phone counts as outdoor air; errands use the home cell | Phone (layers 4-5) |
| 5 | Personal breathing rate | `engine/dose.py` | BMR (WHO/FAO/UNU) × MET × EPA EFH O2 and ventilation constants, from weight | Onboarding (layer 4) |
| 7 | Better forecast | `engine/forecast.py` | Nowcast (current model error fading over ~6 h) + fire risk flag (none/low/medium/high); PM2.5 uplift kept at 0 until calibrated | Layer 3 (latest readings), layer 7 (FIRMS) |
| 8 | Uncertainty range | `engine/uncertainty.py` | 200 seeded Monte Carlo runs; p10/p50/p90 score and band probabilities; known inputs use tighter spreads | Nothing extra |
| 6 | Low-cost sensor input | — | **Deferred** at the user's request | — |

### New optional user inputs (all optional, all extensible)

| Input | Used for | Sensitive? |
| --- | --- | --- |
| Body weight | Personal breathing rate | Yes: kept out of logs |
| Home size (1RK-4BHK+) | Indoor volume | No |
| Purifier CADR | Purifier strength | No |
| Indoor sources + times (cooking fuel and meal times, incense, mosquito coil, smoking, candles) | Indoor source PM2.5 | Smoking: yes, handled like the asthma flag |

New source kinds are added as **one line in `config.yaml`**; no code changes. That's the "add more options" mechanism: the app shows the list from config, and every option a user adds gives the engine another parameter.

### Verified

- `make check`: ruff, strict mypy, **75 tests** (74 engine + 1 health).
- The worked example is unchanged: 1,619.5 µg, score 622.3, red. Default indoor factors are exactly 0.4 / 0.5 / 0.7 / 0.25.
- Uncertainty: 200 runs in about 80 ms. Worked example: p50 ≈ 602, range ≈ 320-1,113, red ≈ 78%. Adding weight, home size and a station-corrected cell gives a measurably narrower range (tested).

### Behaviour changes from layer 2

| Change | Before | After | Why |
| --- | --- | --- | --- |
| Purifier + open windows | 0.35 | 0.525 | Physics: a purifier can't keep up with an open window |
| Purifier + closed windows | 0.2 | 0.171 | Same model |
| `indoor_factor` and `purifier_multiplier` config keys | present | replaced by the `indoor:` section | Mass-balance model |
| Segment | outdoor factor only | + `added_ugm3` (sources), + `observed` flag | Sources and geofence visits |
| Result | — | + `indoor_source_share` | "Cooking caused X% of today's dose" tips |

### Follow-ups this creates for later layers

- **Layer 3 database:** add `users.weight_kg`; `indoor_state.size`, `purifier_cadr_m3h`; new tables `indoor_sources` (place, kind, start, minutes), `route_points` (user, seq, cell_id, road_class) and `visits` (user, place, start, end, activity); and `engine_version` on `daily_scores`.
- **Layer 3/4 integrations:** OpenRouteService (route once per home/office change; fall back to a straight line). Needs a free ORS API key.
- **Layer 4 API:** expose the optional inputs and `GET` the source catalog from config; return `range` (p10/p90) and `band_probability` with every score.
- Tips don't yet use observed visits (they simulate the declared day). Revisit once visits are stored.

---

## Layer 3: Data pipeline ✅

**Goal:** real air data flows in on a schedule, and every user's scores for today and tomorrow are computed and stored without anyone calling the API.

### Built

| Area | Where | What it does |
| --- | --- | --- |
| Schema | `migrations/versions/0001_core_schema.py` | 14 tables (below), PostGIS points, monthly partitions for `air_readings` via an idempotent `ensure_air_partitions()` function. Upgrade and downgrade both tested |
| Grid cells | `domain/geo.py` | 0.1° cells (about 11 km, close to the air model's grid), haversine distance, even sampling along a line |
| DB / cache / queue adapters | `infra/db.py`, `cache.py`, `queue.py` | Async SQLAlchemy sessions (commit/rollback per unit of work); Valkey that **fails open**; SQS client (ElasticMQ locally) with batching and delays |
| Repositories | `repositories/*.py` | One file per table, hand-written SQL, plain records out |
| Open-Meteo | `integrations/open_meteo.py` | Hourly PM2.5/PM10 + wind for a point, in UTC; drops blank forecast hours; 429/5xx/timeouts → `Retryable` |
| OpenRouteService | `integrations/openrouteservice.py` | Route + road types (waytype/waycategory → road class), sampled every ~1 km (max 20 points). **Optional:** without `ORS_API_KEY`, a straight line is used |
| Services | `services/` | `ingest_service` (tick, fetch), `route_service`, `score_service` (recompute, cached reads), `alert_service`, `plan` (rows → engine inputs), `notifier` (logs until FCM in layer 4) |
| Worker | `worker/main.py`, `handlers.py`, `__main__.py` | Polls both queues, one handler per message, concurrency gate, deletes only on success, `Retryable` → retry, 5 failures → DLQ, graceful SIGTERM. `LOCAL_TICK_MINUTES` stands in for EventBridge locally |
| Dev tools | `devtools/seed.py`, `make seed`, `make worker` | Demo user: Connaught Place home, Noida office, LPG cooking + mosquito coil |
| Compose | `docker-compose.yml` | `worker` service (profile `app`) from the same image as the API |

### Tables

| Table | Owner | Notes |
| --- | --- | --- |
| `users` | user | Identity only; auth columns come in layer 4 |
| `profiles` | user | age, sex, sensitive, **weight_kg** (optional), timezone |
| `places` | user | home/office point + cell, plus indoor state: windows, purifier, **CADR**, **size** |
| `indoor_sources` | place | kind, start time, minutes |
| `schedules` | user | wake/trips/sleep, mode, mask, **office_days** (ISO weekdays); DB check keeps trips in order |
| `routes`, `route_points` | user | source (ORS or straight line), sampled points with cell and road class |
| `visits` | user | geofence visits (filled from the app in layers 4-5) |
| `daily_scores` | user | today and tomorrow: score + **p10/p90**, band, shares, **indoor source share**, fire risk, `details` JSON (tips, hours, band odds), `data_as_of`, **engine_version** |
| `device_tokens`, `alerts` | user | FCM tokens; one alert per user, type and day |
| `air_readings` | shared | Partitioned by month; key (cell, hour) |
| `fire_events` | shared | Ready for FIRMS (layer 7) |

### How the pipeline runs

```
EventBridge / local ticker --tick--> ingest-jobs
  tick:      ensure partitions -> one fetch per cell in use (places + route points)
  fetch:     skip if fetched < 50 min ago or another worker holds the 2-min lock
             -> Open-Meteo -> upsert air_readings -> queue ONE recompute per affected user (60 s delay)
user-jobs
  recompute: rows -> engine (today with visits, tomorrow forecast, tips, uncertainty)
             -> upsert daily_scores -> clear cache -> queue alerts (red tomorrow, high smoke)
             no air yet? -> force-fetch the missing cells and retry
  route:     ORS (or straight line) -> route_points -> fetch new cells -> recompute
  alert:     claim (user, type, day) once -> FCM tokens -> push -> drop dead tokens
```

### Verified

- `make check-all`: ruff, strict mypy (59 files), **99 unit + 20 integration tests**. Integration tests use a fresh `lung_test` database, real PostGIS and Valkey, and fake providers.
- **Live run against the real Open-Meteo API**, using the demo user (Sunday, so home all day):
  - 3 cells fetched once each, 72 hours each; Delhi PM2.5 ranged 42-157 µg/m³.
  - Today: score 1,125, red, range 631-2,239.
  - Tomorrow: commute 8%, office 9%.
  - 75% of the dose came from indoor sources, mostly the overnight coil.
  - Top tip: "Use a mosquito net or plug-in repellent instead of coils" (saves 69%).

### Problems found and fixed

| Problem | Fix |
| --- | --- |
| A user without a route needs the midpoint cell, but the tick only knew place and route cells, so the midpoint was never refreshed | **Every user always has a stored route**: a straight line straight away, upgraded by ORS when a key exists |
| The same cell was fetched up to 3 times when messages arrived together | A 2-minute per-cell lock (released on failure), on top of the 50-minute freshness check |
| `cell_id` with a 0.25° grid kept 1 decimal (`77.25` → `77.2`) | Decimals are counted from the resolution itself; `-0.0` is normalised to `0.0` |
| Indoor sources dominated, but the only tip was a purifier (closing windows makes indoor smoke worse) | **Source tips** in config: coil → net (removes the coil's emissions), smoking → outside, cooking → exhaust/open window (halves them), and so on |
| Queue test lost messages to a running worker | The test uses its own throwaway queue |
| A stale `worker/handlers/` folder shadowed `handlers.py` | Removed |

### Decisions

- **Hand-written SQL** in repositories; no ORM models. Migrations are SQL too (PostGIS and partitions).
- **Grid 0.1°**: about 11 km, matching the model's grid, so neighbours share fetches.
- **Fetch freshness 50 min** and a recompute delay of 60 s per tick, so one tick gives one recompute per user.
- **Alerts are claimed before sending**, so a redelivered message never double-pushes. If the push itself fails, that alert is lost for the day; we chose that over sending duplicates.

---

## Layer 4: Auth + API ✅

**Goal:** real users can sign up, onboard and use every feature over a secure, rate-limited HTTP API, with email and push ready to switch on with keys.

### Auth design

| Piece | Choice | Why |
| --- | --- | --- |
| Passwords | argon2id (argon2-cffi defaults); 8-128 chars, not the email (NIST SP 800-63B: length, no composition rules) | Memory-hard hashing; rehash on login if the parameters change |
| Unknown email on login | Verified against a dummy hash; same 401 body as a wrong password | Timing and responses don't reveal which emails exist |
| Access token | HS256 JWT, 15 min; checks signature, `iss`, `aud`, `typ`, expiry against the app clock; `alg: none` rejected | Short-lived, stateless |
| Refresh token | 256-bit random, **stored only as a SHA-256 hash**, 30 days, **single-use with rotation** | A leaked database can't be turned into sessions |
| Reuse detection | A used refresh token presented again revokes its whole sign-in family | Stops a stolen refresh token |
| Email codes | 6 digits, 15 min, **HMAC-keyed hash** (bound to user and purpose), 5 attempts then dead | 6 digits are easy to brute-force if stored as a plain hash |
| Google sign-in | The app sends Google's ID token; the API verifies the RS256 signature against Google's published keys, plus audience, issuer, expiry and `email_verified` | No Google SDK on the server |
| Account linking | Same email + Google → linked. If that email was never verified, its **password is dropped** | Blocks pre-registering a victim's email to take over their account later |
| Password reset / change | Revoke every session (change keeps the current device) | |
| Forgot password | Always 202 | No account enumeration |
| Rate limits | Valkey fixed windows: 10/min per IP on auth endpoints, 60/min per user, 5 failed logins per email per 15 min. **Fail open** if Valkey is down | Brute-force protection without making Valkey a single point of failure |
| Production guard | The API refuses to start with the dev JWT secret or a secret under 32 characters; Brevo is required in production | |

### Endpoints

| Method and path | Auth | Purpose |
| --- | --- | --- |
| `GET /health`, `GET /ready` | — | Liveness; readiness (database, cache, queue) |
| `GET /v1/catalog` | — | Every option for the app, from config (sources, sizes, modes, masks, mitigations, bands, disclaimer) |
| `POST /v1/auth/register` / `login` / `google` | IP-limited | Returns `{access_token, expires_at, refresh_token, user_id, is_new_user}` |
| `POST /v1/auth/refresh` / `logout` | IP-limited | Rotate; revoke the sign-in |
| `POST /v1/auth/logout-all` | user | Sign out everywhere |
| `GET /v1/auth/me` | user | Email, verified, has password, Google linked, onboarded |
| `POST /v1/auth/verify-email` (+ `/resend`) | user | 6-digit code |
| `POST /v1/auth/password/forgot` / `reset` / `change` | IP / user | Reset by code; change keeps this device signed in |
| `GET` / `PUT /v1/me/profile` | user | Whole onboarding profile: age, sex, sensitive, weight, timezone, home and office (with indoor details and sources), schedule with office days |
| `PUT /v1/me/indoor` | user | Partial update of windows, purifier, CADR, size, sources; score refreshes at once |
| `POST /v1/me/visits` | user | Geofence enter/exit batches (last 48 h, max 200) |
| `POST /v1/me/devices`, `DELETE /v1/me/devices/{token}` | user | FCM tokens |
| `DELETE /v1/me` | user | Delete the account and everything stored (cascades) |
| `GET /v1/me/score/today` / `forecast` | user | Score, range p10/p90, band odds, split, source share, tips or hourly forecast, fire risk, `data_as_of`, `engine_version`, `estimated: true`, disclaimer. 503 + `Retry-After` while the first air data loads |
| `POST /v1/me/score/simulate` | user | Commute shift ±3 h and mitigations (`purifier_home`, `n95_commute`, `source:<kind>`, …). On a day off, commute changes are tried as a workday (`as_workday: true`) |
| `GET /v1/air?lat&lon` | user | Hourly PM2.5/PM10/wind for the cell: 24 h back, 48 h ahead |

Every error has one shape: `{"error": {"code", "message", "details?"}}`, with stable codes such as `invalid_credentials`, `email_taken`, `weak_password`, `invalid_code`, `invalid_refresh_token`, `profile_incomplete`, `bad_schedule`, `unknown_source`, `not_ready` and `rate_limited`. Requests reject unknown fields. Responses carry `X-Request-ID`, `nosniff` and `no-store`. Access logs record method, path, status and time only: never bodies, tokens or query strings.

### Built

| Area | Where |
| --- | --- |
| Migration `0002_auth` | `users` + email (citext, unique), verified, password hash, Google subject, last login; `refresh_tokens`; `email_codes` |
| Auth primitives | `auth/passwords.py`, `auth/tokens.py` |
| Repositories | `accounts`, `refresh_tokens`, `email_codes` (+ `device_tokens.owner`) |
| Integrations | `google_auth.py` (JWKS verify), `brevo.py` (email), `fcm.py` (HTTP v1, service-account OAuth, dead-token detection) |
| Services | `auth_service`, `profile_service`, `air_service`, `mailer` (Brevo or log), score read/simulate/catalog in `score_service` |
| API | `api/errors.py` (one error shape), `api/deps.py` (context, current user, rate limits), `api/schemas/`, `api/v1/{auth,me,scores,meta}.py`, `main.py` (lifespan, request IDs, access log, security headers) |

### Verified

- `make check-all`: ruff, strict mypy (82 files), **119 unit + 51 integration tests**. New: 20 auth unit tests (JWT forgery and `alg: none`, wrong audience/issuer, expiry, argon2, code hashing, Google RS256 with real generated keys, FCM OAuth caching and dead tokens, Brevo request) and 31 API tests over HTTP.
- **Live through the Docker API container** with real Open-Meteo data: register → code in the API log → onboarding → today 303 amber (range 173-500) with 3 tips → forecast worst hours 03:00-05:00 → simulator: N95 + 1 h later saves 12% (tried as a workday on a Sunday), purifier + incense by a window saves 52%.

### Problems found and fixed

| Problem | Fix |
| --- | --- |
| Tokens and codes were checked against the real clock but issued with the app clock, so they "expired" in tests | Expiry is checked against the app's clock everywhere (JWT `exp`/`iat` and code expiry), so the whole app agrees on time |
| A failed code attempt raised inside the transaction, so the attempt counter rolled back | Errors are raised after the transaction commits |
| `fcm.py` imported from `services/` (an upward import) | `Push` moved to `domain/` |
| The simulator showed 0% for commute changes on a day off | Tried as a workday on today's air, flagged `as_workday` |
| `GOOGLE_CLIENT_IDS=a,b` couldn't be parsed (pydantic-settings expects JSON) | `NoDecode` + comma splitting |
| A blank `JWT_SECRET=` in `.env` would have meant an empty key | Blank means the dev secret locally; production rejects it |

---

## Layer 6: Infra + CI/CD ✅ (written and verified locally; not yet applied to AWS)

**Goal:** everything needed to run the backend on AWS for real users, reproducible from code, deployable by a push to `main`. The runbook is [deployment.md](deployment.md).

### Built

| Area | Where | What |
| --- | --- | --- |
| OpenTofu modules | `infra/modules/` | `network` (VPC, 2 public + 2 private subnets, **no NAT**, SG 80/443 only), `compute` (t4g.small AL2023 ARM, IMDSv2, encrypted root + **separate data disk** with `prevent_destroy`, Elastic IP, first-boot script: Docker, Compose, data disk, swap), `queue` (SQS ×2 + DLQs, SSE, EventBridge Scheduler hourly tick), `storage` (private versioned bucket: backups 30 d, releases 30 d, TLS-only), `iam` (instance role scoped to its own resources; GitHub **OIDC** deploy role limited to the repo's `demo` environment and instances tagged `lung-env`), `monitoring` (log group 14 d; alarms: DLQ, EC2 auto-recover, auto-reboot, CPU, CPU credits → SNS email), `edge` (ALB + ACM + Route 53, **off**), `rds` (Postgres 17, **off**), `stack` (wires it all + non-secret config into SSM) |
| Environments | `infra/bootstrap`, `infra/envs/demo`, `infra/envs/scale` | State bucket with native S3 locking; demo (deployed); scale (ALB + RDS on, written only) |
| Production stack | `deploy/compose.prod.yml` | Caddy → API ×2 (Docker DNS round-robin) · worker · migrate one-shot · Postgres (tuned for 2 GB) · Valkey (cache-only, LRU). Memory limits, awslogs to CloudWatch, worker heartbeat health check |
| Caddy | `deploy/caddy/Caddyfile` | Auto HTTPS (Let's Encrypt via DuckDNS), or `:80` behind the ALB; HSTS and security headers, `Server` hidden, 1 MB body limit, zstd/gzip, `/ready` and `/docs` blocked publicly, holds requests up to 15 s during deploys, serves `site/` |
| Server scripts | `deploy/scripts/` | `render-env.sh` (SSM → root-only `.env`), `deploy.sh` (pull → migrate → wait healthy → **auto-rollback**), `backup.sh` (pg_dump streamed to S3, size check), `restore.sh`, `duckdns.sh`, `put-secrets.sh` (run on your machine) |
| Timers | `deploy/systemd/` | Nightly backup 02:00 IST; DuckDNS every 5 min |
| CI/CD | `.github/workflows/ci-cd.yml` | PR/push: lint, types, unit + integration tests (PostGIS/Valkey/ElasticMQ services), tofu fmt/validate/**test**, shellcheck, Caddy validate, compose config. Main: ARM images → GHCR (tagged by commit) → deploy via SSM → HTTPS health check. Deploy is off until `DEPLOY_ENABLED=true` |
| Local production run | `deploy/compose.local-prod.yml`, `make prod-local` | The real production compose file on a laptop (only images, SQS, logging and TLS swapped) |
| Infra checks | `make infra-check` | Everything above that CI checks, through Docker; no local tools needed |
| Site | `site/index.html` | Placeholder download page (app link comes in layer 5) |
| Backend | `ingest_service.tick` | Purges expired refresh tokens hourly |
| Backend | `worker/main.py` | Heartbeat file on every poll, for the health check |

### Verified

- `tofu validate`: bootstrap, demo and scale all valid. `tofu test` with a mocked AWS provider, **6 security assertions pass**: only 80/443 open; IMDSv2 required; root and data disks encrypted; instance carries the deploy tag; ARM instance type; bucket private, encrypted, versioned, TLS-only; deploy role trusts only `owner/repo:environment:demo`; instance reads only `/lung/<env>/*`.
- shellcheck clean; actionlint clean; Caddyfile valid in DuckDNS, ALB and localhost modes; compose config valid.
- **Production compose running locally** (`make prod-local`): every service healthy (including the worker heartbeat), migrations ran, HTTPS through Caddy:
  - `/health` 200; `/ready`, `/docs`, `/openapi.json` 404; site 200; HTTP→HTTPS 308; 1.1 MB body → 413; HSTS and security headers present; gzip; HTTP/3 advertised.
  - **Load balancing 20/20** across the two API replicas.
  - Sign-up flow through Caddy works.
  - Memory in use about 420 MB of the 2 GB.
  - **Redeploying both API containers under load: 0 of 272 requests failed** (slowest waited 11 s).
- `make check-all`: 119 unit + 51 integration tests still pass.

### Problems found and fixed

| Problem | Fix |
| --- | --- |
| Deploy role ↔ instance ↔ instance profile formed a dependency cycle | SendCommand is scoped by the instance tag `lung-env`, not its ARN |
| `--wait` failed: the worker had no health check, and "process alive" would hide a stuck loop | Heartbeat file touched every poll; unhealthy if stale over 2 min |
| `/ready` and `/docs` were publicly reachable (Caddy ran the catch-all site handler before `respond`) | Blocked paths get their own `handle`, matched first. Caught by the local production test |
| `env_file: [${...}]` broke YAML (braces read as a mapping) | Quoted block list |
| Windows git doesn't keep the executable bit | Scripts are run with `bash <script>`; CI sets +x when building the bundle |
| Git Bash's curl returns "bad argument" (exit 43) for `-k -w` on HTTPS | Local checks use Python httpx; noted for local testing |

### Not done here (needs you, in AWS)

`tofu apply`, DuckDNS record, `put-secrets.sh`, GitHub environment and variables, GHCR package visibility, first deploy. All in [deployment.md](deployment.md).

---

## Layer 5: Mobile app (in progress: 5a-5c ✅, 5d next)

**Goal:** the Android app real users install: sign in, onboard in a couple of minutes, see today's estimate, tomorrow's forecast and what to change. Code: `apps/mobile/` ([README](../apps/mobile/README.md)).

### Stack

Expo **SDK 57**, React Native 0.86, React 19 (React Compiler on), TypeScript strict, Expo Router (typed routes), TanStack Query (server state), Zustand (onboarding draft), expo-secure-store (tokens), expo-location, react-native-svg. **Node 22.13+** is required by Expo 57: installed via **fnm** for this project only (`.node-version`); the global Node 20 is untouched.

Android package / iOS bundle id: **`com.lungexposure.tracker`** (Google sign-in and Firebase are tied to it).

### 5a: Foundation and sign-in ✅

- Design system (`src/theme`, `src/components/ui.tsx`): light/dark tokens, band colours **always with a text label** (Low / Elevated / High), 16 px gutters, 50 px touch targets, accessibility roles and labels.
- API client (`src/lib/api`): types mirror the API schemas exactly; adds the token; **one shared refresh** when several requests hit a 401 at once; rotates tokens; a failed refresh signs out; retries a read (never a write) once after a network error; turns the error format into a typed `ApiError` (code, message, field errors, `Retry-After`).
- Session: tokens in **SecureStore** (localStorage only in the web dev preview), restored at launch.
- Screens: sign in, create account (live validation), forgot password (code + new password).

### 5b: Onboarding ✅

Profile (age, sex, breathing condition, optional weight) → places → schedule (wake, four trip times, sleep; travel mode; work days) → optional home details (size, windows, purifier + CADR, indoor sources with time windows). One `PUT /v1/me/profile` at the end, then straight into the app.
- **Places:** "use my current location" (expo-location) or address search via **Photon** (open-source OpenStreetMap geocoder, no key). Results show the country whenever it isn't India.
- **Times:** a −/+ 15-minute stepper (no native picker dependency, works everywhere).
- **Indoor sources** come from `GET /v1/catalog`: a new kind added to the server's `config.yaml` appears in the app automatically, with a readable fallback name.
- Validation mirrors the API (age, weight, trip order) so errors show before submitting.

### 5c: Main app ✅

| Tab | Shows |
| --- | --- |
| Today | Score ring + band label, likely range and band odds, cigarettes, average PM2.5 breathed, home/commute/work split, indoor-smoke share, tips with savings, data timestamp, verify-email reminder, pull to refresh, disclaimer |
| Tomorrow | Forecast score + advice, smoke-risk banner, 24-hour PM2.5 chart, best and worst hours |
| What if | Leave-time shift and mitigation switches **tailored to the user** (no "run a purifier" if they already do; one switch per indoor source) → before/after with % saving; flags when a day off is shown as a workday |
| Settings | Account and email confirmation, profile/places/schedule editor, home and indoor-smoke editor, about the estimate, privacy note, sign out, delete account (with confirmation) |

Native tab bar on Android/iOS (Material / SF Symbols icons); a JavaScript tab bar on the web preview. "Air data still loading" (503) shows a friendly message and retries automatically after `Retry-After`.

### Verified

- `npm run check`: tsc strict, expo lint (incl. React Compiler rules), **20 Jest tests**: API client (shared refresh under 5 concurrent 401s, sign-out on a failed refresh, read-only retry, error parsing, 202/204), onboarding validation and request mapping, indoor editor.
- **End to end in the browser against the local API**:
  - sign-up, sign-in, sign-out;
  - full onboarding saved correctly (checked in Postgres: profile, both places with cells, schedule with Saturday, two-wheeler, 2BHK, closed windows, purifier CADR 250, sources), and the worker fetched the real OpenRouteService route (22 km);
  - Today 508 High with 82% from indoor smoke and the coil tip;
  - Tomorrow 644 High with best hours 10 am-12 pm;
  - What-if: leave 1 h later 627→620, plus cutting the coil → 202 Elevated (−68%);
  - Home & sources save (recomputed in 0.7 s);
  - email verification with a resent code.

### Problems found and fixed

| Problem | Fix |
| --- | --- |
| Search for "Connaught Place" also returned Hong Kong, with nothing on screen to tell them apart | Results name the country when it isn't India; the chosen card shows area, city and state instead of coordinates |
| Two quick taps on "+ source" kept only the second | The editor applies changes to the latest value (regression test added) |
| The app restarting mid-onboarding left the last step with an empty draft, failing at "Finish" | Each step sends the user back to the first step with missing answers |
| Finishing reset the draft before the server said "onboarded", bouncing back to step 1 for a moment | Refresh `/me` first, then clear the draft |
| A guarded route as the redirect anchor could make the router bounce | One unguarded `index` route decides; each area's layout gates itself (`AreaGate`) |
| Reading/writing a ref during render (flagged by React Compiler lint) | Removed; the splash is hidden from an effect |
| Native tabs froze the web preview | A web-only JavaScript tab bar (`_layout.web.tsx`); Android/iOS keep native tabs |
| Detail screens opened by link had nowhere to go "back" to after saving | `goBack()` falls back to Settings / Today |
| RNTL v14 renders asynchronously (React 19) | Tests `await render()` |

Testing note: browser screenshots and real clicks only work while the Chrome window is visible. A hidden window looked like a frozen app; the flows above were driven with real React events instead.

### 5d: Native features (in progress)

**Done in code (tested in Jest, device build pending):**

| Feature | Where | How |
| --- | --- | --- |
| Geofencing ("Use my real day") | `src/lib/geofence.ts`, `components/geofence-card.tsx` | Opt-in from Settings. Two 150 m circles (home, work) registered with Android's geofencing service; no GPS trail. Enter/exit → home / office / away visits (flickers under 2 min ignored, missed exits closed by the next enter, anything older than 47 h dropped), queued in AsyncStorage, uploaded to `POST /v1/me/visits` from the background task and whenever the app comes to the foreground. Asks "while using" then "all the time"; offers "Open settings" if refused |
| Push (FCM) | `src/lib/push.ts`, `app.config.js` | Registers the device's FCM token after sign-in (`POST /v1/me/devices`), "Air alerts" channel (Android 13 permission prompt), tapping an alert opens Tomorrow, sign-out unregisters the token. `google-services.json` is added to the build only if present, so push stays off until Firebase is set up |
| Permissions | `app.json` (expo-location plugin) | Background location on Android; plain-language permission texts |

**Build machine setup (Windows):** C: ran out of space during the first Android build (Gradle cache). With the user's OK: npm cache cleaned (~4 GB) and only that day's Gradle downloads removed (0.78 GB); older caches kept. This project's Android builds now keep everything on D: (`D:\dev-cache\`: Android SDK with platform 36, build-tools 36.0.0, NDK 27.1, CMake 3.22.1; Gradle home; npm cache; Java temp). See [local-development.md](local-development.md#android-device-builds).

**Status at end of 2026-10-05:** the first debug build succeeded (17 min, mostly first-time downloads) and is **installed on the test phone** (TECNO CK8n, Android 14). Not yet opened on the device (the phone was locked). Next session: start the stack, `adb reverse` the two ports, run Metro (`npx expo start`, no rebuild needed), then test every screen on the phone, including the native tab bar and geofencing.

### 5d: still to do (needs you)

| Feature | Needs |
| --- | --- |
| Android development/release build (APK) | Android SDK (installed) + a phone with USB debugging, or an emulator image |
| Geofencing → `POST /v1/me/visits` | expo-location background + expo-task-manager; tested on a device |
| Push (FCM) | A **Firebase project** with the Android app `com.lungexposure.tracker` → `google-services.json`, plus the service-account key for the server (`FCM_*`) |
| Google sign-in | OAuth clients in Google Cloud: Android (package + SHA-1 of the signing key) and Web; `GOOGLE_CLIENT_IDS` on the server |

---

## Layer LL: Lung Load (in progress)

Personalising the score with how hard the person is breathing. The score is presented as **Lung Load** (the pollution your lungs took in, compared with the same day in WHO-guideline air), not a "lung health" score: it measures exposure, not the state of anyone's lungs.

| Part | What | Status |
| --- | --- | --- |
| L1 | Engine: `run` activity, measured MET per interval (heart rate → MET, steps/min → MET), exercise near home/work counted as outdoors, typical weight when none given, `by_activity` dose shares, `air_m3` (air breathed) | ✅ |
| L2 | API: `activity_intervals` table (migration 0003), `POST /v1/me/activity`, recompute with intervals, `details.by_activity`, `GET /v1/me/score/history` with weekly insights | ✅ |
| L3 | App: "Lung Load" naming, log-activity screen, Trends tab, plus the "glass and air" redesign | ✅ (browser + phone) |
| L4 | Android Activity Recognition (walking / running / in vehicle) | ⬜ |
| L5 | Health Connect (heart rate, steps, workouts) | ✅ connected on the phone (permissions granted, sync runs; no data on the test phone yet) |

### L1 details

- New file `engine/activity.py` (`met_from_heart_rate`, `met_from_cadence`, `kind_from_met`); `ActivityInterval` in `models.py`; `Segment.met`; `build_day(..., activity=...)` and `estimate_range(..., activity=...)`.
- Parameters and sources: [engine-parameters.md](engine-parameters.md#measured-exertion-activity-lung-load).
- 15 new tests in `tests/unit/engine/test_activity.py`. Defaults with no activity reproduce every earlier result, including the worked example.
- Design note: in the same air everywhere, exercise doesn't change the score (it's a ratio against the same breathing in clean air) but raises the dose and the air breathed. In polluted air, exercising outside raises the score.

### L2 details

| Endpoint | What |
| --- | --- |
| `POST /v1/me/activity` | Up to 500 intervals: `start`, `end`, and `kind` (`asleep`/`light`/`walk`/`run`/`cycle`) **or** `heart_rate` / `steps_per_min` (the server turns them into a MET with `engine/activity.py`, using the profile's age, and picks the kind). Optional `met`, `outdoors`, `source` (`manual` / `activity_recognition` / `health_connect`). Within the last 48 h, at most 12 h each. Manual logs recompute today at once; phone batches go through the queue. Returns the new ids (201) |
| `GET /v1/me/activity?date=` | That local day's intervals (today by default) |
| `DELETE /v1/me/activity/{id}` | Removes one and recomputes |
| `GET /v1/me/score/history?days=14` | Stored days (1-90, today included) with score, band, dose, PM2.5, breathing rate and activity split, plus `insights`: this week's and last week's average and the change in %, days per band, best and worst day, share of the dose while exercising, average breathing rate |

`ScoreOut` (today / forecast) gained `by_activity`, `breathing_lpm` (average litres per minute) and `air_litres` (air breathed over the day). Scores stored before this change have none of these until they are recomputed.

- Migration `0003_activity.py`: `activity_intervals` (cascade-deleted with the user) and `run` allowed in `visits.activity`. Downgrade turns `run` visits into `walk`.
- New: `repositories/activity.py`, `services/activity_service.py`, `api/v1/activity.py`; `plan.load_activity`; `score_service.history` / `insights`.
- Tests: `tests/integration/test_api_activity.py` (4), `tests/unit/test_insights.py` (3).
- **Live run (dev API, test account):** 30-minute run logged → dose 1211 → 1320 µg, Lung Load 665 → 673, run = 9.4% of the day's dose, 9.1 L/min average; history returned 2 days with insights; deleting the run restored the dose exactly.

### L3 details: screens and the "glass and air" look

The look is based on the samples in `ui_SAMPLE/` (light, airy, big light headings, black pill buttons, soft grey fields with the label inside, frosted cards) but not copied. Decisions (2026-10-05): light only, animation "noticeable but calm", done together with L3.

- **Living air backdrop** (`components/air-backdrop.tsx`): behind every screen. Clean air = pale sky, mint/lilac light, breeze streaks gliding across, a few bright motes. Polluted = the sky greys over, dark smoke billows up from the bottom, soot rises. Strength follows PM2.5 (12 → clean, 180 → thickest) and fades smoothly when it changes. Today uses the PM2.5 you breathed, Tomorrow the outdoor forecast, Trends the period's average; sign-in/up and Log activity use the breeze; forms and settings use the still sky. One looping clock on the UI thread drives everything (Reanimated 4 + react-native-svg, no new native modules, so no rebuild); it stops when the screen is hidden and is static with the phone's reduced-motion setting.
- **Lung Load ring** (`components/score.tsx`): a halo that breathes at the person's own pace (litres per minute ÷ ~0.5 L per breath).
- **Today:** Lung Load ring, band, headline, three glass tiles (breathing L/min, PM2.5 breathed, cigarette comparison), "What you were doing" (activity split + Log activity), where it came from, alerts, tips.
- **Log activity** (`app/(app)/log-activity.tsx`): walk/run/cycle, outside/indoors, duration, when it finished; today's entries with Remove.
- **Trends tab** (5th tab): this week's average, change against last week, 14 bars against the WHO line, easiest/heaviest day, breathing and exercise share, days per band.
- **Tab bar:** a floating frosted-glass pill (`components/glass-tab-bar.tsx`, SVG icons in `tab-icons.tsx`) with a sliding highlight, inset from the screen edges; same on Android and web (replaced the native Material bar). True background blur needs `expo-blur` (native): add it with the next rebuild (L4).
- Building blocks restyled (`components/ui.tsx`, `controls.tsx`, `theme/index.ts`); Jest stubs the backdrop (`jest.setup.ts`) and transforms the ESM `standard-navigation` package.
- **Typefaces:** Fredoka (chunky, rounded, playful) for headings and big numbers, Inter for body text, labels and inputs (`@expo-google-fonts/fredoka`, `@expo-google-fonts/inter`, loaded before first render) so it looks the same whatever font the phone theme uses; text scaling is capped at 1.4× (hero numbers 1×–1.1×).
- **Checked on the phone (2026-10-05):** sign-in (breeze), Today (smog + soot at 127 µg/m³), Trends, Tomorrow. Found and fixed: text cut off when rendered before the font loaded; ring caption, stat tiles and the Log activity button overflowing with wider text. The debug app had been uninstalled again; reinstalled from the existing APK (no rebuild).

## Layer MAP: the air map (in progress)

Asked for 2026-10-05: a scrollable world map with the pollution around you, any place's air, trips out of town, and the commute route with vehicles as a factor. Decisions: map before L4/L5; recording the routes you actually travel is **opt-in, off by default**.

| Part | What | Status |
| --- | --- | --- |
| M1 | Map tab: MapLibre (native) with free OpenFreeMap tiles (no key), PM2.5 layer for the visible area anywhere in the world, your location, search any place (Photon), tap anywhere for now + 5 days + cleanest hours | ✅ |
| M2 | Commute on the map: route coloured by roadside PM2.5 at your morning / evening departure, Home and Work markers, "Your commute" card comparing car / two-wheeler / walk / bus-metro / cycle per hour on that route | ✅ |
| M3 | Trips out of town + "where are you today" switch (home / current location / any place) | ✅ (checked on the phone: Home → GPS "Jail Road" 310 → Home 643, instant) |
| M4 | Opt-in route recording + L4 activity detection: exposure along the real roads and vehicle | ✅ code + tests; native build done, phone check pending |

### M3: trips and the location switch

- **Trips** (`trips` table, migration 0004): `POST /v1/me/trips` (place + start/end dates, at most 60 days, up to a year ahead), `GET /v1/me/trips` (now and upcoming), `DELETE /v1/me/trips/{id}`.
- **On a trip day** the plan is a day off at the destination, indoors with normal windows and none of the home's smoke sources (`UserInputs.plan_for`). Scores carry `trip: {id, label}`; tomorrow's forecast and alerts follow the trip too.
- **Air for destinations:** trips on now or starting within 3 days join `cells_in_use`, so the worker keeps them fresh. Adding a trip fetches the destination's air on the spot and rescores at once (it used to wait for the worker's 60 s batching delay, which looked like "nothing happened").
- **Where are you today** (`GET/POST /v1/me/location`): `home`, or a place (one-day trip for today). Choosing home ends any trip covering today: one that started today is removed; one that started earlier now ends yesterday, so the days already away keep their scores.
- **App:** location chip top-right on Today (Home / Use my current location via GPS / search any place; a GPS fix within 1.5 km of home or work counts as the usual day, so being at home never drops the home's own smoke sources); "Plan a trip here" on map place cards (start: today, tomorrow, in 3 days, next week; length 1-7 days); "Your trips" on Tomorrow with each day's AQI at the destination; "Outside now" follows where you are.
- Issue hit: a test trip to Goa left on the test account made the app say "You're in Goa"; removed, and the account rescored.

### Route planner and editing home/work from the Map (2026-10-05)

- **Directions by the air** (`POST /v1/map/route`, `services/route_planner.py`): From (my location or any place) → To. OpenRouteService gives up to 3 driving alternatives (trips under 80 km), plus cycling (≤ 60 km) and walking (≤ 25 km). Each route is sampled every ~1 km (≤ 40 points); roadside PM2.5 = current PM2.5 on the map's 0.1° lattice (shared cache) × road-type factor. Fastest and cleanest drives are marked, with "% cleaner air". Per way of travelling, **whole-trip dose** = average roadside × share reaching you × breathing rate × trip time (bus = the drive × 1.3 for stops). Without an ORS key or route: straight lines at typical speeds (marked in the app).
- **Live:** Connaught Place → Noida Sec 62 in 2.4 s: 3 drives (22 / 23 / 23 min), the cleanest 4.7 % cleaner than the fastest; whole trip car ≈ 15 µg, two-wheeler 24, bus/metro 55, cycle 232, walk 370 (3 h 48 min).
- **App:** ⇄ button next to the map search; From/To panel with "My location" and search; selected route drawn in AQI colours, alternatives grey; bottom sheet with the drives and the whole-trip comparison; "Directions here" on any place card.
- **Home and work** can be changed straight from the Map ("Change home & work" next to "Your commute", and in the commute card): opens Profile, where each place has search and "Use my current location"; saving recomputes the commute route.
- Tests: `test_api_map.py` +3 (alternatives, cleanest vs fastest, mode doses, straight-line fallback, validation).

## 5d: Google sign-in and push (6 Oct 2026)

- **Firebase project `lung-score`:** `google-services.json` in `apps/mobile/` (git-ignored); Expo's prebuild adds the Google services Gradle plugin and copies the file, so Firebase's manual Gradle steps are not needed. Service-account key in `apps/api/` (git-ignored; `.gitignore` now also ignores `*firebase-adminsdk*.json` / `*service-account*.json`, after the key was first saved at the repo root where git would have picked it up) and in `.env` as `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON`. Checked live: Google issues an FCM token; a send to a fake device returns `INVALID_ARGUMENT` (authorised, API enabled).
- **Google sign-in:** OAuth consent screen (External, Testing; test users added), a **Web** client (the ID token's audience) and an **Android** client (package `com.lungexposure.tracker`, debug SHA-1 `5E:8F:16:06:2E:A3:CD:2C:4A:0D:54:78:76:BA:A6:F3:8C:AB:F6:25`). Server: `GOOGLE_CLIENT_IDS` = web, android. App: `@react-native-google-signin/google-signin` 16.1 (config plugin; `iosUrlScheme` set to the reversed web client ID because the plugin requires it), `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` in `.env.local`, real "Continue with Google" button (always shows the account picker; cancel is silent).
- **Checked on the phone:** Google's account picker opened for Lung Exposure Tracker; the user picked akashbisht2021@gmail.com; the server verified the token and linked it to the existing email account (same email, verified by Google).
- **Push checked on the phone (6 Oct 2026):** Bad-air alerts switched on, Android notification permission allowed, the app registered its FCM token (`device_tokens`), and a real test push sent through `FcmNotifier` arrived on the phone.
- **To publish for any Google account:** Google Auth Platform → Audience → Publish app (basic scopes only: no verification unless a logo is added). Release build and Play Store signing will each need their own SHA-1 added as another Android client.
- **Bug found while testing (00:15 IST):** "Getting the air data for your area" never finished. Open-Meteo counts forecast days from the UTC date; between 00:00 and 05:30 IST the UTC date is still yesterday, so 2 forecast days ended before the local tomorrow and every recompute failed with "no air data". Fix: `air_forecast_days` 2 → 3 (covers zones up to UTC+13); regression test `test_fetch_window.py` (fails with 2, passes with 3 for India after midnight, New Zealand and the Americas). All areas re-fetched and everyone rescored.

### Popular areas kept warm (6 Oct 2026)

- Areas people already use were refreshed hourly; a brand-new user still waited ~1 minute for the first fetch of their area. Now the hourly tick also fetches the areas in `apps/api/src/lung/warm_areas.yaml`: all of **Delhi NCR** (Delhi, Gurugram, Noida, Ghaziabad, Faridabad: 48 areas of ~11 km) plus the centres of Mumbai, Bengaluru, Kolkata, Chennai, Hyderabad, Pune, Ahmedabad, Lucknow, Jaipur and Chandigarh. 58 areas, about 2,800 Open-Meteo calls a day (free plan ~10,000).
- Add a city by adding a box or a point to the YAML and restarting the worker; no code change. `WARM_AREAS=false` switches it off.
- Code: `services/warm_service.py` (box/point → cells), `ingest_service.tick` (in-use ∪ warm). Tests: `tests/unit/test_warm_areas.py`, `test_tick_also_keeps_popular_areas_warm`.
- Checked live: first tick after the change queued 58 areas (3 in use), 55 new areas had fresh data within a minute; a Noida area had 96 hours stored with no user there.

## Commute footprint (CO₂), 8 Oct 2026

- **What:** a Trends card ("Commute footprint · estimate": kg CO₂ a week, range, one sentence) and a detail screen (every way of making the commute side by side with range bands, the best swap, recorded trips, how we estimate, sources). For example: "Two days a week by bus would save about 5 kg a week (about 240 kg a year)." Low-carbon commuters see what they avoid compared with driving alone.
- **Decisions (user):** Trends card + detail; India-specific factors with ranges; bus and metro split into two options.
- **Honesty rules:** every figure is a range and labelled an estimate; CO₂, never "air pollution saved"; a swap is "clear" only if it saves even at the pessimistic end, otherwise "might save … the estimates overlap"; never suggests a car or two-wheeler; walk ≤ 2 km, cycle ≤ 8 km one way.
- **Finding:** per km the metro (UNEP DTU 2014 / Sperling 2004: 20-61 g) is no better than a scooter (India GHG 2015: 32-46 g); the bus (15 g) is lowest. So the app suggests the bus, not the metro, to two-wheeler riders.
- **Bus/metro split:** migration `0006` (existing `bus_metro` → `bus`; switch to metro in the profile), engine config, route planner (metro uses the road route's time for now), trip recording, app labels. Exposure factors for metro are kept the same as bus (conservative) until we have a source.
- **API:** `GET /v1/me/footprint`. **Code:** `engine/footprint.py` + `footprint.yaml` (factors and sources), `services/footprint_service.py`; app `components/footprint-card.tsx`, `app/(app)/footprint.tsx`, `lib/footprint.ts`.
- **Also fixed:** `load_inputs` used the wall clock for "today" instead of the app clock, so trip tests broke once the real date ran more than 2 days past the tests' fixed day. No effect for users (the two clocks are the same in production).
- **Tests:** 8 unit (`test_footprint.py`), 2 integration, 7 Jest (`footprint.test.ts`, including "never calls CO₂ air pollution"). Totals: 173 unit + 83 integration + 68 Jest.
- **Checked on real data:** the user's account (bus, 21.2 km, 5 days) → 3.2 kg a week (2.4-6.4); no swap beats the bus; about 26 kg a week avoided compared with driving. **Tested on the phone (8 Oct):** the card and the detail screen show these numbers; the Map button and the source links work. The detail screen's map button wrapped its arrow onto a second line, so it now reads "Lung Load on the Map →".
- **Black screen on launch (fixed):** after the green splash the app showed about 3 s of black before the UI. The splash hides before the JS is ready, and the Android window behind it followed the phone's dark mode. `app.json` now sets `userInterfaceStyle: "light"` (the app is light-only) and `backgroundColor: "#F3F4F6"` (the app's background), so the gap is the app's own grey. The gap is long in debug builds because the JS comes from Metro; a release build has the JS inside the APK.
- Formulas, factors and sources: [how-the-numbers-work.md §12](how-the-numbers-work.md#12-commute-footprint-co).

## Layer 7: real-world data and monitoring (in progress)

| Part | What | Status |
| --- | --- | --- |
| 7a | NASA FIRMS fires → tomorrow's smoke-risk flag | ✅ live (key in `.env`) |
| 7b | Official ground stations (OpenAQ + CPCB) → correct the model air near them | ✅ OpenAQ live; CPCB key added, waiting for data.gov.in to come back up |
| 7c | Monitoring (metrics, dashboards, alerts) | ✅ built (goes live with the AWS deploy) |

### 7c: Monitoring (6 Oct 2026)

- **Metrics from the logs:** CloudWatch metric filters on the app's JSON logs (no agent, no SDK): API requests, 5xx and response time; air areas fetched; failed jobs; failed outside calls (OpenAQ, CPCB, geocoders, FCM, Brevo, route fallbacks); alerts sent.
- **3 new alarms → the same email:** `api-5xx`, `air-data-stale` (no fetch for 2 h; reliable now that the warm areas are fetched every hour), `jobs-failing`. Joins the existing DLQ, EC2 recover/reboot, CPU and CPU-credit alarms.
- **Dashboard** `lung-demo` with those, queue backlog, CPU and a warnings-by-event table.
- **Outside-in check:** public `GET /status` (API up and air data fresh, 503 if not) and a GitHub Action calling it every 15 min; a failure emails you. Needs the repo variable `STATUS_URL` after the deploy.
- All in the CloudWatch free tier (7/10 metrics, 9/10 alarms, 1/3 dashboards). Runbook in `docs/deployment.md` → Health signals.
- Checked: `tofu test` for the monitoring module (free-tier limits, stale-air alarm treats silence as breaching, filters match the log fields), `tofu validate` for both environments, Caddyfile valid, `/status` live locally: `{"status":"ok","air_age_min":27}`.

### 7a: FIRMS (2026-10-05)

- `integrations/firms.py` (area CSV API, VIIRS S-NPP near-real-time; confidence l/n/h or MODIS %), `repositories/fires.py`, `services/fire_service.py`; `fire_events` table (from 0001).
- **Refresh:** the worker's tick queues a `fires` job; it runs at most every 3 h, pulling the last day over everyone's places ± 5° (~500 km), and drops detections older than 7 days.
- **Upwind:** tomorrow's wind direction at home = speed-weighted vector mean of the hourly forecast (calm → no direction). Fires count when within 400 km, within ±45° of where the wind comes from, in the last 48 h, and not low confidence (`ST_Azimuth` / `ST_DWithin` in PostGIS). Count → none / low ≥ 1 / medium ≥ 25 / high ≥ 100 (`config.yaml`). Flag only; no PM2.5 uplift until calibrated.
- **Live (5 Oct 2026, 21:50 IST):** 115 detections over north India in 24 h (1.6 s), 83 north-west of Delhi; 99 stored. Tomorrow's Delhi wind mostly from 65° (ENE) → no fires upwind → "none" (correct). With a north-westerly the count would be 22 → "low".
- Tests: `test_firms.py` (CSV parsing, MODIS confidence, wind mean), `test_fires.py` (upwind vs downwind vs low-confidence through PostGIS → "medium"; off without a key).
- Key: `FIRMS_MAP_KEY` (free). Note for later: a single speed-weighted mean wind can hide a few north-westerly hours on variable days; an hour-by-hour count is a possible refinement.

### 7b: official ground stations (2026-10-05)

- **Decision (user):** official monitors only (no low-cost sensors), from OpenAQ and also CPCB directly (data.gov.in).
- **Why both:** a live check of OpenAQ found its Indian government feeds mostly stale: within 25 km, Delhi 79 official monitors / 0 reporting in 24 h (only 5 AirGradient low-cost sensors live), Mumbai 41 / 1, Bengaluru 14 / 0, Kolkata 16 / 0, London 159 / 22 by station time. Also OpenAQ's `datetimeLast` covers any sensor: the PM2.5 sensor itself can be weeks old (e.g. Marylebone Road: 10 Sep), so each PM2.5 reading's own time is checked.
- `integrations/stations.py` (`OpenAQClient`: locations within 25 km with a PM2.5 sensor, `isMonitor` and fixed, then `/latest`; `CpcbClient`: data.gov.in "Real time Air Quality Index", PM2.5 rows, IST timestamps, "NA" skipped), `services/station_service.py`.
- **Correction** on every cell fetch: official readings ≤ 3 h old within 30 km (OpenAQ cached 30 min per cell; CPCB one India-wide list cached 30 min) → the engine's `correct()` (1/d² weights, trust, ×¼…×4 cap) against the model at the reading's hour → applied to all hours as `ratio ^ exp(-|h - t| / 6 h)`, so the next hours follow the stations and the far forecast stays modelled. Stored with source `open_meteo+stations`; days with corrected home air use the tighter uncertainty (σ 0.20 instead of 0.45).
- **Live:** OpenAQ key valid (200; 401 without). Delhi: 0 live official stations. London: 1 (Tower Hamlets, 3.0 µg/m³) → model 4.0 corrected to 3.2 (×0.79, partial trust with one station). data.gov.in returned 502 / timeouts all evening, so CPCB couldn't be tried live; built to their documented format.
- Keys: `OPENAQ_API_KEY` (in `.env`), `CPCB_API_KEY` (free, data.gov.in; still to add). Tests: `test_stations.py` (pull + fade, far station ignored, cap, CPCB parsing).

### L5: Health Connect (2026-10-05)

- **Library:** `react-native-health-connect` 4.1 (Expo config plugin; permission delegate registered automatically). Android 14 has Health Connect built in; older phones get the "Open Health Connect" route. `expo-build-properties` raises minSdk to 26 (Health Connect's minimum).
- **Read-only permissions:** heart rate, resting heart rate, steps, exercise sessions (declared in `app.json`; the plugin adds the privacy-rationale intent filter and the Android 14 `ViewPermissionUsageActivity` alias).
- **Phone** (`lib/health.ts`): reads the last 47 h and turns it into activity intervals (`toActivities`, pure, 5 Jest tests):
  - workouts → run / walk / cycle (by ExerciseType) with the average heart rate during them; treadmill, gym machines, pool, yoga → indoors;
  - outside workouts, 5-minute buckets of brisk stepping (≥ 60 steps/min → cadence) or raised heart rate (≥ resting + 25 bpm), merged when back to back;
  - the latest resting heart rate is sent so effort from heart rate uses the person's own resting rate.
- **Server:** `resting_hr` on `POST /v1/me/activity`; a Health Connect batch replaces earlier Health Connect intervals in the same window, so re-syncing never double counts (integration test).
- **App:** Settings → "Health Connect" card (Connect / Sync now / Manage access); quiet sync whenever the app opens, at most every 15 minutes.
- Note: with Uth's estimate, a lower resting heart rate means a higher fitness ceiling, so the same heart rate is more absolute effort for a fitter person (and more air breathed).

### Faster place search and a route view that shows the route (2026-10-05)

- **Problem:** place search went straight from the phone to Photon's public server, which took 5-60 s; and the route results card covered almost the whole map, so routes were drawn but hidden.
- **Search** now goes through our API (`GET /v1/geo/search`, `GET /v1/geo/reverse`, `services/geo_service.py`, `integrations/geocoder.py`): Nominatim first (0.6-1.2 s live), Photon as the fallback, results cached in Valkey (searches 7 days, reverse 30 days; a repeat takes 0.01 s), and at most 1 Nominatim request per second for everyone (its usage policy). Results prefer places near the person (home or the route's start). The app searches after a 450 ms pause and cancels older searches. "My location" for routes uses GPS only (no name lookup), so routing starts at once. For real scale: self-host Photon or Nominatim.
- **Route view:** the trip collapses to one line ("My location → Gaur City"); routes are small swipeable cards (Fastest / Cleanest air, time, km, AQI); "Compare ways of travelling ▾" expands the whole-trip doses; the camera fits the chosen route between the bar and the cards. Loading shows a sweeping breeze bar, the step being worked on ("Finding roads…", "Checking the air along each route…", "Comparing ways to travel…") and ghost cards.
- Checked on the phone: My location → Gaur City, fastest 49 min / 41.5 km AQI 300 vs cleanest 51 min / 44.6 km AQI 293 (2 % cleaner); switching cards redraws the route.
- Tests: `test_api_geo.py` (cache, Photon fallback, short queries, reverse, auth).

### M4 + L4: recording real trips (opt-in)

- **Off by default.** Settings → "Record my trips". Android shows an ongoing notification while it records (required foreground service). "Delete my recorded trips" wipes everything at once.
- **Phone** (`lib/trip-recorder.ts`): background location updates (every ~40 m / 30 s, batched each minute, auto-paused when still). With each batch it takes one reading of Android's activity recognition (Google Play Services, via `expo-location`'s motion activity API: walking, running, cycling, in a vehicle, still). Points queue on the phone and upload in batches of 30+ to `POST /v1/me/tracks`.
- **Server** (`services/track_service.py`): each stretch between two points gets a way of travelling: the phone's reading if it is at least medium confidence, otherwise GPS speed (< 0.6 m/s still, < 2.5 walk, < 4.5 run, < 8.5 cycle if the person cycles to work else a vehicle, faster a vehicle; a vehicle is their declared bus/metro, two-wheeler or car, or bus/metro). Same way + same grid cell → one leg; gaps > 10 min split; legs < 2 min dropped; points with accuracy worse than 100 m ignored.
- **Privacy:** raw GPS points are never stored. A leg keeps times, way of travelling, grid cell, distance and a simplified line (≤ 30 points, rounded to ~100 m) so the person sees their day on the map. Legs are deleted after 7 days (worker tick) or on request.
- **Scoring:** recorded legs replace the declared day for their minutes (`build_day(travel=...)`), each with its own cell's air and the mode's factor and breathing (on foot or bike: outdoor air). Leg cells are fetched by the worker for 2 days.
- **L4 note:** Health Connect (L5) is still to come; activity recognition now comes from the phone itself.
- Endpoints: `POST /v1/me/tracks` (≤ 2000 points, last 48 h), `GET /v1/me/tracks?date=`, `DELETE /v1/me/tracks`. Migration 0005 (`travel_legs`).
- Tests: engine `test_travel.py` (5), `test_tracks.py` (4), `test_api_tracks.py` (2), app `trip-recorder.test.ts` (3).

### API

| Endpoint | What |
| --- | --- |
| `GET /v1/map/grid?south&west&north&east` | Current PM2.5 for the visible area as ≤ ~11×11 points on a fixed world lattice (0.1° in a city up to 30° for the whole world), so panning reuses cached points. One Open-Meteo call per 50 missing points; each point cached 30 min in Valkey |
| `GET /v1/map/place?lat&lon` | Any place: PM2.5 now, hourly for yesterday + 5 days, and per local day the average, peak and three cleanest daytime hours (in the place's own time zone). Cached 30 min per ~5 km square |
| `GET /v1/me/commute` | The stored route with roadside PM2.5 (area × road-type factor) at today's departure hours, both directions, and per mode: air let in × mask × breathing rate = µg per hour of travel |

New: `services/map_service.py`, `services/commute_service.py`, `api/v1/map.py`, `OpenMeteoClient.current_many` / `place_forecast`, `routes.meta`. Tests: `tests/unit/test_map_grid.py`, `tests/integration/test_api_map.py`, `test_api_commute.py`.

**Live (2026-10-05):** Delhi 49 points 67-107 µg/m³ (1.2 s, then 31 ms cached); North India at 2°; whole world at 30°; Goa / Shimla / London 5-day forecasts. On the phone: Delhi as an orange "poor" haze, the 22 km two-wheeler commute drawn Home → Work at ~130 µg/m³ roadside (car 48, two-wheeler 80, walk and bus/metro 139, cycle 270 µg per hour), a dropped pin with its 5 days, search → Shimla in green ("fair").

### App

- `app/(app)/(tabs)/map.tsx`, `components/place-sheet.tsx`, `components/commute-sheet.tsx`, `lib/air-colors.ts` (PM2.5 scale: 15 / 35 / 55 / 150 / 250).
- Map took the "What if" tab slot (six tabs don't fit the pill); What if is now a screen opened from Today ("Try what-ifs") and from the commute card.
- OpenStreetMap / OpenFreeMap attribution stays visible (the ⓘ button), as their licences require.
- Accuracy note shown to users via the card wording: Open-Meteo's global model is ~10-40 km per square, so city-level, not street-level. OpenAQ stations (layer 7) can sharpen it.

### Build notes

- MapLibre needed one native rebuild (12 min; `libmaplibre.so` is in the APK). `expo-blur` was tried for the tab bar and removed: on Android it can't blur the GPU-drawn map and would re-blur the animated smoke every frame.
- Metro hung after the dependency installs and the native prebuild; restart it with `--clear` after native changes.
- The local `worker` container runs a built image: after backend changes run `docker compose up -d --build worker`, or it keeps scoring with old code (seen: breathing missing on Today).

### AQI and "what is 665?" (2026-10-05)

The user compared Lung Load 665 with "live AQI 124" online. They measure different things, so the app now says so:

- **AQI shown wherever outdoor air appears** (Today "Outside your home now", map colours and legend, place cards, commute card), on the scale chosen in Settings: **India NAQI (CPCB, default) or US EPA AQI** (`lib/aqi.ts`, official PM2.5 breakpoints, 18 unit tests). Check: 45 µg/m³ = US AQI 124 (what the user saw); Delhi's 67 µg/m³ = India AQI 121.
- **Lung Load ring:** "665 · 6.7× the WHO limit".
- **"How is 665 worked out?"** card on Today with the person's own numbers: litres breathed → µg of PM2.5 (and the indoor-smoke share) → the same breathing at 15 µg/m³ → the ratio (× sensitivity if any). The API now returns `ref_ug`, `sensitivity`, `times_who`; an integration test checks the sum reproduces the score.
- **Tip fix:** the "always include a free tip" rule could add a free tip that saved ~0 % (shown as "−0%"); a free tip now also has to clear `tips.min_saving_pct` (3 %).
- "Try what-ifs" is a full black button; the alerts card stacks its buttons so the label never wraps.

## Real-key status

Keys live only in `apps/api/.env` (git-ignored). `make smoke` checks them without printing them.

| Provider | Status (2026-10-04) | Result |
| --- | --- | --- |
| Open-Meteo | ✅ Live | 72 hours for Delhi, PM2.5 45-132 µg/m³, wind on every hour |
| OpenRouteService | ✅ Key works | Connaught Place → Noida Sec 62: 21.2 km by road, 20 samples, real road types (motorway 9, primary 3, secondary 8) |
| Brevo | ✅ Live end to end | Registered through the API → verification email delivered → code verified (`email_verified: true`) |
| Full flow with real keys | ✅ 2026-10-04 | Onboarding → ORS route (21.2 km, 20 samples) → live air → today 337 amber (range 199-552, indoor sources 18%, 3 tips) → tomorrow 440 red (commute 26%), best hours outdoors 10:00-12:00 |
| `JWT_SECRET` | ✅ Random 64-character value generated into `.env` | |
| OpenAQ | ✅ Key valid (2026-10-05) | London corrected from a live official monitor; Indian government feeds on OpenAQ currently stale |
| CPCB (data.gov.in) | 🟡 Key added 5 Oct (passes their key check: a fake key gets 403); data.gov.in itself down (502 on every dataset), so not yet seen live | |
| NASA FIRMS | ✅ Live (2026-10-05) | 115 detections over north India in 24 h, fetched in 1.6 s |
| Google sign-in | ✅ Live on the phone (6 Oct) | Account picker → token verified → linked to the existing account |
| FCM | ✅ Live (6 Oct) | A real test push arrived on the phone | Release builds need their own Firebase app fingerprint |

**Security note:** the Brevo key was shared in a chat on 2026-10-04. Regenerate it in Brevo before production and put only the new key in `.env` / SSM.

## Open items

- [ ] Check the breathing table, EFH constants and BMR equations against the primary sources ([engine-parameters.md](engine-parameters.md#validation-still-to-do)).
- [ ] Cite primary studies for the car-cabin, road, deposition and indoor-source values.
- [ ] Calibrate the uncertainty σ values, nowcast τ and fire thresholds with a personal-monitor validation study.
- [ ] **Keys you'll add at the end** (everything works without them; all are in `.env.example`): `JWT_SECRET` (production: 32+ random characters), `GOOGLE_CLIENT_IDS` (Android/iOS/web OAuth clients), `BREVO_API_KEY` + `MAIL_FROM` (a sender verified in Brevo), `FCM_PROJECT_ID` + `FCM_SERVICE_ACCOUNT_JSON`, `ORS_API_KEY`; in layer 7 FIRMS and OpenAQ.
- [ ] An alert is claimed before the push is sent: if FCM fails, that day's alert is lost (chosen over duplicates).
- [ ] **Open-Meteo licence:** the free API is for **non-commercial** use (and has daily limits). Fine for development and a free public beta; a commercial launch needs their paid API plan or a self-hosted Open-Meteo. Check the current terms before launch. Check OpenRouteService's free-plan terms too.
- [ ] Tips don't use observed visits yet (they simulate the declared day).
- [ ] Source tip `scale` values (exhaust 0.5, etc.) are design choices; verify against kitchen-hood capture studies.
- [ ] Starlette warns that it prefers `httpx2` for its test client. This is harmless; revisit when upgrading.
- [ ] First git commit and push to GitHub (by the user), then the AWS setup in [deployment.md](deployment.md).
- [ ] Deploys pause requests for up to ~15 s (both API replicas restart together). True zero-downtime needs the ALB + 2 instances (`envs/scale`) or a blue/green step.
- [ ] Decide whether to move the original design PDF and `.md` into `docs/design/`.
- [ ] Commute footprint: find a source for metro in-cabin PM2.5 (metro uses the bus exposure factor now) and for metro trip time (uses the road route's time); refresh the metro CO₂ factor with current grid data.

## Changelog

| Date | Change |
| --- | --- |
| 2026-10-03 | Stack decisions agreed; layer 1 (foundation) and layer 2 (engine) completed; docs created |
| 2026-10-09 | **Live:** first deploy succeeded; `https://lung-scorer.duckdns.org/health` ok, `/status` ok (air data minutes old), Let's Encrypt certificate. Fixes on the way: the deploy role now trusts GitHub's immutable OIDC subject (`owner@id/repo@id`), and the GHCR images are public |
| 2026-10-09 | AWS demo environment created (66 resources, `lung-scorer.duckdns.org` → 13.200.124.7), secrets in SSM, GitHub `demo` environment + variables. CI: "which cells/users are in use" and the 7-day trip purge now use the app clock, not the database's; integration tests create the air partitions around their fixed day, so CI no longer breaks as the real date moves on |
| 2026-10-08 | Launch: no black screen between the splash and the UI (light-only app, window background #F3F4F6) |
| 2026-10-08 | Commute footprint (CO₂): Trends card + detail, India-specific factors with ranges and sources; bus and metro split (migration 0006) |
| 2026-10-06 | Layer 7c monitoring: log metrics, 3 app alarms, dashboard, public `/status` + GitHub uptime check |
| 2026-10-06 | Push alerts checked end to end: a real FCM push arrived on the phone |
| 2026-10-06 | Popular areas kept warm: Delhi NCR + 10 metro centres fetched hourly before anyone lives there (`warm_areas.yaml`) |
| 2026-10-06 | 5d: Google sign-in live on the phone; Firebase/FCM credentials in place; fixed the after-midnight (IST) "getting air data" hang (3 forecast days) |
| 2026-10-05 | Layer 7b: official station correction (OpenAQ live; CPCB built, needs a data.gov.in key); OpenAQ's India feeds found stale |
| 2026-10-05 | Layer 7a: NASA FIRMS fires → smoke-risk flag (upwind by tomorrow's wind, PostGIS), live with the key |
| 2026-10-05 | L5 Health Connect: heart rate, steps and workouts → activity (read-only, 2 days, idempotent re-sync, resting HR) |
| 2026-10-05 | Place search via our API (Nominatim + cache, ~1 s / 0.01 s cached); compact route view with the route visible and a new loading state |
| 2026-10-05 | Route planner by the air (From → To, fastest vs cleanest, whole-trip dose per way of travelling); change home & work from the Map |
| 2026-10-05 | M4 + L4: opt-in trip recording (background GPS + Android activity recognition → travel legs, raw points discarded, 7-day retention), legs scored with their own air and vehicle, drawn on the map |
| 2026-10-05 | Map M3: trips out of town (destination's air on those days), "where are you today" switch with current location, instant fetch + rescore |
| 2026-10-05 | AQI (India / US, user's choice) next to PM2.5, Lung Load shown as × WHO limit with a step-by-step breakdown, no more near-zero tips |
| 2026-10-05 | Map M1-M2: world PM2.5 map (MapLibre + OpenFreeMap), search and any-place forecast, commute route coloured by roadside PM2.5 with a per-vehicle comparison; floating glass tab bar; Fredoka headings |
| 2026-10-05 | Lung Load L3 + redesign: "glass and air" theme with a living smoke/breeze backdrop, breathing Lung Load ring, Log activity screen, Trends tab |
| 2026-10-05 | Lung Load L2 (API): activity table + endpoints, heart rate / steps → exertion on the server, score history with weekly insights; live run |
| 2026-10-05 | Lung Load L1 (engine): running, measured exertion from heart rate or steps, outdoor exercise near home/work, per-activity dose split, air breathed |
| 2026-10-05 | Layer 5d (part): geofencing + push code, Android build setup on D:, first debug build installed on the phone |
| 2026-10-04 | Layer 5a-5c: Expo 57 app: sign-in, onboarding, Today/Tomorrow/What-if/Settings, typed API client with token refresh; Node 22 via fnm |
| 2026-10-04 | Layer 6: OpenTofu (9 modules, demo + scale envs, bootstrap), production compose + Caddy, deploy/backup/restore scripts, CI/CD with OIDC deploy, infra security tests; production stack verified locally |
| 2026-10-04 | Layer 4: auth (argon2id, rotating refresh tokens with reuse detection, email codes, Google, account-takeover guard), Brevo, FCM, rate limits, all `/v1` endpoints, one error format; live API run |
| 2026-10-04 | Layer 3: schema, repositories, Open-Meteo + ORS integrations, services, SQS worker, seed; live Open-Meteo run; source tips added to the engine |
| 2026-10-04 | Layer 2b: 7 accuracy refinements (stations, route, mass-balance indoor + sources, geofence visits, personal breathing, nowcast + fire flag, uncertainty). Sensor input deferred. OpenRouteService chosen for routes |
