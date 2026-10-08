import { Redirect } from 'expo-router';
import type { PropsWithChildren } from 'react';

import { type Area, useArea } from '@/lib/auth/gate';

/**
 * Wraps a route group's layout. If the user doesn't belong in this area (signed out, not
 * onboarded yet, ...), it sends them to "/", which picks the right place. Each group checks
 * itself, so a sign-in or sign-out never leaves a screen visible in the wrong area.
 */
export function AreaGate({ area, children }: PropsWithChildren<{ area: Area }>) {
  const current = useArea();
  if (current === null) return null;
  if (current !== area) return <Redirect href="/" />;
  return children;
}
