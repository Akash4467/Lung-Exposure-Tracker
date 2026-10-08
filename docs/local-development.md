# Local development

## Prerequisites

| Tool | Version used | Check |
| --- | --- | --- |
| Docker Desktop | 27 (Compose v2.28+) | `docker info` (Desktop must be running) |
| uv | 0.11 | `uv --version` (installs Python 3.12 itself if needed) |
| GNU Make | 3.81+ | `make --version` (comes with Git for Windows) |
| Git | any recent | `git --version` |

## First run

```bash
cp apps/api/.env.example apps/api/.env   # once
make up        # Postgres+PostGIS, Valkey, ElasticMQ
make migrate   # apply database migrations
make seed      # demo user (Delhi home, Noida office) + first jobs queued
make worker    # worker: fetches live Open-Meteo data, computes scores (Ctrl+C to stop)
make api       # API with reload on http://localhost:18000  (docs: /docs)
```

After about a minute the demo user's scores are in the database:

```bash
docker compose exec postgres psql -U lung -d lung -c \
  "SELECT date, is_forecast, round(score) score, band FROM daily_scores"
```

Run the API and worker in Docker instead, the same way production does:

```bash
docker compose --profile app up -d --build api worker
curl localhost:18000/health     # {"status":"ok"}
docker compose logs -f worker
docker compose stop worker      # it ticks hourly and calls Open-Meteo while running
```

## Trying the API locally

No keys needed. Without Brevo, emails (with their codes) are printed in the API log. Without Google client IDs, Google sign-in answers 401. Without FCM, pushes are logged.

```bash
B=http://localhost:18000
curl -s -X POST $B/v1/auth/register -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"a long password"}'      # → access_token, refresh_token
# the verification code is in the API log ("email_logged")
T=<access_token>
curl -s -X PUT $B/v1/me/profile -H "Authorization: Bearer $T" -H 'content-type: application/json' -d @profile.json
curl -s $B/v1/me/score/today -H "Authorization: Bearer $T"            # 503 + Retry-After until air data lands
```

Interactive docs: http://localhost:18000/docs (switched off in production).

## Mobile app (web preview)

```bash
# once: Node 22 for this project only (global Node stays as is)
winget install Schniz.fnm && fnm install 22
cd apps/mobile && fnm exec --using=22 -- npm install && cp .env.example .env.local
# API: allow the preview's origin, then start it (make api, or the api container)
echo CORS_ORIGINS=http://localhost:8081 >> ../api/.env
fnm exec --using=22 -- npx expo start --web      # http://localhost:8081
fnm exec --using=22 -- npm run check             # tsc + lint + jest
```

To test sign-up without sending real emails, run the API with Brevo off for that session: `BREVO_API_KEY= make api` (codes are printed in the API log).

## Android device builds

The phone connects over USB (developer options → USB debugging). Everything heavy lives on D: so C: can't fill up:

```bash
export ANDROID_HOME='D:\dev-cache\android-sdk'
export GRADLE_USER_HOME='D:\dev-cache\gradle'
export npm_config_cache='D:\dev-cache\npm'
export JAVA_TOOL_OPTIONS='-Djava.io.tmpdir=D:\dev-cache\tmp'
export ORG_GRADLE_PROJECT_reactNativeArchitectures=arm64-v8a   # build only for the phone's CPU
adb reverse tcp:18000 tcp:18000      # the phone's localhost:18000 = this PC's API (no Wi-Fi setup)
adb reverse tcp:8081 tcp:8081        # Metro (JS bundler)
cd apps/mobile
fnm exec --using=22 -- npx expo prebuild --clean --platform android   # after app.json / plugin changes
fnm exec --using=22 -- npx expo run:android                          # build, install, start Metro
```

If Metro is already running, build and install without `run:android` (PowerShell; avoids `cmd` path quoting):

```powershell
$env:ANDROID_HOME='D:\dev-cache\android-sdk'; $env:GRADLE_USER_HOME='D:\dev-cache\gradle'
$env:JAVA_TOOL_OPTIONS='-Djava.io.tmpdir=D:\dev-cache\tmp'; $env:ORG_GRADLE_PROJECT_reactNativeArchitectures='arm64-v8a'
Set-Location apps\mobile\android; fnm exec --using=22 -- .\gradlew.bat assembleDebug
adb install -r -t app\build\outputs\apk\debug\app-debug.apk
```

After native changes or dependency installs, restart Metro with `npx expo start --clear`. After backend changes, rebuild the local worker: `docker compose up -d --build worker`.

