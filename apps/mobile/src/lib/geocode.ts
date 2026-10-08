/**
 * Place search and "what's here?" through our own API (/v1/geo): OpenStreetMap data via
 * Nominatim, with Photon as the fallback. The server caches answers (repeat searches are
 * instant) and keeps to Nominatim's one-request-a-second rule for everyone.
 * Privacy: the typed text and, for reverse lookups, the coordinates go to our server, which
 * passes them on to the OpenStreetMap services.
 */
import * as Location from 'expo-location';

import { api } from '@/lib/api/client';

export interface Place {
  label: string;
  detail: string;
  lat: number;
  lon: number;
}

/** Results near `near` come first (e.g. the person's home), but the whole world is searched. */
export async function searchPlaces(
  query: string,
  signal?: AbortSignal,
  near?: { lat: number; lon: number },
): Promise<Place[]> {
  const q = query.trim();
  if (q.length < 3) return [];
  const params = new URLSearchParams({ q });
  if (near) {
    params.set('lat', near.lat.toFixed(3));
    params.set('lon', near.lon.toFixed(3));
  }
  const out = await api<{ places: Place[] }>(`/v1/geo/search?${params.toString()}`, { signal });
  return out.places;
}

/** The name of the place at a point (a map tap, "my location"), or null if none is found. */
export async function reverse(lat: number, lon: number): Promise<Place | null> {
  try {
    const out = await api<{ place: Place | null }>(
      `/v1/geo/reverse?lat=${lat.toFixed(5)}&lon=${lon.toFixed(5)}`,
    );
    return out.place ? { ...out.place, lat, lon } : null;
  } catch {
    return null;
  }
}

export class LocationDenied extends Error {}

/** The phone's current position, with a readable label when one can be found. */
export async function currentPlace(): Promise<Place> {
  const perm = await Location.requestForegroundPermissionsAsync();
  if (!perm.granted) throw new LocationDenied('Location permission was not given.');
  const pos = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
  const { latitude: lat, longitude: lon } = pos.coords;
  const named = await reverse(lat, lon);
  return (
    named ?? { label: 'Current location', detail: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon }
  );
}

/** Just the phone's coordinates (no name lookup): fast, for starting a route. */
export async function currentPosition(): Promise<{ lat: number; lon: number }> {
  const perm = await Location.requestForegroundPermissionsAsync();
  if (!perm.granted) throw new LocationDenied('Location permission was not given.');
  const last = await Location.getLastKnownPositionAsync({ maxAge: 5 * 60_000 });
  const pos =
    last ?? (await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }));
  return { lat: pos.coords.latitude, lon: pos.coords.longitude };
}
