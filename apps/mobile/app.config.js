// Extends app.json. Firebase's google-services.json (needed for push on Android) is added to
// the build only when the file exists, so the app builds and runs without it; push simply
// stays off until it's there. The file is git-ignored: download it from the Firebase console
// (Project settings > Your apps > Android com.lungexposure.tracker) into apps/mobile/.
const fs = require('fs');
const path = require('path');

module.exports = ({ config }) => {
  const googleServices = path.join(__dirname, 'google-services.json');
  const plugins = [...(config.plugins ?? [])];
  if (!plugins.some((p) => (Array.isArray(p) ? p[0] : p) === 'expo-notifications')) {
    plugins.push(['expo-notifications', { color: '#1F6F54', defaultChannel: 'alerts' }]);
  }
  return {
    ...config,
    plugins,
    android: {
      ...config.android,
      ...(fs.existsSync(googleServices) ? { googleServicesFile: './google-services.json' } : {}),
    },
  };
};
