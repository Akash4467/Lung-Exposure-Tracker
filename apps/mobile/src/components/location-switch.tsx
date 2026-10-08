/**
 * Top-right of Today: where today's Lung Load is worked out. Tap to choose home, the phone's
 * current location, or any place found by search. A place counts as a one-day trip on the
 * server; home ends any trip on today. Today is rescored straight away.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AppText, Card, ErrorBanner } from "@/components/ui";
import { locationApi, meApi } from "@/lib/api/endpoints";
import type { LocationIn } from "@/lib/api/types";
import { currentPlace, LocationDenied, searchPlaces } from "@/lib/geocode";
import { errorMessage, keys } from "@/lib/query";
import { useDebounced } from "@/lib/use-debounced";
import { radius, space, useColors } from "@/theme";

export function useTodayLocation() {
  return useQuery({ queryKey: keys.location, queryFn: locationApi.get });
}

export function LocationChip() {
  const c = useColors();
  const loc = useTodayLocation();
  const [open, setOpen] = useState(false);
  const label = loc.data?.kind === "trip" ? loc.data.trip.label : "Home";
  return (
    <>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={`Location: ${label}. Change`}
        onPress={() => setOpen(true)}
        style={({ pressed }) => [
          styles.chip,
          {
            backgroundColor: c.glassStrong,
            borderColor: c.glassBorder,
            opacity: pressed ? 0.8 : 1,
          },
        ]}
      >
        <AppText variant="label">⌖</AppText>
        <AppText variant="label" numberOfLines={1} style={{ maxWidth: 150 }}>
          {label}
        </AppText>
        <AppText variant="caption" muted>
          ▾
        </AppText>
      </Pressable>
      {open ? (
        <LocationSheet onClose={() => setOpen(false)} current={label} />
      ) : null}
    </>
  );
}

function LocationSheet({
  onClose,
  current,
}: {
  onClose: () => void;
  current: string;
}) {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [gpsError, setGpsError] = useState<string | null>(null);
  const [locating, setLocating] = useState(false);
  const q = useDebounced(query, 450);
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  const results = useQuery({
    queryKey: ["location-search", q],
    queryFn: ({ signal }) => searchPlaces(q, signal),
    enabled: q.trim().length >= 3,
  });

  const set = useMutation({
    mutationFn: (body: LocationIn) => locationApi.set(body),
    onSuccess: async () => {
      await Promise.all(
        [
          keys.location,
          keys.today,
          keys.forecast,
          keys.trips,
          keys.history,
        ].map((k) => qc.invalidateQueries({ queryKey: k })),
      );
      onClose();
    },
  });

  const useGps = async () => {
    setGpsError(null);
    setLocating(true);
    try {
      const p = await currentPlace();
      const places = profile.data?.places;
      const nearUsual =
        places && [places.home, places.office].some((x) => km(x, p) <= NEAR_KM);
      // At (or next to) home or work, "my location" is just the usual day, with its commute
      // and the home's own smoke sources; anywhere else counts as a day away.
      if (nearUsual) set.mutate({ kind: "home" });
      else
        set.mutate({
          kind: "place",
          label: p.label === "Current location" ? "My location" : p.label,
          lat: p.lat,
          lon: p.lon,
        });
    } catch (e) {
      setGpsError(
        e instanceof LocationDenied
          ? "Location permission is off. You can allow it in your phone settings, or search instead."
          : "Could not get your location. Try again or search instead.",
      );
    } finally {
      setLocating(false);
    }
  };

  const busy = set.isPending || locating;
  return (
    <Modal transparent animationType="fade" onRequestClose={onClose}>
      <Pressable
        style={styles.backdrop}
        onPress={onClose}
        accessibilityLabel="Close"
      />
      <View
        style={[styles.sheetWrap, { paddingBottom: insets.bottom + space.lg }]}
      >
        <Card strong style={{ gap: space.md, backgroundColor: "#FAFAFB" }}>
          <View style={styles.head}>
            <View style={{ flex: 1 }}>
              <AppText variant="heading">Where are you today?</AppText>
              <AppText variant="caption" muted>
                Today's Lung Load uses the air where you are. Now: {current}.
              </AppText>
            </View>
            {busy ? <ActivityIndicator color={c.text} /> : null}
          </View>
          <ErrorBanner message={gpsError ?? errorMessage(set.error)} />

          <Option
            icon="⌂"
            title="Home"
            hint="Your usual day: home, commute and work"
            selected={current === "Home"}
            disabled={busy}
            onPress={() => set.mutate({ kind: "home" })}
          />
          <Option
            icon="◎"
            title="Use my current location"
            hint="From your phone's GPS. Near home or work, your usual day applies"
            disabled={busy}
            onPress={useGps}
          />

          <View style={[styles.search, { backgroundColor: c.field }]}>
            <AppText muted>⌕</AppText>
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search any place"
              placeholderTextColor="#8A8F98"
              accessibilityLabel="Search a place"
              maxFontSizeMultiplier={1.3}
              style={[styles.searchInput, { color: c.text }]}
            />
          </View>
          {results.data?.length ? (
            <View>
              {results.data.slice(0, 5).map((p, i) => (
                <Pressable
                  key={`${i}:${p.lat},${p.lon}`}
                  accessibilityRole="button"
                  disabled={busy}
                  onPress={() =>
                    set.mutate({
                      kind: "place",
                      label: p.label,
                      lat: p.lat,
                      lon: p.lon,
                    })
                  }
                  style={({ pressed }) => [
                    styles.result,
                    pressed && { backgroundColor: c.field },
                  ]}
                >
                  <AppText numberOfLines={1}>{p.label}</AppText>
                  {p.detail ? (
                    <AppText variant="caption" muted numberOfLines={1}>
                      {p.detail}
                    </AppText>
                  ) : null}
                </Pressable>
              ))}
            </View>
          ) : null}
        </Card>
      </View>
    </Modal>
  );
}

function Option({
  icon,
  title,
  hint,
  selected,
  disabled,
  onPress,
}: {
  icon: string;
  title: string;
  hint: string;
  selected?: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  const c = useColors();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!selected, disabled: !!disabled }}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.option,
        {
          borderColor: selected ? c.text : c.glassBorder,
          borderWidth: selected ? 1.5 : 1,
          backgroundColor: pressed ? c.field : c.glass,
        },
      ]}
    >
      <AppText variant="heading" style={{ width: 28, textAlign: "center" }}>
        {icon}
      </AppText>
      <View style={{ flex: 1 }}>
        <AppText variant="label">{title}</AppText>
        <AppText variant="caption" muted>
          {hint}
        </AppText>
      </View>
      {selected ? <AppText variant="label">✓</AppText> : null}
    </Pressable>
  );
}

/** Within this distance of home or work, "my location" means the usual day. */
const NEAR_KM = 1.5;

function km(
  a: { lat: number; lon: number },
  b: { lat: number; lon: number },
): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * 6371 * Math.asin(Math.sqrt(h));
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    borderWidth: 1,
    borderRadius: radius.pill,
    paddingHorizontal: space.md,
    minHeight: 40,
    boxShadow: "0px 4px 14px rgba(30, 40, 60, 0.10)",
  },
  backdrop: {
    position: "absolute",
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    backgroundColor: "rgba(18,20,23,0.35)",
  },
  sheetWrap: {
    position: "absolute",
    left: space.lg,
    right: space.lg,
    bottom: 0,
  },
  head: { flexDirection: "row", alignItems: "center", gap: space.md },
  option: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.md,
    borderRadius: radius.md,
    padding: space.md,
  },
  search: {
    flexDirection: "row",
    alignItems: "center",
    gap: space.sm,
    borderRadius: radius.pill,
    paddingHorizontal: space.lg,
  },
  searchInput: {
    flex: 1,
    fontSize: 16,
    minHeight: 46,
    fontFamily: "Inter_400Regular",
  },
  result: {
    paddingVertical: space.sm,
    paddingHorizontal: space.md,
    borderRadius: radius.sm,
  },
});
