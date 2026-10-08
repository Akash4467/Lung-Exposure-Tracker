import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Redirect } from 'expo-router';
import { View } from 'react-native';

import { Progress } from '@/components/controls';
import { IndoorEditor } from '@/components/indoor-editor';
import { AppText, Button, ErrorBanner, Screen } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import { errorMessage, keys } from '@/lib/query';
import { missingStep, toProfileIn, useDraft } from '@/store/onboarding';
import { space } from '@/theme';

export default function DetailsStep() {
  const d = useDraft();
  const qc = useQueryClient();
  const save = useMutation({
    mutationFn: (withDetails: boolean) => {
      const draft = withDetails ? d : { ...d, size: null, purifier: false, cadr: '', sources: [] };
      return meApi.saveProfile(toProfileIn(draft));
    },
    onSuccess: async (profile) => {
      qc.setQueryData(keys.profile, profile);
      // "onboarded" flips to true and the area gate moves the user into the app. Clear the
      // draft only after that, or this step would bounce back to step 1 for a moment.
      await qc.invalidateQueries({ queryKey: keys.me });
      d.reset();
    },
  });

  const back = missingStep(d, 'details');
  if (back) return <Redirect href={back} />;

  return (
    <Screen
      footer={
        <>
          <Button title="Finish" onPress={() => save.mutate(true)} loading={save.isPending && save.variables} />
          <Button
            title="Skip for now"
            kind="ghost"
            onPress={() => save.mutate(false)}
            disabled={save.isPending}
          />
        </>
      }>
      <Progress step={4} of={4} />
      <View style={{ gap: space.sm }}>
        <AppText variant="title">At home (optional)</AppText>
        <AppText muted>
          Each detail makes your estimate more personal and narrows its range. Skip anything
          you're unsure about; you can add it later in Settings.
        </AppText>
      </View>
      <ErrorBanner message={errorMessage(save.error)} />
      <IndoorEditor
        value={{ size: d.size, windows: d.windows, purifier: d.purifier, cadr: d.cadr, sources: d.sources }}
        update={(fn) =>
          useDraft.setState((s) =>
            fn({ size: s.size, windows: s.windows, purifier: s.purifier, cadr: s.cadr, sources: s.sources }),
          )
        }
      />
    </Screen>
  );
}
