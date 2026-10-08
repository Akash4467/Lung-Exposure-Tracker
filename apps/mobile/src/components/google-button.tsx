/**
 * "Continue with Google": Android's native Google account picker → a Google ID token → our
 * API (POST /v1/auth/google), which checks the token's signature, audience and issuer and
 * signs the person in (or creates their account). The token's audience is the Web client ID,
 * so that is what the phone is configured with (EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID).
 */
import { useMutation } from '@tanstack/react-query';
import { Platform } from 'react-native';

import { Button, ErrorBanner } from '@/components/ui';
import { authApi } from '@/lib/api/endpoints';
import { useSession } from '@/lib/auth/session';
import { errorMessage } from '@/lib/query';

const WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID;

type GoogleModule = typeof import('@react-native-google-signin/google-signin');
let configured = false;

async function google(): Promise<GoogleModule | null> {
  if (Platform.OS === 'web' || !WEB_CLIENT_ID) return null;
  try {
    const m = await import('@react-native-google-signin/google-signin');
    if (!configured) {
      m.GoogleSignin.configure({ webClientId: WEB_CLIENT_ID });
      configured = true;
    }
    return m;
  } catch {
    return null; // a build without the native module
  }
}

class Cancelled extends Error {}

/** The Google ID token for an account the person picks, or throws Cancelled. */
async function pickAccount(): Promise<string> {
  const m = await google();
  if (!m) throw new Error('Google sign-in is not available in this build.');
  const { GoogleSignin, isSuccessResponse, isErrorWithCode, statusCodes } = m;
  try {
    await GoogleSignin.hasPlayServices({ showPlayServicesUpdateDialog: true });
    await GoogleSignin.signOut().catch(() => undefined); // always offer the account picker
    const res = await GoogleSignin.signIn();
    if (!isSuccessResponse(res)) throw new Cancelled();
    if (!res.data.idToken) throw new Error('Google did not return a sign-in token.');
    return res.data.idToken;
  } catch (e) {
    if (e instanceof Cancelled) throw e;
    if (isErrorWithCode(e)) {
      if (e.code === statusCodes.SIGN_IN_CANCELLED || e.code === statusCodes.IN_PROGRESS) {
        throw new Cancelled();
      }
      if (e.code === statusCodes.PLAY_SERVICES_NOT_AVAILABLE) {
        throw new Error('Google Play services are needed for Google sign-in on this phone.');
      }
    }
    throw new Error('Google sign-in failed. Please try again or use email instead.');
  }
}

export function GoogleButton() {
  const { signIn } = useSession();
  const go = useMutation({
    mutationFn: async () => authApi.google(await pickAccount()),
    onSuccess: signIn,
  });
  if (!WEB_CLIENT_ID || Platform.OS === 'web') {
    return (
      <Button title="Google sign-in (not set up)" kind="secondary" disabled onPress={() => {}} />
    );
  }
  const err = go.error instanceof Cancelled ? null : go.error;
  return (
    <>
      <ErrorBanner message={errorMessage(err)} />
      <Button
        title="Continue with Google"
        kind="secondary"
        onPress={() => go.mutate()}
        loading={go.isPending}
      />
    </>
  );
}
