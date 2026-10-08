/**
 * The floating glass tab bar: a pill that hovers above the bottom edge (not edge to edge),
 * frosted white over the air backdrop, with a soft highlight that slides to the chosen tab.
 * Screens get the space it covers from TabBarSpace, so their last content can scroll clear.
 */
import type { Tabs } from 'expo-router';
import { type ComponentProps, useEffect, useState } from 'react';
import { Pressable, StyleSheet, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Defs, LinearGradient, Rect, Stop } from 'react-native-svg';

import { TabIcon, type TabIconName } from '@/components/tab-icons';
import { AppText } from '@/components/ui';
import { useColors } from '@/theme';

type TabBarProps = Parameters<NonNullable<ComponentProps<typeof Tabs>['tabBar']>>[0];

const BAR_HEIGHT = 66;
const SIDE = 16;
const LIFT = 10; // gap between the pill and the bottom of the safe area


export function useTabBarSpace(): number {
  const insets = useSafeAreaInsets();
  return BAR_HEIGHT + LIFT + insets.bottom + 12;
}

export function GlassTabBar({ state, descriptors, navigation }: TabBarProps) {
  const c = useColors();
  const insets = useSafeAreaInsets();
  const [width, setWidth] = useState(0);
  const count = state.routes.length;
  const slot = width / Math.max(count, 1);
  const x = useSharedValue(0);

  useEffect(() => {
    x.value = withSpring(state.index * slot, { damping: 18, stiffness: 180, mass: 0.8 });
  }, [state.index, slot, x]);

  const highlight = useAnimatedStyle(() => ({ transform: [{ translateX: x.value }] }));

  return (
    <View
      pointerEvents="box-none"
      style={[styles.wrap, { bottom: insets.bottom + LIFT, left: SIDE, right: SIDE }]}>
      <View
        style={[styles.pill, { borderColor: c.glassBorder, backgroundColor: 'rgba(248,249,251,0.94)' }]}
        accessibilityRole="tablist"
        onLayout={(e) => setWidth(e.nativeEvent.layout.width)}>
        {/* glass: translucent white plus a sheen that is brighter at the top edge */}
        <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
          <Defs>
            <LinearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor="#FFFFFF" stopOpacity={0.98} />
              <Stop offset="0.5" stopColor="#FFFFFF" stopOpacity={0.9} />
              <Stop offset="1" stopColor="#F2F4F7" stopOpacity={0.93} />
            </LinearGradient>
          </Defs>
          <Rect width="100%" height="100%" rx={BAR_HEIGHT / 2} fill="url(#sheen)" />
        </Svg>

        {width > 0 ? (
          <Animated.View style={[styles.highlightSlot, { width: slot }, highlight]}>
            <View style={styles.highlight} />
          </Animated.View>
        ) : null}

        {state.routes.map((route, i) => {
          const focused = state.index === i;
          const label = descriptors[route.key].options.title ?? route.name;
          const color = focused ? c.text : c.textMuted;
          return (
            <Pressable
              key={route.key}
              accessibilityRole="tab"
              accessibilityState={{ selected: focused }}
              accessibilityLabel={label}
              style={styles.item}
              onPress={() => {
                const ev = navigation.emit({
                  type: 'tabPress',
                  target: route.key,
                  canPreventDefault: true,
                });
                if (!focused && !ev.defaultPrevented) navigation.navigate(route.name, route.params);
              }}
              onLongPress={() => navigation.emit({ type: 'tabLongPress', target: route.key })}>
              <TabIcon name={route.name as TabIconName} color={color} size={23} />
              <AppText
                variant="caption"
                numberOfLines={1}
                maxFontSizeMultiplier={1.1}
                style={{ fontSize: 11, lineHeight: 14, fontWeight: focused ? '600' : '500' }}
                color={color}>
                {label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { position: 'absolute', alignItems: 'center' },
  pill: {
    width: '100%',
    maxWidth: 520,
    height: BAR_HEIGHT,
    borderRadius: BAR_HEIGHT / 2,
    borderWidth: 1,
    flexDirection: 'row',
    overflow: 'hidden',
    boxShadow: '0px 10px 28px rgba(30, 40, 60, 0.16)',
  },
  highlightSlot: { position: 'absolute', top: 0, bottom: 0, left: 0, padding: 6 },
  highlight: { flex: 1, borderRadius: 999, backgroundColor: 'rgba(18,20,23,0.09)' },
  item: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
});
