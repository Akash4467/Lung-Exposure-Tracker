import { useMutation } from '@tanstack/react-query';
import { Link } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { GoogleButton } from '@/components/google-button';
import { AppText, Button, Disclaimer, ErrorBanner, Overline, Screen, TextField } from '@/components/ui';
import { authApi } from '@/lib/api/endpoints';
import { useSession } from '@/lib/auth/session';
import { errorMessage } from '@/lib/query';
import { emailError } from '@/lib/validate';
import { space, useColors } from '@/theme';

export default function SignIn() {
  const c = useColors();
  const { signIn } = useSession();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const login = useMutation({
    mutationFn: () => authApi.login(email.trim(), password),
    onSuccess: signIn,
  });

  return (
    <Screen air="breeze">
      <View style={{ gap: space.sm, marginTop: space.xxl, marginBottom: space.xl }}>
        <Overline>Lung Exposure Tracker</Overline>
        <AppText variant="display">Know the air{'\n'}you breathe.</AppText>
        <AppText muted>See what your lungs took in today, and what to change tomorrow.</AppText>
      </View>

      <ErrorBanner message={errorMessage(login.error)} />
      <TextField
        label="Email"
        value={email}
        onChangeText={setEmail}
        autoCapitalize="none"
        autoCorrect={false}
        spellCheck={false}
        autoComplete="email"
        keyboardType="email-address"
        textContentType="emailAddress"
        error={emailError(email)}
      />
      <TextField
        label="Password"
        value={password}
        onChangeText={setPassword}
        secureTextEntry
        autoComplete="current-password"
        textContentType="password"
        onSubmitEditing={() => login.mutate()}
      />
      <Button
        title="Sign in"
        onPress={() => login.mutate()}
        loading={login.isPending}
        disabled={!email || !password || !!emailError(email)}
      />
      <Link href="/forgot-password" style={{ color: c.text, textDecorationLine: 'underline', textAlign: 'center', fontFamily: 'Inter_500Medium' }}>
        Forgot password?
      </Link>

      <View style={{ flexDirection: 'row', alignItems: 'center', gap: space.md }}>
        <View style={{ flex: 1, height: 1, backgroundColor: c.border }} />
        <AppText variant="caption" muted>
          or
        </AppText>
        <View style={{ flex: 1, height: 1, backgroundColor: c.border }} />
      </View>
      <GoogleButton />

      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: space.xs }}>
        <AppText muted>New here?</AppText>
        <Link href="/sign-up" style={{ color: c.text, textDecorationLine: 'underline', fontFamily: 'Inter_600SemiBold' }}>
          Create an account
        </Link>
      </View>
      <Disclaimer />
    </Screen>
  );
}
