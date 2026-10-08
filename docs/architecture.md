# Architecture

The architecture as agreed and as built. Where it differs from the original design documents (the Game Plan PDF and the LLD `.md` in the repo root), **this file wins**.

## Goals and constraints

- Built for **real users**, not only a demo: production-grade auth, HTTPS, load balancing, backups and logs.
- **AWS**, on a budget of about **$100 in free credits**, using open-source or free tools only.
- **Python with uv, everything in Docker**, deployed on **EC2**.
- **Honest product:** "estimated exposure", never a diagnosis. Privacy first: two saved places and a declared schedule, with geofence events instead of a GPS trail.

## Production shape

```
Android app (Expo / React Native)
  · home + office geofences on the phone · FCM push · Google / email sign-in
        │ HTTPS: <name>.duckdns.org (Let's Encrypt via Caddy)
        ▼
EC2 t4g.small (ARM) + Elastic IP, ap-south-1 (Mumbai)
  ├─ caddy        TLS + load balancing across API replicas
  ├─ api ×2       FastAPI, built-in auth, rate limiting
  ├─ worker       SQS consumer: fetch air → recompute scores → alerts
  ├─ postgres     17 + PostGIS 3.6 (Docker volume)
  └─ valkey       cache
        │
AWS managed (free or near free):
  SQS ingest-jobs + user-jobs (each with a DLQ) · EventBridge Scheduler (hourly tick)
  S3 (nightly pg_dump) · CloudWatch Logs + DLQ alarm · SSM (deploys, secrets) · IAM instance role

Written in OpenTofu but switched off (envs/scale):
  ALB + ACM + Route 53 (needs a real domain) · RDS · ElastiCache

External (free tiers): Open-Meteo · OpenRouteService (commute routes) · Brevo (email) · FCM · Google OAuth · GHCR
Later: NASA FIRMS · OpenAQ · Prometheus / Grafana
```

### Why this shape

| Decision | Reason |
| --- | --- |
| Caddy instead of an ALB for now | DuckDNS can only point at an IP address (A record), and an ALB has none. ACM certificates can't be validated on DuckDNS. An ALB would also cost about $16-20 a month. The ALB code is ready for when a domain is bought |
| Postgres in a container, not RDS | RDS costs about $15 a month in credits. Nightly backups to S3 cover the risk; the RDS module is written but switched off |
| Valkey in a container | ElastiCache costs about $12 a month or more |
| SQS + EventBridge Scheduler | Managed, effectively free at our volume, and has dead-letter queues built in |
| Built-in auth (no Cognito, no Keycloak) | Open source and light enough for a 2 GB instance |
| Brevo + Google sign-in | EC2 blocks port 25 and self-hosted mail lands in spam; Brevo has a free tier |
| FCM | Free; Android push can't be self-hosted |
| React Native (Expo) | Background geofencing needs a native app |
| GHCR + SSM deploy | Free registry; no SSH port open on the instance |
| OpenRouteService for routes | Open source with a free API key; a route is looked up once per home/office change, so the free limit is plenty. Self-hosting OSRM for India needs 8-16 GB RAM. Fallback: straight-line sampling |
| Postgres on host port 55432, API on 18000 (local only) | Avoids services already running on the dev machine |

## Deployment

Runbook, costs, operations and security summary: [deployment.md](deployment.md). The infrastructure lives in `infra/` (OpenTofu), the server runtime in `deploy/`, the pipeline in `.github/workflows/ci-cd.yml`.

## Backend layers

```
api/  worker/                 entry points: parse, call one service, respond
   │
services/                     use cases: load → engine → save → cache → queue
   │
engine/  repositories/  integrations/  infra/  auth/
```

Rules:

1. Imports only point down.
2. `engine/` does no I/O, and doesn't read the clock or the environment. It uses only the standard library and its own files.
3. One table has one repository file; one external provider has one integration file.
4. Every number lives in `engine/config.yaml`; sources are in [engine-parameters.md](engine-parameters.md).

## Repository layout

```
.
├── apps/
│   ├── api/                       Python package "lung" (uv); API and worker share one image
│   │   ├── pyproject.toml uv.lock .python-version Dockerfile .dockerignore
│   │   ├── alembic.ini  migrations/            hand-written SQL migrations
│   │   ├── .env.example
│   │   ├── src/lung/
│   │   │   ├── main.py  settings.py
│   │   │   ├── api/                 ✅ errors, deps (auth, rate limits), schemas/, v1/{auth,me,scores,meta}
│   │   │   ├── auth/                ✅ passwords (argon2id), tokens (JWT, refresh, email codes)
│   │   │   ├── services/            ✅ auth, profile, score, air, ingest, route, alert, plan, mailer, notifier
│   │   │   ├── engine/              ✅ pure scoring maths + config.yaml
│   │   │   │     models config day dose indoor score cigarettes tips forecast
│   │   │   │     airdata (station correction) uncertainty (Monte Carlo)
│   │   │   ├── repositories/        ✅ one file per table, hand-written SQL
│   │   │   ├── integrations/        ✅ open_meteo, openrouteservice, google_auth, brevo, fcm (firms, openaq: layer 7)
│   │   │   ├── infra/               ✅ logging, engine_config, db, cache (fail-open), queue
│   │   │   ├── worker/              ✅ SQS poll loop + handlers (tick, fetch, route, recompute, alert)
│   │   │   ├── devtools/            ✅ seed (local only)
│   │   │   └── domain/              ✅ geo (cells, distance, sampling), air, errors
│   │   └── tests/unit/  tests/integration/  tests/fixtures/
│   └── mobile/                     ✅ Expo 57 app (see apps/mobile/README.md): auth, onboarding, tabs; native features in 5d
├── deploy/
│   ├── postgres/                   ✅ Postgres 17 + PostGIS image (ARM-ready)
│   ├── elasticmq/                  ✅ local SQS config
│   ├── compose.prod.yml            ✅ production stack (+ compose.local-prod.yml to run it locally)
│   ├── caddy/Caddyfile             ✅ HTTPS, headers, routing, load balancing
│   ├── scripts/                    ✅ render-env, deploy (auto-rollback), backup, restore, duckdns, put-secrets
│   └── systemd/                    ✅ backup and DuckDNS timers
├── infra/                          ✅ OpenTofu
│   ├── bootstrap/                  state bucket (once per account)
│   ├── modules/                    network compute storage queue iam monitoring edge rds stack (+ tests/)
│   └── envs/                       demo (deployed) · scale (ALB + RDS on; written only)
├── docs/                           this folder
├── scripts/  site/  .github/workflows/
├── docker-compose.yml              ✅ local stack
└── Makefile                        ✅ dev tasks
```

