import { useMutation } from '@tanstack/react-query';
import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AppText, Button, ErrorBanner, Screen, TextField } from '@/components/ui';
import { authApi } from '@/lib/api/endpoints';
import { errorMessage } from '@/lib/query';
import { space } from '@/theme';

export default function ForgotPassword() {
  const [step, setStep] = useState<'email' | 'code' | 'done'>('email');
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');

  const send = useMutation({
    mutationFn: () => authApi.forgot(email.trim()),
    onSuccess: () => setStep('code'),
  });
  const reset = useMutation({
    mutationFn: () => authApi.reset(email.trim(), code.trim(), password),
    onSuccess: () => setStep('done'),
  });

  if (step === 'done') {
    return (
      <Screen air="breeze">
        <AppText variant="title">Password changed</AppText>
        <AppText muted>You've been signed out everywhere. Sign in with your new password.</AppText>
        <Button title="Back to sign in" onPress={() => router.back()} />
      </Screen>
    );
  }

  return (
    <Screen air="breeze">
      <View style={{ gap: space.sm }}>
        <AppText variant="title">Reset your password</AppText>
        <AppText muted>
          {step === 'email'
            ? "Enter your email and we'll send a 6-digit code."
            : `If ${email.trim()} has an account, a code is on its way. It expires in 15 minutes.`}
        </AppText>
      </View>
      <ErrorBanner message={errorMessage(send.error ?? reset.error)} />

      {step === 'email' ? (
        <>
          <TextField
            label="Email"
            value={email}
            onChangeText={setEmail}
            autoCapitalize="none"
        autoCorrect={false}
        spellCheck={false}
            keyboardType="email-address"
            autoComplete="email"
          />
          <Button title="Send code" onPress={() => send.mutate()} loading={send.isPending} disabled={!email} />
        </>
      ) : (
        <>
          <TextField
            label="6-digit code"
            value={code}
            onChangeText={(t) => setCode(t.replace(/\D/g, '').slice(0, 6))}
            keyboardType="number-pad"
            autoComplete="one-time-code"
            textContentType="oneTimeCode"
          />
          <TextField
            label="New password"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
            hint="At least 8 characters"
          />
          <Button
            title="Set new password"
            onPress={() => reset.mutate()}
            loading={reset.isPending}
            disabled={code.length !== 6 || password.length < 8}
          />
          <Button title="Send a new code" kind="ghost" onPress={() => send.mutate()} />
        </>
      )}
    </Screen>
  );
}
