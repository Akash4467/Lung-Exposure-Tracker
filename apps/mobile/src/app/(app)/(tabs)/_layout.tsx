import { Tabs } from 'expo-router';

import { GlassTabBar, useTabBarSpace } from '@/components/glass-tab-bar';
import { TabBarSpace } from '@/lib/tab-bar-space';

/**
 * Five tabs under a floating glass pill (components/glass-tab-bar.tsx). The same on Android,
 * iOS and web. The bar floats over the screens, so the air backdrop shows around it; screens
 * pad their bottom by TabBarSpace so nothing ends up hidden behind it.
 */
export default function TabsLayout() {
  const space = useTabBarSpace();
  return (
    <TabBarSpace.Provider value={space}>
      <Tabs
        tabBar={(props) => <GlassTabBar {...props} />}
        screenOptions={{ headerShown: false, sceneStyle: { backgroundColor: 'transparent' } }}>
        <Tabs.Screen name="today" options={{ title: 'Today' }} />
        <Tabs.Screen name="tomorrow" options={{ title: 'Tomorrow' }} />
        <Tabs.Screen name="map" options={{ title: 'Map' }} />
        <Tabs.Screen name="trends" options={{ title: 'Trends' }} />
        <Tabs.Screen name="settings" options={{ title: 'Settings' }} />
      </Tabs>
    </TabBarSpace.Provider>
  );
}
