import { useQuery } from '@tanstack/react-query';

import { authApi } from '@/lib/api/endpoints';
import { useSession } from '@/lib/auth/session';
import { keys } from '@/lib/query';

export type Area = 'auth' | 'onboarding' | 'app';

/** Which area the user belongs in right now, or null while that's still being worked out. */
export function useArea(): Area | null {
  const { status } = useSession();
  const me = useQuery({ queryKey: keys.me, queryFn: authApi.me, enabled: status === 'signedIn' });
  if (status === 'loading') return null;
  if (status === 'signedOut') return 'auth';
  if (!me.data) return null;
  return me.data.onboarded ? 'app' : 'onboarding';
}

export const HOME: Record<Area, '/sign-in' | '/profile' | '/today'> = {
  auth: '/sign-in',
  onboarding: '/profile',
  app: '/today',
};
