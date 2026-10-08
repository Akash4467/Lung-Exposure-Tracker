import { useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, View } from 'react-native';

import { AppText, Button, ErrorBanner, TextField } from '@/components/ui';
import { useDebounced } from '@/lib/use-debounced';
import { currentPlace, LocationDenied, type Place, searchPlaces } from '@/lib/geocode';
import type { PlaceDraft } from '@/store/onboarding';
import { radius, space, useColors } from '@/theme';

/** Pick a place by typing an address or using the phone's location. */
export function PlacePicker({
  title,
  value,
  onChange,
}: {
  title: string;
  value: PlaceDraft | null;
  onChange: (p: PlaceDraft | null) => void;
}) {
  const c = useColors();
  const [query, setQuery] = useState('');
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState<string | null>(null);

  // Search once typing pauses; TanStack Query cancels stale requests and caches answers.
  const term = useDebounced(query.trim(), 400);
  const search = useQuery({
    queryKey: ["places", term],
    queryFn: ({ signal }) => searchPlaces(term, signal),
    enabled: term.length >= 3,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const results = term.length >= 3 ? (search.data ?? []) : [];
  const searchError = search.isError
    ? "Search isn't available right now."
    : search.isSuccess && term.length >= 3 && results.length === 0
      ? "No matches. Try a nearby landmark or area name."
      : null;
  const error = locError ?? searchError;
  const searching = search.isFetching;

  const pick = (p: Place) => {
    onChange({ label: p.label, detail: p.detail, lat: p.lat, lon: p.lon });
    setQuery('');
    setLocError(null);
  };

  const useHere = async () => {
    setLocating(true);
    setLocError(null);
    try {
      pick(await currentPlace());
    } catch (e) {
      setLocError(
        e instanceof LocationDenied
          ? 'Allow location access, or search for the address instead.'
          : "Couldn't get your location. Search for the address instead.",
      );
    } finally {
      setLocating(false);
    }
  };

  if (value) {
    return (
      <View style={[styles.chosen, { borderColor: c.text, backgroundColor: c.glassStrong }]}>
        <View style={{ flex: 1, gap: 2 }}>
          <AppText variant="caption" muted>
            {title}
          </AppText>
          <AppText variant="heading">{value.label}</AppText>
          <AppText variant="caption" muted>
            {value.detail || `${value.lat.toFixed(4)}, ${value.lon.toFixed(4)}`}
          </AppText>
        </View>
        <Button title="Change" kind="ghost" onPress={() => onChange(null)} />
      </View>
    );
  }

  return (
    <View style={{ gap: space.sm }}>
      <TextField
        label={title}
        value={query}
        onChangeText={setQuery}
        placeholder="Search an address, area or landmark"
        autoCorrect={false}
      />
      {searching ? <ActivityIndicator color={c.text} /> : null}
      {results.map((r, i) => (
        <Pressable
          key={`${r.lat},${r.lon},${i}`}
          accessibilityRole="button"
          onPress={() => pick(r)}
          style={({ pressed }) => [
            styles.result,
            { borderColor: c.border, backgroundColor: pressed ? c.surfaceMuted : c.surface },
          ]}>
          <AppText>{r.label}</AppText>
          {r.detail ? (
            <AppText variant="caption" muted>
              {r.detail}
            </AppText>
          ) : null}
        </Pressable>
      ))}
      <ErrorBanner message={error} />
      <Button title="Use my current location" kind="secondary" onPress={useHere} loading={locating} />
    </View>
  );
}

const styles = StyleSheet.create({
  chosen: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    padding: space.md,
    borderRadius: radius.md,
    borderWidth: 1.5,
  },
  result: { padding: space.md, borderRadius: radius.md, borderWidth: StyleSheet.hairlineWidth, gap: 2 },
});
