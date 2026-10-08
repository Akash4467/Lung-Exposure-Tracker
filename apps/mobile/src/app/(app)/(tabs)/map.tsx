/**
 * The air map: scroll and zoom anywhere in the world like any map app, with a soft coloured
 * layer of PM2.5 over it. Search a place or tap anywhere to see its air now and the next days.
 *
 * Base map: OpenFreeMap (free OpenStreetMap vector tiles, no key). Air: Open-Meteo's global
 * model via our API (/v1/map/grid), about 10-40 km per square: city-level, not street-level.
 */
import {
  Camera,
  type CameraRef,
  GeoJSONSource,
  Layer,
  Map,
  NativeUserLocation,
  type ViewStateChangeEvent,
} from '@maplibre/maplibre-react-native';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { router } from 'expo-router';
import * as Location from 'expo-location';
import { useContext, useEffect, useRef, useState } from 'react';
import {
  Keyboard,
  type NativeSyntheticEvent,
  Pressable,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { CommuteSheet, type Leg } from '@/components/commute-sheet';
import {
  type Endpoint,
  planShapes,
  routeBounds,
  RoutePanel,
  RouteSheet,
} from '@/components/route-planner';
import { type MapPlace, PlaceSheet } from '@/components/place-sheet';
import { AppText, Button, Card } from '@/components/ui';
import { aqiBands, aqiColorExpression, SCALE_NAME, useAqiScale } from '@/lib/aqi';
import { mapApi, meApi, tracksApi } from '@/lib/api/endpoints';
import type { CommuteOut, TravelLegOut } from '@/lib/api/types';
import { currentPosition, reverse, searchPlaces } from '@/lib/geocode';
import { errorMessage, keys } from '@/lib/query';
import { TabBarSpace } from '@/lib/tab-bar-space';
import { useDebounced } from '@/lib/use-debounced';
import { radius, space, useColors } from '@/theme';

const STYLE = 'https://tiles.openfreemap.org/styles/positron';
const INDIA: [number, number] = [79, 22.5];

type Bounds = { south: number; west: number; north: number; east: number };

const r2 = (v: number) => Math.round(v * 100) / 100;

export default function MapScreen() {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const tabBar = useContext(TabBarSpace);
  const camera = useRef<CameraRef>(null);
  const [view, setView] = useState<{ bounds: Bounds; zoom: number } | null>(null);
  const [selected, setSelected] = useState<MapPlace | null>(null);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [showCommute, setShowCommute] = useState(false);
  const [leg, setLeg] = useState<Leg>('morning');
  const [routing, setRouting] = useState(false);
  const [from, setFrom] = useState<Endpoint | null>(null);
  const [to, setTo] = useState<Endpoint | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const q = useDebounced(query, 450);
  const scale = useAqiScale((s) => s.scale);
  const airColor = aqiColorExpression(scale) as never;

  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  const home = profile.data?.places.home;

  const commute = useQuery({
    queryKey: ['commute'],
    queryFn: meApi.commute,
    enabled: !!home,
    staleTime: 10 * 60_000,
  });

  const tracks = useQuery({ queryKey: keys.tracks, queryFn: tracksApi.today, staleTime: 60_000 });

  const grid = useQuery({
    queryKey: ['map-grid', view?.bounds],
    queryFn: () => mapApi.grid(view!.bounds),
    enabled: !!view,
    placeholderData: keepPreviousData,
    staleTime: 10 * 60_000,
  });
  const plan = useQuery({
    queryKey: ['route-plan', from?.lat, from?.lon, to?.lat, to?.lon],
    queryFn: () => mapApi.route(from!, to!),
    enabled: routing && !!from && !!to,
    staleTime: 10 * 60_000,
  });
  // The cleanest drive is shown first; the person can pick another.
  const firstPick = plan.data?.options.find((o) => o.cleanest) ?? plan.data?.options[0];
  const selectedRoute = chosen ?? firstPick?.id ?? null;
  const shapes = planShapes(plan.data, selectedRoute);
  const bounds = routing ? routeBounds(plan.data, selectedRoute) : null;
  const boundsKey = bounds?.join(',');
  useEffect(() => {
    if (!boundsKey) return;
    const b = boundsKey.split(',').map(Number) as [number, number, number, number];
    // room for the one-line trip bar on top and the route cards below
    camera.current?.fitBounds(b, {
      padding: { top: insets.top + 90, bottom: (tabBar || 90) + 330, left: 40, right: 40 },
      duration: 900,
    });
  }, [boundsKey, insets.top, tabBar]);

  const results = useQuery({
    queryKey: ['map-search', q],
    queryFn: ({ signal }) =>
      searchPlaces(q, signal, home ? { lat: home.lat, lon: home.lon } : undefined),
    enabled: searching && q.trim().length >= 3,
  });

  const onRegion = (e: NativeSyntheticEvent<ViewStateChangeEvent>) => {
    const [west, south, east, north] = e.nativeEvent.bounds;
    setView({
      zoom: e.nativeEvent.zoom,
      bounds: {
        south: r2(Math.max(-85, south)),
        west: r2(Math.max(-180, west)),
        north: r2(Math.min(85, north)),
        east: r2(Math.min(180, east)),
      },
    });
  };

  const goTo = (p: MapPlace, zoom = 10) => {
    camera.current?.flyTo({ center: [p.lon, p.lat], zoom, duration: 1200 });
    setSelected(p);
  };

  const fitTrip = (a: Endpoint, b: Endpoint) =>
    camera.current?.fitBounds(
      [
        Math.min(a.lon, b.lon),
        Math.min(a.lat, b.lat),
        Math.max(a.lon, b.lon),
        Math.max(a.lat, b.lat),
      ],
      { padding: { top: 260, bottom: 470, left: 50, right: 50 }, duration: 1000 },
    );

  /** Directions: from my location (if allowed) to `dest` (or to be searched). */
  const startRouting = async (dest: Endpoint | null) => {
    setSelected(null);
    setShowCommute(false);
    setChosen(null);
    setTo(dest);
    setFrom(null);
    setRouting(true);
    try {
      const me = { label: 'My location', ...(await currentPosition()) };
      setFrom(me);
      if (dest) fitTrip(me, dest);
    } catch {
      // no location: the person types where they start
    }
  };

  const locateMe = async () => {
    const perm = await Location.requestForegroundPermissionsAsync();
    if (!perm.granted) return;
    const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    const { latitude: lat, longitude: lon } = pos.coords;
    goTo({ lat, lon, label: 'You are here' }, 11);
  };

  // One soft blob per grid point, big enough to overlap its neighbours into a smooth cloud.
  const step = grid.data?.step ?? 0.1;
  const zoom = view?.zoom ?? 4;
  const pxPerDegree = (512 * 2 ** zoom) / 360;
  const blobRadius = Math.min(320, Math.max(22, step * pxPerDegree * 1.15));
  const airShape: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: (grid.data?.points ?? []).map((p) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { pm25: p.pm25 },
    })),
  };
  const pin: GeoJSON.FeatureCollection = {
    type: 'FeatureCollection',
    features: selected
      ? [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: [selected.lon, selected.lat] },
            properties: {},
          },
        ]
      : [],
  };

  // Open on the user's home: wait for the profile so the first camera position is right.
  if (profile.isPending) return <View style={{ flex: 1, backgroundColor: c.background }} />;

  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <Map
        style={StyleSheet.absoluteFill}
        mapStyle={STYLE}
        logo={false}
        attributionPosition={{ top: insets.top + 70, right: 8 }}
        compass={false}
        onRegionDidChange={onRegion}
        onPress={async (e) => {
          const [lon, lat] = e.nativeEvent.lngLat;
          Keyboard.dismiss();
          setSearching(false);
          setSelected({
            lat,
            lon,
            label: 'Dropped pin',
            detail: `${lat.toFixed(3)}, ${lon.toFixed(3)}`,
          });
          const named = await reverse(lat, lon);
          if (named) setSelected({ lat, lon, label: named.label, detail: named.detail });
        }}>
        <Camera
          ref={camera}
          initialViewState={{
            center: home ? [home.lon, home.lat] : INDIA,
            zoom: home ? 9 : 3.5,
          }}
        />
        <GeoJSONSource id="air" data={airShape}>
          <Layer
            id="air-cloud"
            type="circle"
            paint={{
              'circle-radius': blobRadius,
              'circle-color': airColor,
              'circle-opacity': 0.38,
              'circle-blur': 1,
            }}
          />
        </GeoJSONSource>
        {commute.data && !routing ? (
          <>
            <GeoJSONSource id="route" data={routeShape(commute.data, leg)}>
              <Layer
                id="route-casing"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{ 'line-color': '#FFFFFF', 'line-width': 9 }}
              />
              <Layer
                id="route-air"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{ 'line-color': airColor, 'line-width': 5 }}
              />
            </GeoJSONSource>
            <GeoJSONSource id="places" data={placesShape(commute.data)}>
              <Layer
                id="places-dot"
                type="circle"
                paint={{
                  'circle-radius': 7,
                  'circle-color': '#FFFFFF',
                  'circle-stroke-color': '#121417',
                  'circle-stroke-width': 3,
                }}
              />
              <Layer
                id="places-label"
                type="symbol"
                layout={{
                  'text-field': ['get', 'name'],
                  'text-size': 13,
                  'text-offset': [0, 1.3],
                  'text-anchor': 'top',
                  'text-font': ['Noto Sans Bold'],
                }}
                paint={{
                  'text-color': '#121417',
                  'text-halo-color': '#FFFFFF',
                  'text-halo-width': 1.5,
                }}
              />
            </GeoJSONSource>
          </>
        ) : null}
        {tracks.data?.legs.length ? (
          <GeoJSONSource id="travel" data={legsShape(tracks.data.legs)}>
            <Layer
              id="travel-line"
              type="line"
              layout={{ 'line-cap': 'round', 'line-join': 'round' }}
              paint={{
                'line-color': [
                  'match',
                  ['get', 'mode'],
                  'walk',
                  '#3E8E6E',
                  'run',
                  '#E07B39',
                  'cycle',
                  '#4C8DC9',
                  '#121417',
                ] as never,
                'line-width': 4,
                'line-dasharray': [1.5, 1.2],
              }}
            />
          </GeoJSONSource>
        ) : null}
        {routing ? (
          <>
            <GeoJSONSource id="plan-others" data={shapes.others}>
              <Layer
                id="plan-others-line"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{ 'line-color': '#8A8F98', 'line-width': 5, 'line-opacity': 0.6 }}
              />
            </GeoJSONSource>
            <GeoJSONSource id="plan-chosen" data={shapes.chosen}>
              <Layer
                id="plan-casing"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{ 'line-color': '#FFFFFF', 'line-width': 10 }}
              />
              <Layer
                id="plan-air"
                type="line"
                layout={{ 'line-cap': 'round', 'line-join': 'round' }}
                paint={{ 'line-color': airColor, 'line-width': 6 }}
              />
            </GeoJSONSource>
          </>
        ) : null}
        <GeoJSONSource id="pin" data={pin}>
          <Layer
            id="pin-dot"
            type="circle"
            paint={{
              'circle-radius': 8,
              'circle-color': '#121417',
              'circle-stroke-color': '#FFFFFF',
              'circle-stroke-width': 3,
            }}
          />
        </GeoJSONSource>
        <NativeUserLocation />
      </Map>

      {/* search, or the route panel */}
      <View style={[styles.top, { top: insets.top + space.sm }]}>
        {routing ? (
          <RoutePanel
            from={from}
            to={to}
            near={from ?? (home ? { lat: home.lat, lon: home.lon } : undefined)}
            onClose={() => setRouting(false)}
            onChange={(field, e) => {
              setChosen(null);
              if (field === 'from') setFrom(e);
              else setTo(e);
              const a = field === 'from' ? e : from;
              const b = field === 'to' ? e : to;
              if (a && b) fitTrip(a, b);
            }}
          />
        ) : (
          <>
            <View style={{ flexDirection: 'row', gap: space.sm }}>
              <Card strong style={{ ...styles.search, flex: 1 }}>
                <AppText muted>⌕</AppText>
                <TextInput
                  value={query}
                  onChangeText={(t) => {
                    setQuery(t);
                    setSearching(true);
                  }}
                  onFocus={() => setSearching(true)}
                  placeholder="Search any place in the world"
                  placeholderTextColor="#8A8F98"
                  accessibilityLabel="Search a place"
                  maxFontSizeMultiplier={1.3}
                  style={[styles.searchInput, { color: c.text }]}
                  returnKeyType="search"
                />
                {query ? (
                  <Pressable
                    accessibilityLabel="Clear search"
                    hitSlop={10}
                    onPress={() => setQuery('')}>
                    <AppText muted>✕</AppText>
                  </Pressable>
                ) : null}
              </Card>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Directions"
                onPress={() => startRouting(null)}
                style={[styles.directions, { backgroundColor: c.primary }]}>
                <AppText variant="heading" color="#FFFFFF">
                  ⇄
                </AppText>
              </Pressable>
            </View>
            {searching && results.isFetching && !results.data?.length ? (
              <Card strong style={{ padding: space.md }}>
                <AppText muted>Searching…</AppText>
              </Card>
            ) : null}
            {searching && results.data?.length ? (
              <Card strong style={{ padding: space.sm, gap: 0 }}>
                {results.data.map((p, i) => (
                  <Pressable
                    key={`${i}:${p.lat},${p.lon}`}
                    accessibilityRole="button"
                    onPress={() => {
                      Keyboard.dismiss();
                      setSearching(false);
                      setQuery(p.label);
                      goTo({ lat: p.lat, lon: p.lon, label: p.label, detail: p.detail });
                    }}
                    style={({ pressed }) => [
                      styles.result,
                      pressed && { backgroundColor: c.field },
                    ]}>
                    <AppText numberOfLines={1}>{p.label}</AppText>
                    {p.detail ? (
                      <AppText variant="caption" muted numberOfLines={1}>
                        {p.detail}
                      </AppText>
                    ) : null}
                  </Pressable>
                ))}
              </Card>
            ) : null}
          </>
        )}
      </View>

      {/* bottom: locate button, legend or the chosen place */}
      <View style={[styles.bottom, { bottom: (tabBar || 90) + space.sm }]} pointerEvents="box-none">
        {selected || showCommute || routing ? null : (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Show my location"
            onPress={locateMe}
            style={[styles.locate, { backgroundColor: c.glassStrong, borderColor: c.glassBorder }]}>
            <AppText variant="heading">◎</AppText>
          </Pressable>
        )}
        {routing ? (
          from && to ? (
            <RouteSheet
              plan={plan.data}
              selected={selectedRoute}
              onSelect={setChosen}
              loading={plan.isFetching && !plan.data}
              error={plan.isError ? errorMessage(plan.error) : null}
            />
          ) : null
        ) : selected ? (
          <PlaceSheet
            place={selected}
            onClose={() => setSelected(null)}
            onDirections={() =>
              startRouting({ label: selected.label, lat: selected.lat, lon: selected.lon })
            }
          />
        ) : showCommute && commute.data ? (
          <CommuteSheet
            c={commute.data}
            leg={leg}
            onLeg={setLeg}
            onClose={() => setShowCommute(false)}
          />
        ) : (
          <>
            <View style={{ flexDirection: 'row', gap: space.sm, flexWrap: 'wrap' }}>
              {commute.data ? (
                <Button
                  title="Your commute"
                  kind="secondary"
                  compact
                  onPress={() => {
                    setShowCommute(true);
                    const { home: h, office: o } = commute.data;
                    camera.current?.fitBounds(
                      [
                        Math.min(h.lon, o.lon),
                        Math.min(h.lat, o.lat),
                        Math.max(h.lon, o.lon),
                        Math.max(h.lat, o.lat),
                      ],
                      { padding: { top: 130, bottom: 470, left: 60, right: 60 }, duration: 1000 },
                    );
                  }}
                />
              ) : null}
              <Button
                title="Change home & work"
                kind="secondary"
                compact
                onPress={() => router.push('/edit-profile')}
              />
            </View>
            <Card strong style={styles.legend}>
              <AppText variant="caption" muted>
                {SCALE_NAME[scale]} outside now · tap anywhere
              </AppText>
              <View style={{ flexDirection: 'row', gap: 4 }}>
                {aqiBands(scale).map((b) => (
                  <View key={b.label} style={{ flex: 1, gap: 2 }} accessibilityLabel={b.label}>
                    <View style={{ height: 6, borderRadius: 3, backgroundColor: b.color }} />
                    <AppText
                      variant="caption"
                      style={{ fontSize: 11, lineHeight: 14 }}
                      numberOfLines={1}>
                      {b.from}
                    </AppText>
                  </View>
                ))}
              </View>
              <AppText variant="caption" muted style={{ fontSize: 11, lineHeight: 14 }}>
                {aqiBands(scale)
                  .map((b) => b.label)
                  .join(' → ')}
              </AppText>
            </Card>
          </>
        )}
      </View>
    </View>
  );
}

