/** Small, consistent building blocks used by every screen ("glass and air" style). */
import { type PropsWithChildren, type ReactNode, useContext, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  RefreshControl,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  type TextProps,
  TextInput,
  type TextInputProps,
  View,
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AirBackdrop, type AirMood } from '@/components/air-backdrop';
import { TabBarSpace } from '@/lib/tab-bar-space';
import { DISPLAY_VARIANTS, fontFor, radius, space, type, useColors } from '@/theme';

type Variant = keyof typeof type;

export function AppText({
  variant = 'body',
  muted,
  color,
  style,
  ...rest
}: TextProps & { variant?: Variant; muted?: boolean; color?: string }) {
  const c = useColors();
  const weight = StyleSheet.flatten(style)?.fontWeight ?? type[variant].fontWeight;
  return (
    <Text
      // Follow the phone's text size, but cap it so layouts still hold together.
      maxFontSizeMultiplier={variant === 'hero' || variant === 'display' ? 1.1 : 1.4}
      {...rest}
      style={[
        type[variant],
        { color: color ?? (muted ? c.textMuted : c.text) },
        style,
        { fontFamily: fontFor(weight, DISPLAY_VARIANTS.has(variant)), fontWeight: 'normal' },
      ]}
    />
  );
}

/**
 * A full screen: the air behind (`air`: a PM2.5 value for the living sky, 'breeze', or the
 * still 'calm' sky), safe area, scrolling, keyboard-aware, 16 px gutters.
 */
export function Screen({
  children,
  scroll = true,
  footer,
  refreshing,
  onRefresh,
  edges = ['top', 'bottom'],
  air = 'calm',
}: PropsWithChildren<{
  scroll?: boolean;
  footer?: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  edges?: ('top' | 'bottom')[];
  air?: AirMood;
}>) {
  const c = useColors();
  const tabBar = useContext(TabBarSpace); // > 0 inside the tabs: room for the floating bar
  const bottomRoom = tabBar ? { paddingBottom: tabBar } : null;
  const body = scroll ? (
    <ScrollView
      contentContainerStyle={[styles.screenContent, bottomRoom]}
      keyboardShouldPersistTaps="handled"
      refreshControl={
        onRefresh ? (
          <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={c.text} />
        ) : undefined
      }>
      {children}
    </ScrollView>
  ) : (
    <View style={[styles.screenContent, { flex: 1 }, bottomRoom]}>{children}</View>
  );
  return (
    <View style={{ flex: 1, backgroundColor: c.background }}>
      <AirBackdrop air={air} />
      <SafeAreaView style={{ flex: 1 }} edges={edges}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior="padding">
          {body}
          {footer ? <View style={styles.footer}>{footer}</View> : null}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </View>
  );
}

/** Frosted glass panel. `strong` is more opaque, for dense text over thick smoke. */
export function Card({
  children,
  style,
  strong,
}: PropsWithChildren<{ style?: ViewStyle; strong?: boolean }>) {
  const c = useColors();
  return (
    <View
      style={[
        styles.card,
        {
          backgroundColor: strong ? c.glassStrong : c.glass,
          borderColor: c.glassBorder,
        },
        style,
      ]}>
      {children}
    </View>
  );
}

/** Small uppercase label above a group, like "WHAT'S NEXT" in the samples. */
export function Overline({ children }: PropsWithChildren) {
  const parts = Array.isArray(children) ? children : [children];
  const text = parts.every((p) => typeof p === 'string' || typeof p === 'number');
  return (
    <AppText variant="overline" muted>
      {text ? parts.join('').toUpperCase() : children}
    </AppText>
  );
}

type ButtonKind = 'primary' | 'secondary' | 'ghost' | 'danger';

/** Pill buttons: solid near-black (primary), outlined glass (secondary), text (ghost). */
export function Button({
  title,
  onPress,
  kind = 'primary',
  loading,
  disabled,
  accessibilityHint,
  compact,
}: {
  title: string;
  onPress: () => void;
  kind?: ButtonKind;
  loading?: boolean;
  disabled?: boolean;
  accessibilityHint?: string;
  compact?: boolean;
}) {
  const c = useColors();
  const off = disabled || loading;
  const bg = {
    primary: off ? '#C9CBD0' : c.primary,
    secondary: c.glassStrong,
    ghost: 'transparent',
    danger: c.dangerSurface,
  }[kind];
  const fg = { primary: c.primaryText, secondary: c.text, ghost: c.text, danger: c.danger }[kind];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!off, busy: !!loading }}
      accessibilityHint={accessibilityHint}
      onPress={onPress}
      disabled={off}
      style={({ pressed }) => [
        styles.button,
        compact && styles.buttonCompact,
        {
          backgroundColor: bg,
          borderColor: kind === 'secondary' ? c.text : 'transparent',
          opacity: off && kind !== 'primary' ? 0.5 : pressed ? 0.82 : 1,
          transform: [{ scale: pressed ? 0.98 : 1 }],
        },
      ]}>
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <AppText
          variant="label"
          color={fg}
          style={[{ fontSize: compact ? 14 : 16 }, kind === 'ghost' && styles.underline]}>
          {title}
        </AppText>
      )}
    </Pressable>
  );
}

