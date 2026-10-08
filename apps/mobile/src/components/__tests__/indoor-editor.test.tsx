/// <reference types="jest" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { useState } from 'react';

import { IndoorEditor, type IndoorValue } from '../indoor-editor';

jest.mock('@/lib/api/endpoints', () => ({
  metaApi: {
    catalog: jest.fn(async () => ({
      indoor_sources: [
        { kind: 'cooking_lpg', tip: null },
        { kind: 'mosquito_coil', tip: null },
        { kind: 'brand_new_kind', tip: null }, // added on the server, unknown to the app
      ],
      home_sizes: ['1bhk', '2bhk'],
    })),
  },
}));

function Harness({ onValue }: { onValue: (v: IndoorValue) => void }) {
  const [v, setV] = useState<IndoorValue>({
    size: null,
    windows: 'normal',
    purifier: false,
    cadr: '',
    sources: [],
  });
  onValue(v);
  return <IndoorEditor value={v} update={(fn) => setV((cur) => ({ ...cur, ...fn(cur) }))} />;
}

async function setup() {
  let latest: IndoorValue | null = null;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  await render(
    <QueryClientProvider client={qc}>
      <Harness onValue={(v) => (latest = v)} />
    </QueryClientProvider>,
  );
  return () => latest!;
}

test('two quick taps add both sources (no stale overwrite)', async () => {
  const value = await setup();
  const lpg = await screen.findByLabelText('Add Cooking on gas (LPG)');
  const coil = screen.getByLabelText('Add Mosquito coil');
  await act(async () => {
    fireEvent.press(lpg);
    fireEvent.press(coil); // same tick, before a re-render
  });
  expect(value().sources.map((s) => s.kind)).toEqual(['cooking_lpg', 'mosquito_coil']);
  expect(value().sources[1]).toMatchObject({ start: '22:00', minutes: 480 });
});

test('a kind the app has never heard of still gets a readable name', async () => {
  await setup();
  expect(await screen.findByLabelText('Add Brand new kind')).toBeTruthy();
});

test('the same source cannot be added twice', async () => {
  const value = await setup();
  const lpg = await screen.findByLabelText('Add Cooking on gas (LPG)');
  await act(async () => {
    fireEvent.press(lpg);
    fireEvent.press(lpg);
  });
  expect(value().sources).toHaveLength(1);
});
