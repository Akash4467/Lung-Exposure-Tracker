/**
 * The air you're breathing, drawn behind the glass.
 *
 *   clean  → a pale sky with mint/lilac light, slow breeze streaks and a few bright motes
 *   polluted → the sky greys over, dark smoke rolls up from the bottom, soot drifts upward
 *
 * `pm25` (µg/m³) sets how far along that scale the screen is (WHO guideline 15 = clean,
 * ~180 = thickest smoke), and changes fade over a couple of seconds.
 *
 * Performance: one looping shared clock on the UI thread drives every element (each one a
 * transformed view around a static SVG), so nothing re-renders in React while it animates. It
 * stops when the screen isn't focused, and it is static when the phone asks for reduced motion.
 */
import { useIsFocused } from 'expo-router';
import { memo, useEffect } from 'react';
import { StyleSheet, useWindowDimensions, View } from 'react-native';
import Animated, {
  cancelAnimation,
  Easing,
  type SharedValue,
  useAnimatedStyle,
  useReducedMotion,
  useSharedValue,
  withRepeat,
  withTiming,
} from 'react-native-reanimated';
import Svg, { Circle, Defs, LinearGradient, Path, RadialGradient, Rect, Stop } from 'react-native-svg';

const LOOP_MS = 90_000; // one full cycle of the clock; every motion repeats a whole number of times
const TAU = Math.PI * 2;

/** 0 = clean air, 1 = heavy smoke. */
export function airIntensity(pm25: number): number {
  return Math.min(1, Math.max(0, (pm25 - 12) / (180 - 12)));
}

export type AirMood = number | 'breeze' | 'calm';

export function AirBackdrop({ air }: { air: AirMood }) {
  if (air === 'calm') return <Sky />;
  return <LivingAir intensity={air === 'breeze' ? 0 : airIntensity(air)} />;
}

/** The still version: sky plus soft pastel light. Used on forms and settings. */
const Sky = memo(function Sky() {
  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <SkyGradient id="clean" top="#E3F0F3" bottom="#F6F7F5" />
      <Aurora />
    </View>
  );
});

function LivingAir({ intensity }: { intensity: number }) {
  const focused = useIsFocused();
  const reduced = useReducedMotion();
  const clock = useSharedValue(0);
  const t = useSharedValue(intensity);

  useEffect(() => {
    t.value = withTiming(intensity, { duration: 2000, easing: Easing.inOut(Easing.quad) });
  }, [intensity, t]);

  useEffect(() => {
    if (!focused || reduced) {
      cancelAnimation(clock);
      return;
    }
    // Continue from wherever the clock stopped, then loop forever.
    const from = clock.value;
    clock.value = withTiming(1, { duration: (1 - from) * LOOP_MS, easing: Easing.linear }, (done) => {
      if (!done) return;
      clock.value = 0;
      clock.value = withRepeat(withTiming(1, { duration: LOOP_MS, easing: Easing.linear }), -1);
    });
    return () => cancelAnimation(clock);
  }, [focused, reduced, clock]);

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents="none">
      <SkyGradient id="clean" top="#E3F0F3" bottom="#F6F7F5" />
      <Fade t={t} from={0} to={1}>
        <SkyGradient id="smog" top="#D3CFC8" bottom="#958F87" />
      </Fade>
      <Fade t={t} from={1} to={0}>
        <Aurora />
      </Fade>
      <Haze t={t} />
      {BREEZE.map((b, i) => (
        <Streak key={i} spec={b} clock={clock} t={t} />
      ))}
      {SMOKE.map((s, i) => (
        <Smoke key={i} spec={s} clock={clock} t={t} />
      ))}
      {MOTES.map((m, i) => (
        <Mote key={i} spec={m} clock={clock} t={t} />
      ))}
    </View>
  );
}

// ---------------------------------------------------------------------------------- layers

function SkyGradient({ id, top, bottom }: { id: string; top: string; bottom: string }) {
  return (
    <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
      <Defs>
        <LinearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor={top} />
          <Stop offset="1" stopColor={bottom} />
        </LinearGradient>
      </Defs>
      <Rect width="100%" height="100%" fill={`url(#${id})`} />
    </Svg>
  );
}

/** Soft coloured light, like the pastel glows in the samples. */
function Aurora() {
  return (
    <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
      <Defs>
        <Glow id="mint" color="#BDEBD7" />
        <Glow id="lilac" color="#DCD5F7" />
        <Glow id="sky" color="#C6E3F6" />
      </Defs>
      <Circle cx="85%" cy="6%" r="55%" fill="url(#mint)" />
      <Circle cx="5%" cy="38%" r="50%" fill="url(#lilac)" />
      <Circle cx="90%" cy="78%" r="55%" fill="url(#sky)" />
    </Svg>
  );
}