/** The route as short segments, each coloured by the roadside PM2.5 at its two ends. */
function routeShape(c: CommuteOut, leg: Leg): GeoJSON.FeatureCollection {
  const pts = c[leg].points;
  const features: GeoJSON.Feature[] = [];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1];
    const b = pts[i];
    const vals = [a.pm25, b.pm25].filter((v): v is number => v !== null);
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [a.lon, a.lat],
          [b.lon, b.lat],
        ],
      },
      properties: { pm25: vals.length ? vals.reduce((x, y) => x + y, 0) / vals.length : 0 },
    });
  }
  return { type: 'FeatureCollection', features };
}

/** Today's recorded travel (opt-in) as lines; path points are [lat, lon]. */
function legsShape(legs: TravelLegOut[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: legs
      .filter((l) => l.path.length >= 2)
      .map((l) => ({
        type: 'Feature',
        geometry: { type: 'LineString', coordinates: l.path.map(([lat, lon]) => [lon, lat]) },
        properties: { mode: l.mode },
      })),
  };
}

function placesShape(c: CommuteOut): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [c.home.lon, c.home.lat] },
        properties: { name: 'Home' },
      },
      {
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [c.office.lon, c.office.lat] },
        properties: { name: 'Work' },
      },
    ],
  };
}

const styles = StyleSheet.create({
  top: { position: 'absolute', left: space.lg, right: space.lg, gap: space.sm },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.sm,
    paddingVertical: 4,
    paddingHorizontal: space.lg,
    borderRadius: radius.pill,
  },
  searchInput: { flex: 1, fontSize: 16, minHeight: 44, fontFamily: 'Inter_400Regular' },
  result: { paddingVertical: space.sm, paddingHorizontal: space.md, borderRadius: radius.sm },
  bottom: { position: 'absolute', left: space.lg, right: space.lg, gap: space.sm },
  locate: {
    alignSelf: 'flex-end',
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0px 6px 18px rgba(30, 40, 60, 0.15)',
  },
  legend: { padding: space.md, gap: space.xs },
  directions: {
    width: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    boxShadow: '0px 6px 18px rgba(30, 40, 60, 0.18)',
  },
});
