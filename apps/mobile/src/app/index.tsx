import { Redirect } from 'expo-router';

import { HOME, useArea } from '@/lib/auth/gate';

/** "/" sends everyone to the start of the area they belong in. */
export default function Index() {
  const area = useArea();
  if (!area) return null; // the root layout keeps the splash up meanwhile
  return <Redirect href={HOME[area]} />;
}