function Glow({ id, color, opacity = 0.85 }: { id: string; color: string; opacity?: number }) {
  return (
    <RadialGradient id={id} cx="50%" cy="50%" r="50%">
      <Stop offset="0" stopColor={color} stopOpacity={opacity} />
      <Stop offset="1" stopColor={color} stopOpacity={0} />
    </RadialGradient>
  );
}

/** A warm yellow-brown haze that is strongest in the middle of the scale. */
function Haze({ t }: { t: SharedValue<number> }) {
  const style = useAnimatedStyle(() => ({ opacity: 4 * t.value * (1 - t.value) * 0.8 }));
  return (
    <Animated.View style={[StyleSheet.absoluteFill, style]}>
      <Svg width="100%" height="100%" style={StyleSheet.absoluteFill}>
        <Defs>
          <Glow id="haze" color="#E9CF9C" opacity={0.75} />
        </Defs>
        <Circle cx="50%" cy="55%" r="75%" fill="url(#haze)" />
      </Svg>
    </Animated.View>
  );
}

function Fade({
  t,
  from,
  to,
  children,
}: {
  t: SharedValue<number>;
  from: number;
  to: number;
  children: React.ReactNode;
}) {
  const style = useAnimatedStyle(() => ({ opacity: from + (to - from) * t.value }));
  return <Animated.View style={[StyleSheet.absoluteFill, style]}>{children}</Animated.View>;
}

// ---------------------------------------------------------------------------------- breeze

type StreakSpec = { y: number; speed: number; phase: number; len: number; amp: number; w: number };

const BREEZE: StreakSpec[] = [
  { y: 0.16, speed: 7, phase: 0.0, len: 0.9, amp: 14, w: 1.6 },
  { y: 0.3, speed: 5, phase: 0.45, len: 1.1, amp: 20, w: 2.2 },
  { y: 0.47, speed: 8, phase: 0.2, len: 0.8, amp: 12, w: 1.4 },
  { y: 0.62, speed: 6, phase: 0.7, len: 1.0, amp: 18, w: 2.0 },
  { y: 0.8, speed: 9, phase: 0.35, len: 0.7, amp: 10, w: 1.3 },
];

/** A thin wavy line of moving air that glides across the screen. */
function Streak({
  spec,
  clock,
  t,
}: {
  spec: StreakSpec;
  clock: SharedValue<number>;
  t: SharedValue<number>;
}) {
  const { width, height } = useWindowDimensions();
  const len = width * spec.len;
  const style = useAnimatedStyle(() => {
    const p = (clock.value * spec.speed + spec.phase) % 1;
    const x = -len + p * (width + len);
    const y = Math.sin(TAU * (clock.value * spec.speed * 2 + spec.phase)) * 6;
    // fade in and out at the edges so the wrap-around is never visible
    const edge = Math.min(1, p * 6, (1 - p) * 6);
    return { opacity: (1 - t.value) * 0.9 * edge, transform: [{ translateX: x }, { translateY: y }] };
  });
  const h = spec.amp * 2 + 8;
  const d = wave(len, spec.amp, h / 2);
  return (
    <Animated.View
      style={[{ position: 'absolute', top: height * spec.y - h / 2, left: 0, width: len, height: h }, style]}>
      <Svg width={len} height={h}>
        <Defs>
          <LinearGradient id="streak" x1="0" y1="0" x2="1" y2="0">
            <Stop offset="0" stopColor="#7CC7AE" stopOpacity={0} />
            <Stop offset="0.5" stopColor="#5DB596" stopOpacity={0.55} />
            <Stop offset="1" stopColor="#FFFFFF" stopOpacity={0} />
          </LinearGradient>
        </Defs>
        <Path d={d} stroke="url(#streak)" strokeWidth={spec.w} strokeLinecap="round" fill="none" />
        <Path
          d={wave(len * 0.7, spec.amp * 0.6, h / 2 + 5, len * 0.2)}
          stroke="url(#streak)"
          strokeWidth={spec.w * 0.6}
          strokeLinecap="round"
          fill="none"
        />
      </Svg>
    </Animated.View>
  );
}

function wave(len: number, amp: number, mid: number, x0 = 0): string {
  const q = len / 4;
  return (
    `M ${x0} ${mid} C ${x0 + q} ${mid - amp}, ${x0 + q} ${mid - amp}, ${x0 + 2 * q} ${mid} ` +
    `S ${x0 + 3 * q} ${mid + amp}, ${x0 + 4 * q} ${mid}`
  );
}

// ---------------------------------------------------------------------------------- smoke

type SmokeSpec = { x: number; size: number; rise: number; drift: number; phase: number; dark: number };

