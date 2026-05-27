import { NativeTabs } from 'expo-router/unstable-native-tabs';
import { useColorScheme } from 'react-native';

import { Colors } from '@/constants/theme';

// iOS 26 Liquid Glass tab bar. Keep the system glass material intact —
// only override the active tint so brand sage flows through. SF Symbols
// give us Apple's pixel-perfect native icon set.
export default function AppTabs() {
  const scheme = useColorScheme();
  const colors = Colors[scheme === 'unspecified' ? 'light' : scheme];

  return (
    <NativeTabs tintColor={colors.accent}>
      <NativeTabs.Trigger name="index">
        <NativeTabs.Trigger.Label>Home</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="house" />
      </NativeTabs.Trigger>

      <NativeTabs.Trigger name="upload">
        <NativeTabs.Trigger.Label>Upload</NativeTabs.Trigger.Label>
        <NativeTabs.Trigger.Icon sf="square.and.arrow.up" />
      </NativeTabs.Trigger>
    </NativeTabs>
  );
}
