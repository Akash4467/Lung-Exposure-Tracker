/** "AQI 121 · Moderate" in the band's colour, on the scale chosen in Settings. */
import { StyleSheet, View } from 'react-native';

import { AppText } from '@/components/ui';
import { aqi, SCALE_NAME, useAqiScale } from '@/lib/aqi';
import { radius, space } from '@/theme';

/** `short`: just "AQI 300" (narrow places); the category is still read out. */
export function AqiPill({
  pm25,
  small,
  short,
}: {
  pm25: number;
  small?: boolean;
  short?: boolean;
}) {
  const scale = useAqiScale((s) => s.scale);
  const a = aqi(pm25, scale);
  const dark = a.color === '#E8B923' || a.color === '#8BC34A'; // light fills need dark text
  return (
    <View
      style={[styles.pill, { backgroundColor: a.color }, small && styles.small]}
      accessibilityLabel={`${SCALE_NAME[scale]} ${a.value}, ${a.label}`}>
      <AppText variant="label" color={dark ? '#121417' : '#FFFFFF'} numberOfLines={1}>
        AQI {a.value}
        {short ? '' : ` · ${a.label}`}
      </AppText>
    </View>
  );
}

export function useAqi(pm25: number) {
  const scale = useAqiScale((s) => s.scale);
  return { ...aqi(pm25, scale), scaleName: SCALE_NAME[scale] };
}

const styles = StyleSheet.create({
  pill: {
    alignSelf: 'flex-start',
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    paddingVertical: 4,
    maxWidth: '100%',
  },
  small: { paddingVertical: 2, paddingHorizontal: space.sm },
});
