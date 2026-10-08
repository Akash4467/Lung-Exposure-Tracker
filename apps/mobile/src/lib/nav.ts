import { type Href, router } from 'expo-router';

/** Back if there's somewhere to go back to (e.g. opened from Settings), otherwise to
 * `fallback` (e.g. the screen was opened from a link or restored after a restart). */
export function goBack(fallback: Href = '/settings') {
  if (router.canGoBack()) router.back();
  else router.replace(fallback);
}
