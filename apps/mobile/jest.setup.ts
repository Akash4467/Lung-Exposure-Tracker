// The animated air behind each screen is purely visual and needs Reanimated's native runtime,
// which Jest doesn't have. Tests render the screens without it.
jest.mock('@/components/air-backdrop', () => ({
  AirBackdrop: () => null,
  airIntensity: (pm25: number) => Math.min(1, Math.max(0, (pm25 - 12) / 168)),
}));

// AsyncStorage's native module doesn't exist under Jest; use the library's own in-memory mock.
jest.mock('@react-native-async-storage/async-storage', () =>
  require('@react-native-async-storage/async-storage/jest/async-storage-mock'),
);
