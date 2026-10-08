import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, ErrorBanner, Screen, TextField } from '@/components/ui';
import { ApiError } from '@/lib/api/client';
import { authApi } from '@/lib/api/endpoints';
import { useSession } from '@/lib/auth/session';
import { errorMessage } from '@/lib/query';
import { emailError } from '@/lib/validate';
import { space } from '@/theme';

const MIN = 8;

export default function SignUp() {
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const register = useMutation({
    mutationFn: () => authApi.register(email.trim(), password),
    onSuccess: signIn, // onboarding opens next; the email code can be entered any time
  });

  const short = password.length > 0 && password.length < MIN;
  const mismatch = confirm.length > 0 && confirm !== password;
  const emailErr =
    register.error instanceof ApiError && register.error.code === 'email_taken'
      ? 'An account with this email already exists. Sign in instead.'
      : null;

  return (
    <Screen air="breeze">
      <View style={{ gap: space.sm }}>
        <AppText variant="title">Create your account</AppText>
        <AppText muted>We'll email you a 6-digit code to confirm your address.</AppText>
      </View>
      <ErrorBanner message={emailErr ? null : errorMessage(register.error)} />
      <TextField
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        spellCheck={false}
        autoComplete="email"
        keyboardType="email-address"
        error={emailErr ?? emailError(email)}
      />
      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="new-password"
        textContentType="newPassword"
        error={short ? `At least ${MIN} characters` : null}
        hint={`At least ${MIN} characters. A short phrase is easy to remember.`}
      />
      <TextField
        label="Confirm password"
        value={confirm}
        onChangeText={setConfirm}
        secureTextEntry
        autoComplete="new-password"
        error={mismatch ? "Passwords don't match" : null}
      />
      <Button
        title="Create account"
        onPress={() => register.mutate()}
        loading={register.isPending}
        disabled={!email || !!emailError(email) || password.length < MIN || confirm !== password}
      />
      <AppText variant="caption" muted>
        We store only what the estimate needs: your age, sex, two places and your usual
        schedule. You can delete everything in Settings at any time.
      </AppText>
    </Screen>
  );
}
