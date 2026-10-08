import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { Alert, Platform } from 'react-native';

import { AlertsSetting } from '@/components/alerts-card';
import { SettingsGroup, SettingsRow } from '@/components/settings-list';
import { GeofenceCard } from '@/components/geofence-card';
import { HealthCard } from '@/components/health-card';
import { TripRecorderCard } from '@/components/trip-recorder-card';
import { AppText, Button, Card, ErrorBanner, Screen, Segmented } from '@/components/ui';
import { useAqiScale } from '@/lib/aqi';
import { authApi, meApi } from '@/lib/api/endpoints';
import type { ProfileOut } from '@/lib/api/types';
import { useSession } from '@/lib/auth/session';
import { errorMessage, keys } from '@/lib/query';
import { display } from '@/lib/time';

function confirm(title: string, message: string): Promise<boolean> {
  if (Platform.OS === 'web')
    return Promise.resolve(globalThis.confirm?.(`${title}\n\n${message}`) ?? false);
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
      { text: 'Delete', style: 'destructive', onPress: () => resolve(true) },
    ]),
  );
}

export default function Settings() {
  const { signOut } = useSession();
  const me = useQuery({ queryKey: keys.me, queryFn: authApi.me });
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  const summaries = summarize(profile.data);
  const [deleting, setDeleting] = useState(false);
  const del = useMutation({
    mutationFn: meApi.deleteAccount,
    onSuccess: () => signOut(),
  });

  return (
    <Screen edges={['top']}>
      <AppText variant="title">Settings</AppText>

      <Card>
        <AppText variant="caption" muted>
          Signed in as
        </AppText>
        <AppText variant="heading">{me.data?.email ?? '…'}</AppText>
      </Card>
      {me.data && !me.data.email_verified ? (
        <SettingsGroup title="Account">
          <SettingsRow
            icon="mail"
            label="Confirm your email"
            summary="Needed to reset your password"
            href="/verify-email"
            last
          />
        </SettingsGroup>
      ) : null}

      <SettingsGroup title="Your details">
        <SettingsRow
          icon="person"
          label="Profile & daily routine"
          summary={summaries.profile}
          href="/edit-profile"
        />
        <SettingsRow
          icon="home"
          label="Home air & indoor smoke"
          summary={summaries.indoor}
          href="/indoor"
          last
        />
      </SettingsGroup>

      <AqiScaleSetting />
      <GeofenceCard />
      <TripRecorderCard />
      <HealthCard />
      <AlertsSetting />

      <Card>
        <AppText variant="heading">About the estimate</AppText>
        <AppText variant="caption" muted>
          Lung Load compares the PM2.5 your lungs likely took in, counting how hard you were
          breathing (asleep, resting, walking, running), with the same day breathed at the WHO
          24-hour guideline (15 µg/m³). So 100 means "right at the guideline". It measures exposure,
          not the health of your lungs. Air data comes from Open-Meteo's air-quality model;
          breathing rates and indoor factors are population averages, personalised by your age, sex,
          weight and logged activity. It is an estimate, not a measurement and not medical advice.
        </AppText>
        <AppText variant="caption" muted>
          Privacy: we keep your age, sex, two places and schedule (plus anything optional you add).
          No continuous GPS tracking. Delete everything below at any time.
        </AppText>
      </Card>

      <ErrorBanner message={errorMessage(del.error)} />
      <Button title="Sign out" kind="secondary" onPress={() => signOut()} />
      <Button
        title="Delete my account and data"
        kind="danger"
        loading={del.isPending || deleting}
        onPress={async () => {
          setDeleting(true);
          const ok = await confirm(
            'Delete your account?',
            'This permanently deletes your account, profile, places, schedule and history. It cannot be undone.',
          );
          setDeleting(false);
          if (ok) del.mutate();
        }}
      />
    </Screen>
  );
}

const NEWLINE = String.fromCharCode(10);

const SEX: Record<string, string> = { man: 'man', woman: 'woman', other: 'other' };
const WINDOWS: Record<string, string> = {
  closed: 'Windows closed',
  normal: 'Windows sometimes open',
  open: 'Windows open',
};

/** One-line summaries of what's saved, so each row says what it holds. */
function summarize(p: ProfileOut | undefined) {
  if (!p) return { profile: '…', indoor: '…' };
  const home = p.places.home;
  const name = (x: { label?: string | null }, fallback: string) => x.label || fallback;
  const sources = home.sources.length;
  return {
    // two lines: who you are, then where and when you usually go
    profile: [
      [`${p.age}`, SEX[p.sex] ?? p.sex, p.weight_kg ? `${p.weight_kg} kg` : null]
        .filter(Boolean)
        .join(' · '),
      `${name(home, 'Home')} → ${name(p.places.office, 'Work')} · ${display(p.schedule.leave_home)}–${display(p.schedule.arrive_home)}`,
    ].join(NEWLINE),
    indoor: [
      WINDOWS[home.windows] ?? home.windows,
      home.purifier ? 'purifier' : null,
      sources ? `${sources} source${sources > 1 ? 's' : ''}` : 'no smoke',
    ]
      .filter(Boolean)
      .join(' · '),
  };
}

/** Which AQI scale to show next to PM2.5: India's (CPCB) or the US EPA's. */
function AqiScaleSetting() {
  const { scale, setScale } = useAqiScale();
  return (
    <Card>
      <AppText variant="heading">Air quality index</AppText>
      <Segmented
        options={[
          { value: 'in', label: 'India AQI' },
          { value: 'us', label: 'US AQI' },
        ]}
        value={scale}
        onChange={setScale}
      />
      <AppText variant="caption" muted>
        India's scale matches Indian news and government sites. The US scale is used by IQAir and
        many international apps; it gives higher numbers for the same air.
      </AppText>
    </Card>
  );
}
