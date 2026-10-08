/**
 * Trends card: this week's estimated commute CO2 and the one change worth making.
 * Hidden until we know the commute (home, work and a route). CO2 is climate, not the PM2.5
 * behind Lung Load, and the card says so.
 */
import { useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import { View } from 'react-native';

import { AppText, Button, Card, Overline } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import { headline, kg, kgRange } from '@/lib/footprint';
import { keys } from '@/lib/query';
import { space, useColors } from '@/theme';

export function FootprintCard() {
  const c = useColors();
  const q = useQuery({
    queryKey: keys.footprint,
    queryFn: meApi.footprint,
    staleTime: 10 * 60_000,
  });
  const commute = q.data?.commute;
  if (!q.data || !commute) return null;
  const h = headline(q.data);
  return (
    <Card>
      <Overline>Commute footprint · estimate</Overline>
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'flex-end',
          gap: space.sm,
          flexWrap: 'wrap',
        }}
        accessible
        accessibilityLabel={`About ${kg(commute.week_kg.central)} kilograms of CO2 a week, between ${kgRange(commute.week_kg)}`}>
        <AppText variant="display">{kg(commute.week_kg.central)}</AppText>
        <AppText muted style={{ paddingBottom: 8 }}>
          kg CO₂ a week ({kgRange(commute.week_kg)})
        </AppText>
      </View>
      {h ? (
        <AppText
          variant="label"
          color={h.tone === 'good' ? c.accent : c.text}
          style={{ fontWeight: '500' }}>
          {h.text}
        </AppText>
      ) : null}
      <AppText variant="caption" muted>
        CO₂ is about the climate, not the air you breathe: it doesn&apos;t change your Lung Load.
      </AppText>
      <Button
        title="Compare every way →"
        kind="secondary"
        compact
        onPress={() => router.push('/footprint')}
      />
    </Card>
  );
}
