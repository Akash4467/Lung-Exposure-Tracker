import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { AppText, Button, ErrorBanner, Screen, TextField } from '@/components/ui';
import { authApi } from '@/lib/api/endpoints';
import { goBack } from '@/lib/nav';
import { errorMessage, keys } from '@/lib/query';
import { useColors } from '@/theme';

export default function VerifyEmail() {
  const c = useColors();
  const qc = useQueryClient();
  const [code, setCode] = useState('');
  const verify = useMutation({
    mutationFn: () => authApi.verifyEmail(code),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: keys.me });
      goBack('/today');
    },
  });
  const resend = useMutation({ mutationFn: authApi.resendCode });

  return (
    <Screen edges={['bottom']}>
      <AppText muted>Enter the 6-digit code we emailed you. It expires after 15 minutes.</AppText>
      <ErrorBanner message={errorMessage(verify.error ?? resend.error)} />
      <TextField
        label="Code"
        value={code}
        onChangeText={(t) => setCode(t.replace(/\D/g, '').slice(0, 6))}
        keyboardType="number-pad"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        autoFocus
      />
      <Button title="Confirm" onPress={() => verify.mutate()} disabled={code.length !== 6} loading={verify.isPending} />
      <Button title="Send a new code" kind="ghost" onPress={() => resend.mutate()} loading={resend.isPending} />
      {resend.isSuccess ? <AppText color={c.accent}>A new code is on its way.</AppText> : null}
    </Screen>
  );
}