/** Soft grey field with its label inside, above the value (as in the samples). */
export function TextField({
  label,
  error,
  hint,
  ...input
}: TextInputProps & { label: string; error?: string | null; hint?: string }) {
  const c = useColors();
  const [focused, setFocused] = useState(false);
  return (
    <View style={{ gap: space.xs }}>
      <View
        style={[
          styles.field,
          {
            backgroundColor: c.field,
            borderColor: error ? c.danger : focused ? c.text : 'transparent',
          },
        ]}>
        <AppText variant="caption" muted>
          {label}
        </AppText>
        <TextInput
          placeholderTextColor="#9A9EA6"
          {...input}
          onFocus={(e) => {
            setFocused(true);
            input.onFocus?.(e);
          }}
          onBlur={(e) => {
            setFocused(false);
            input.onBlur?.(e);
          }}
          accessibilityLabel={label}
          maxFontSizeMultiplier={1.4}
          style={[styles.input, { color: c.text }]}
        />
      </View>
      {error ? (
        <AppText variant="caption" color={c.danger}>
          {error}
        </AppText>
      ) : hint ? (
        <AppText variant="caption" muted>
          {hint}
        </AppText>
      ) : null}
    </View>
  );
}

/** One-of-N choice as glass pills; the chosen one is outlined in black. */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label?: string;
  options: readonly { value: T; label: string }[];
  value: T | null | undefined;
  onChange: (v: T) => void;
}) {
  const c = useColors();
  return (
    <View style={{ gap: space.sm }}>
      {label ? <AppText variant="label">{label}</AppText> : null}
      <View style={styles.chips} accessibilityRole="radiogroup">
        {options.map((o) => {
          const on = o.value === value;
          return (
            <Pressable
              key={o.value}
              accessibilityRole="radio"
              accessibilityState={{ selected: on }}
              onPress={() => onChange(o.value)}
              style={[
                styles.chip,
                {
                  backgroundColor: on ? c.glassStrong : c.glass,
                  borderColor: on ? c.text : c.glassBorder,
                  borderWidth: on ? 1.5 : 1,
                },
              ]}>
              <AppText variant="label" style={{ fontWeight: on ? '600' : '500' }}>
                {o.label}
              </AppText>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

export function ErrorBanner({ message }: { message?: string | null }) {
  const c = useColors();
  if (!message) return null;
  return (
    <View accessibilityRole="alert" style={[styles.banner, { backgroundColor: c.dangerSurface }]}>
      <AppText variant="body" color={c.danger}>
        {message}
      </AppText>
    </View>
  );
}

export function Disclaimer() {
  return (
    <AppText variant="caption" muted style={{ textAlign: 'center' }}>
      Estimated exposure. Informational only, not medical advice.
    </AppText>
  );
}

export function Loading({ label }: { label?: string }) {
  const c = useColors();
  return (
    <View style={styles.center}>
      <ActivityIndicator color={c.text} size="large" />
      {label ? <AppText muted>{label}</AppText> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screenContent: { padding: space.lg, gap: space.lg, flexGrow: 1, paddingBottom: space.xxl },
  footer: { paddingHorizontal: space.lg, paddingBottom: space.lg, gap: space.sm },
  card: {
    borderRadius: radius.lg,
    borderWidth: 1,
    padding: space.lg,
    gap: space.md,
    boxShadow: '0px 8px 24px rgba(30, 40, 60, 0.08)',
  },
  button: {
    minHeight: 52,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.xl,
  },
  buttonCompact: { minHeight: 40, paddingHorizontal: space.lg },
  underline: { textDecorationLine: 'underline' },
  field: {
    minHeight: 58,
    borderRadius: radius.md,
    borderWidth: 1.5,
    paddingHorizontal: space.md,
    paddingTop: space.sm,
    paddingBottom: 2,
  },
  input: { fontSize: 16, paddingVertical: 4, minHeight: 30, fontFamily: 'Inter_400Regular' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  chip: {
    minHeight: 42,
    paddingHorizontal: space.lg,
    borderRadius: radius.pill,
    justifyContent: 'center',
  },
  banner: { borderRadius: radius.md, padding: space.md },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: space.md },
});
