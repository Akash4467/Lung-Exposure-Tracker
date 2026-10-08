# Lung Exposure Tracker: mobile app

Expo SDK 57 · React Native 0.86 · React 19 · TypeScript (strict) · Expo Router · TanStack Query · Zustand.

## Run it

Node **22.13+** is required (Expo 57). This repo pins it in `.node-version`; with fnm:

```bash
fnm exec --using=22 -- npm install
cp .env.example .env.local          # set EXPO_PUBLIC_API_URL for where the API runs
fnm exec --using=22 -- npx expo start --web     # browser preview (dev only)
```

For the browser preview the API must allow the page's origin: `CORS_ORIGINS=http://localhost:8081` in `apps/api/.env`.

Native features (geofencing, push, Google sign-in) need a development build, not Expo Go: see step 5d in `docs/PROGRESS.md`.

## Checks

```bash
npm run check     # tsc --noEmit && expo lint && jest --ci
```

## Layout

```
src/app/                    routes (Expo Router); each file is a screen
  index.tsx                 the one unguarded route: sends users to their area
  (auth)/                   sign-in, sign-up, forgot-password        (signed out)
  (onboarding)/             profile → places → schedule → details     (signed in, not onboarded)
  (app)/(tabs)/             today, tomorrow, simulate, settings      (onboarded)
  (app)/                    verify-email, edit-profile, indoor
src/components/             ui (design system), controls, score visuals, place picker, indoor editor
src/lib/api/                typed client (token refresh, error format), endpoints, types mirroring the API
src/lib/auth/               session (SecureStore), area gate
src/store/onboarding.ts     onboarding draft + validation mirroring the API
src/theme/                  colours (light/dark), spacing, type, band labels
```

Rules: band colours always come with a text label; every score screen says "estimated" and shows the disclaimer; field names match the API exactly (snake_case).