## Scoring engine

The engine is pure: data in, numbers out. Full details and sources are in [engine-parameters.md](engine-parameters.md).

```
Profile (+weight)  DayPlan (schedule, cells, route, indoor state + sources)  Visits (past)  Readings
        │                                   │                                      │            │
        └──────────────── day.build_day ────┴──────────────────────────────────────┘            │
                                   │ segments (place, activity, cell, factor, added, mask)       │
             airdata.correct ──────┼────────────────────────────── station-corrected readings ───┘
                                   ▼
                            score.compute  → Result (dose, score, band, split, cigarettes, source share)
              ┌────────────────────┼─────────────────────┬──────────────────────────┐
         tips.tips          tips.simulate        forecast.forecast           uncertainty.estimate_range
     (one change each)     (what-if slider)   (nowcast, fire flag, hours)    (p10/p50/p90, band odds)
```

**Optional inputs get more personal and more precise:** weight, home size, purifier CADR, indoor sources, a route, geofence visits and nearby stations each replace a typical value with the user's own, and narrow the uncertainty range.

## API and auth

The full endpoint list and the auth design (argon2id, 15-minute JWTs, single-use rotating refresh tokens with reuse detection, HMAC-hashed 6-digit email codes, Google ID-token verification, account-takeover guard, rate limits) are in [PROGRESS.md](PROGRESS.md#layer-4-auth--api-). In short:

```
App ──Bearer JWT──▶ Caddy ──▶ API
  sign-in: POST /v1/auth/{register|login|google} → {access (15 min), refresh (30 days, single-use)}
  before expiry: POST /v1/auth/refresh → new pair (an old refresh token coming back = theft → sign-in revoked)
  every other call: /v1/me/... with the access token; 401 → refresh → retry once → sign in
```

## Data flow

1. **Hourly:** EventBridge Scheduler (locally: the worker's own ticker) puts a `tick` on `ingest-jobs`. The worker sends one `fetch` per grid cell in use (places + route points + trips + recorded travel), plus the popular areas listed in `warm_areas.yaml` (Delhi NCR and 10 metro centres), so a new user there gets a score at once. A fetch is skipped if the cell was fetched under 50 minutes ago or another worker holds its 2-minute lock. Each fetch upserts `air_readings` and queues **one** delayed `recompute` per affected user.
2. **Recompute:** load the profile, places, route, schedule, indoor state, sources and today's visits → correct readings with stations → `nowcast` tomorrow → `build_day` → `compute` / `tips` / `forecast` / `estimate_range` → upsert `daily_scores` (with `engine_version`) → clear that user's cache → send an `alert` if tomorrow turns red or fire risk is high.
3. **Route:** when home, office or mode changes, a straight-line route is stored at once; with an ORS key it's replaced by the real route. Every user therefore always has route points, so the tick knows every cell they need.
4. **Alert:** insert into `alerts` with `ON CONFLICT DO NOTHING`; only if a row was added, send the FCM push. Running it twice is therefore safe.
5. **App reads:** the API checks Valkey first; on a miss it loads from the database, runs the engine, and caches the result for 15 minutes. Every score response carries `estimated: true` and `data_as_of`.

## Tech stack (locked versions as of 2026-10-03)

| Area | Choice |
| --- | --- |
| Language / tooling | Python 3.12, uv 0.11, ruff 0.16, mypy 2.4 (strict), pytest 9 |
| Web | FastAPI 0.142, uvicorn 0.54 |
| Data | SQLAlchemy 2.1 (async) + asyncpg 0.31, Alembic 1.20, GeoAlchemy2 0.20 |
| Cache / queue | valkey-py 6.1, aioboto3 15.5 (SQS) |
| HTTP / config / logs | httpx 0.28, pydantic-settings 2.15, PyYAML 6, structlog 26 |
| Auth | argon2-cffi 25, PyJWT 2.15 (crypto), email-validator 2.3 |
| Containers | Docker, Postgres 17 + PostGIS 3.6, Valkey 8, ElasticMQ 1.7.1 (local only) |
