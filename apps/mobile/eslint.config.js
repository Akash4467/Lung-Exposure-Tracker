// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'android/*', 'ios/*'],
  },
  {
    rules: {
      // An HTML rule: apostrophes in React Native <Text> are just text.
      'react/no-unescaped-entities': 'off',
    },
  },
]);
