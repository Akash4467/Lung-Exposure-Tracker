import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

import { IndoorEditor, type IndoorValue } from '@/components/indoor-editor';
import { QueryState } from '@/components/query-state';
import { Button, ErrorBanner, Screen } from '@/components/ui';
import { meApi } from '@/lib/api/endpoints';
import type { ProfileOut } from '@/lib/api/types';
import { goBack } from '@/lib/nav';
import { errorMessage, keys } from '@/lib/query';

export default function Indoor() {
  const profile = useQuery({ queryKey: keys.profile, queryFn: meApi.profile });
  return (
    <Screen edges={['bottom']}>
      <QueryState query={profile}>{(p) => <Form p={p} />}</QueryState>
    </Screen>
  );
}

function Form({ p }: { p: ProfileOut }) {
  const qc = useQueryClient();
  const h = p.places.home;
  const [v, setV] = useState<IndoorValue>({
    size: h.size,
    windows: h.windows,
    purifier: h.purifier,
    cadr: h.purifier_cadr_m3h ? String(h.purifier_cadr_m3h) : '',
    sources: h.sources,
  });
  const save = useMutation({
    mutationFn: () =>
      meApi.saveIndoor({
        place: 'home',
        windows: v.windows,
        purifier: v.purifier,
        ...(v.purifier && v.cadr ? { purifier_cadr_m3h: Number(v.cadr) } : { clear_cadr: true }),
        ...(v.size ? { size: v.size } : {}),
        sources: v.sources,
      }),
    onSuccess: async () => {
      // The server recomputed straight away; refresh everything that depends on it.
      await Promise.all([
        qc.invalidateQueries({ queryKey: keys.profile }),
        qc.invalidateQueries({ queryKey: ['score'] }),
        qc.invalidateQueries({ queryKey: ['simulate'] }),
      ]);
      goBack('/settings');
    },
  });
  return (
    <>
      <ErrorBanner message={errorMessage(save.error)} />
      <IndoorEditor value={v} update={(fn) => setV((cur) => ({ ...cur, ...fn(cur) }))} />
      <Button title="Save" onPress={() => save.mutate()} loading={save.isPending} />
    </>
  );
}