The Android SDK on D: was set up once with:
`sdkmanager --sdk_root=D:\dev-cache\android-sdk platform-tools "platforms;android-36" "build-tools;36.0.0" "ndk;27.1.12297006" "cmake;3.22.1"`

## Daily commands

| Command | Does |
| --- | --- |
| `make check` | lint + strict type check + unit tests; no containers needed |
| `make check-all` | `check` + integration tests; needs `make up` |
| `make test` | Unit tests only |
| `make test-int` | Integration tests: a fresh `lung_test` database, real PostGIS/Valkey, fake providers |
| `make smoke` | Check the real providers with the keys in `.env` (Open-Meteo, OpenRouteService, Brevo key and verified senders); never prints a key. `make smoke EMAIL_TO=you@x.in` also sends one real email |
| `make seed` | Create the demo user and queue its first jobs |
| `make worker` | Run the worker locally; it queues a tick every 60 min (EventBridge does this in AWS) |
| `make prod-local` | Run the **production** compose stack on https://localhost:8443 (Caddy → 2 API replicas, worker, migrate, Postgres, Valkey); `make prod-local-down` removes it |
| `make infra-check` | tofu fmt/validate/test, shellcheck, Caddyfile, actionlint, all through Docker |
| `make fmt` | Auto-fix lint and formatting |
| `make image` | Build the API/worker image |
| `make down` | Stop containers (the database volume is kept) |

## Ports on your machine

These defaults avoid services already running on the dev machine (another project's Postgres and API, and a Windows PostgreSQL service).

| Service | Host port | Override |
| --- | --- | --- |
| Postgres | 55432 | `PG_HOST_PORT` |
| API (Docker) | 18000 | `API_HOST_PORT` |
| API (`make api`) | 18000 | `API_PORT` |
| Valkey | 6379 | — |
| ElasticMQ (SQS) | 9324 | — |

Inside Docker, services use their normal ports (`postgres:5432`, `valkey:6379`, `elasticmq:9324`).

## Useful checks

```bash
docker compose exec postgres psql -U lung -d lung -c "select postgis_full_version()"
docker compose exec valkey valkey-cli ping
curl "http://localhost:9324/?Action=ListQueues"
```

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `password authentication failed for user "lung"` | Another Postgres is answering on that port. Check `DATABASE_URL` uses 55432, or set `PG_HOST_PORT` |
| `port is already allocated` | Something else holds the host port; override it with the variables above |
| `No time zone found with key Asia/Kolkata` | Run `uv sync`; the `tzdata` package provides time zones on Windows |
| `open //./pipe/dockerDesktopLinuxEngine` | Docker Desktop isn't running |
| Scores never appear | Is a worker running (`make worker` or the `worker` container)? Check `docker compose logs worker` for `fetched` / `recomputed` |
| `recompute_skipped ... profile incomplete` | The user has no profile, home, office or schedule yet |
| `job_retry ... no air data` | Normal on a first run: the missing cells are being fetched and the recompute retries itself |
| `curl: (43) A libcurl function was given a bad argument` on `https://localhost:8443` | A bug in Git Bash's curl with `-k -w`; drop `-w` or use Python httpx |
| Browser warns on https://localhost:8443 | Expected: Caddy's local CA isn't trusted by your OS (production uses Let's Encrypt) |
| Expo: `Node.js ... is not supported` | Use Node 22 via `fnm exec --using=22 -- ...` |
| Expo: route types out of date / edits not picked up | Don't start Expo with `CI=1` (CI mode disables file watching) |
| Browser preview: screenshots time out, clicks don't register | The Chrome window is hidden/minimised; bring it to the front |
| Android build: `No space left on device` | C: is full; use the D: cache variables above |
| `expo run:android --device <serial>` fails | `--device` wants the device *name*; with one phone connected, leave it out |
| Integration test loses queue messages | A running worker consumes `user-jobs`; the queue test uses its own throwaway queue, but stop the worker if you poke the shared queues by hand |

## External services (optional locally)

| Service | Needed for | Without it |
| --- | --- | --- |
| Open-Meteo | Air data | Required, but needs **no key** |
| OpenRouteService (`ORS_API_KEY`) | Real commute routes with road types | Straight-line route between home and office |
| Brevo (`BREVO_API_KEY`, `MAIL_FROM`) | Verification and reset emails | Emails printed in the API log (refused in production) |
| Google (`GOOGLE_CLIENT_IDS`) | Google sign-in | Google sign-in returns 401 |
| Firebase (`FCM_PROJECT_ID`, `FCM_SERVICE_ACCOUNT_JSON`) | Push alerts | Pushes are logged |
| `JWT_SECRET` | Signing access tokens | A dev secret (refused in production) |
