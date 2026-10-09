# Lung Exposure Tracker

Estimates how much PM2.5 a person breathes in each day from where they spend their time, and suggests what to change. **Estimated exposure, informational only, not medical advice.**

## Try it (Android)

Scan with an Android phone, or open the link: the APK downloads, then tap **Install** (allow installs from your browser if asked). Live API: `https://lung-scorer.duckdns.org`.

<img src="docs/assets/download-apk-qr.png" alt="QR code: download the Android app" width="180">

[Download lung-score.apk](https://lung-scorer.duckdns.org/app) (always the latest build, served from AWS Mumbai; also on [GitHub Releases](https://github.com/Akash4467/Lung-Exposure-Tracker/releases/latest))

## Status

| Layer | |
| --- | --- |
| 1. Foundation (uv, Docker, local stack) | ✅ |
| 2. Scoring engine | ✅ |
| 2b. Engine accuracy refinements (stations, route, indoor model, geofence, personal breathing, nowcast, uncertainty) | ✅ |
| 3. Data: schema, Open-Meteo + routes, services, SQS worker | ✅ |
| 4. Auth + API (email/password, Google, JWT + rotating refresh, Brevo, FCM, rate limits) | ✅ |
| 5. Mobile app (Expo 57): sign-in, onboarding, Today/Tomorrow/What-if/Settings | 🟡 5a-5c ✅ · 5d (APK, geofencing, push, Google) next |
| 6. Infra + CI/CD (OpenTofu, Caddy, GHCR, SSM deploy, backups, alarms) | ✅ live on AWS (`lung-scorer.duckdns.org`) |

Details: [docs/PROGRESS.md](docs/PROGRESS.md)

## Quick start

```bash
cp apps/api/.env.example apps/api/.env
make up && make migrate                 # local Postgres+PostGIS, Valkey, SQS
make seed && make worker                # demo user + live Open-Meteo data → scores
make api                                # http://localhost:18000/docs
make check-all                          # lint + types + unit + integration tests
```

More: [docs/local-development.md](docs/local-development.md)

## Layout

| Path | What lives there |
| --- | --- |
| `apps/api/` | Python package (uv): FastAPI API **and** the SQS worker, same Docker image |
| `apps/api/src/lung/engine/` | Pure scoring maths + `config.yaml`; no I/O |
| `apps/mobile/` | Expo 57 / React Native app ([README](apps/mobile/README.md)) |
| `infra/` | OpenTofu: `envs/demo` (deployed) and `envs/scale` (ALB, RDS; switched off) |
| `deploy/` | Postgres image, local SQS config, Caddy and production Compose |
| `docs/` | Progress, architecture, local dev, engine parameter sources |

## Docs

- [Progress](docs/PROGRESS.md): what's done, what's next, and decisions that differ from the design docs
- [Architecture](docs/architecture.md): production shape on AWS and why
- [Deployment runbook](docs/deployment.md): AWS setup, deploys, backups, costs
- [Local development](docs/local-development.md)
- [Engine parameters](docs/engine-parameters.md): every number and its source