const SMOKE: SmokeSpec[] = [
  { x: -0.25, size: 1.1, rise: 1, drift: 2, phase: 0.0, dark: 0.5 },
  { x: 0.35, size: 1.3, rise: 2, drift: 1, phase: 0.3, dark: 0.45 },
  { x: 0.75, size: 1.0, rise: 1, drift: 3, phase: 0.6, dark: 0.55 },
  { x: 0.1, size: 0.9, rise: 3, drift: 2, phase: 0.15, dark: 0.4 },
  { x: 0.55, size: 1.2, rise: 2, drift: 2, phase: 0.8, dark: 0.5 },
  { x: -0.05, size: 1.4, rise: 1, drift: 1, phase: 0.5, dark: 0.35 },
];

/** A big soft dark cloud that billows up from the bottom and sinks back. */
function Smoke({
  spec,
  clock,
  t,
}: {
  spec: SmokeSpec;
  clock: SharedValue<number>;
  t: SharedValue<number>;
}) {
  const { width, height } = useWindowDimensions();
  const size = width * spec.size;
  const style = useAnimatedStyle(() => {
    const a = TAU * (clock.value * spec.rise + spec.phase);
    const b = TAU * (clock.value * spec.drift + spec.phase * 0.7);
    // thicker smoke reaches higher up the screen
    const reach = height * (0.18 + 0.32 * t.value);
    const y = -reach * (0.5 + 0.5 * Math.sin(a));
    const x = Math.sin(b) * width * 0.12;
    const s = 1 + 0.18 * Math.sin(a + 1.3);
    return {
      opacity: Math.min(1, t.value * 1.4) * (0.65 + 0.35 * Math.sin(b + 2)),
      transform: [{ translateX: x }, { translateY: y }, { scale: s }],
    };
  });
  const id = `smoke${spec.phase}`;
  return (
    <Animated.View
      renderToHardwareTextureAndroid
      style={[
        {
          position: 'absolute',
          left: width * spec.x,
          top: height - size * 0.45,
          width: size,
          height: size,
        },
        style,
      ]}>
      <Svg width={size} height={size}>
        <Defs>
          <RadialGradient id={id} cx="50%" cy="50%" r="50%">
            <Stop offset="0" stopColor="#3B3733" stopOpacity={spec.dark} />
            <Stop offset="0.55" stopColor="#4A4540" stopOpacity={spec.dark * 0.55} />
            <Stop offset="1" stopColor="#5A544E" stopOpacity={0} />
          </RadialGradient>
        </Defs>
        <Circle cx={size / 2} cy={size / 2} r={size / 2} fill={`url(#${id})`} />
      </Svg>
    </Animated.View>
  );
}

// ---------------------------------------------------------------------------------- motes

type MoteSpec = { x: number; y: number; vx: number; vy: number; r: number; min: number };

/** `min` is the intensity at which a mote appears: a few in clean air, many in smoke. */
const MOTES: MoteSpec[] = Array.from({ length: 28 }, (_, i) => {
  const h = (n: number) => ((Math.sin(i * 12.9898 + n * 78.233) * 43758.5453) % 1 + 1) % 1;
  return {
    x: h(1),
    y: h(2),
    vx: 1 + Math.floor(h(3) * 3),
    vy: 1 + Math.floor(h(4) * 3),
    r: 1.2 + h(5) * 2.2,
    min: i < 6 ? 0 : (i - 6) / 22,
  };
});

/** Bright drifting motes in clean air; dark soot rising through smoke. */
function Mote({
  spec,
  clock,
  t,
}: {
  spec: MoteSpec;
  clock: SharedValue<number>;
  t: SharedValue<number>;
}) {
  const { width, height } = useWindowDimensions();
  const style = useAnimatedStyle(() => {
    const k = t.value;
    const px = (spec.x + clock.value * spec.vx * 3) % 1; // sideways with the breeze
    const py = (spec.y + clock.value * spec.vy * 4) % 1; // upward with the smoke
    const x = px * (width + 20) - 10;
    const yClean = spec.y * height + Math.sin(TAU * (clock.value * spec.vy * 4 + spec.x)) * 18;
    const ySmoke = height - py * (height + 20);
    const shown = k >= spec.min ? Math.min(1, (k - spec.min) * 8 + (spec.min === 0 ? 1 : 0)) : 0;
    const edge = Math.min(1, px * 10, (1 - px) * 10);
    return {
      opacity: shown * edge * (0.55 + 0.35 * k),
      backgroundColor: k < 0.3 ? 'rgba(255,255,255,0.95)' : 'rgba(58,54,50,0.8)',
      transform: [{ translateX: x }, { translateY: yClean + (ySmoke - yClean) * k }],
    };
  });
  return (
    <Animated.View
      style={[
        { position: 'absolute', left: 0, top: 0, width: spec.r * 2, height: spec.r * 2, borderRadius: spec.r },
        style,
      ]}
    />
  );
}
