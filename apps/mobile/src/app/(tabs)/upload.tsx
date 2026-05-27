import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BrandLogo } from '@/components/brand-logo';

// Scaffold — Step 4a. Picker wiring + permissions + native bindings land in 4b.
export default function UploadScreen() {
  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.inner}>
        <View style={styles.brandRow}>
          <BrandLogo size="md" />
        </View>

        <View style={styles.body}>
          <Text style={styles.heading} accessibilityRole="header">
            Upload a bill
          </Text>
          <Text style={styles.bodyText}>
            Take a photo, choose an image from your library, or pick a PDF.
            We recommend uploading the itemized version of your bill so we
            can check every line.
          </Text>

          <View style={styles.actions}>
            <ActionButton label="Take a photo" hint="Opens the camera" disabled />
            <ActionButton label="Choose from library" hint="Opens your photo library" disabled />
            <ActionButton label="Pick a PDF" hint="Opens the file picker" disabled />
          </View>

          <Text style={styles.note}>
            Pickers will be wired in checkpoint 4b. Today's build verifies the tab,
            navigation, and permission strings are in place.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

function ActionButton({
  label,
  hint,
  disabled,
  onPress,
}: {
  label: string;
  hint: string;
  disabled?: boolean;
  onPress?: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled }}
      style={({ pressed }) => [
        styles.actionBtn,
        pressed && styles.actionBtnPressed,
        disabled && styles.actionBtnDisabled,
      ]}
    >
      <Text style={[styles.actionBtnText, disabled && styles.actionBtnTextDisabled]}>
        {label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F4F2EC' },
  inner: { flex: 1, paddingHorizontal: 24 },
  brandRow: { alignItems: 'center', paddingVertical: 16, marginBottom: 24 },
  body: { flex: 1, width: '100%', maxWidth: 420, alignSelf: 'center' },
  heading: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontSize: 32,
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.6,
    marginBottom: 12,
  },
  bodyText: { fontSize: 15, color: '#5A5A50', lineHeight: 22, marginBottom: 24 },
  actions: { gap: 12, marginBottom: 24 },
  actionBtn: {
    backgroundColor: '#2D4A2A',
    borderRadius: 999,
    paddingVertical: 16,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionBtnPressed: { opacity: 0.85 },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText: { color: '#ffffff', fontWeight: '700', fontSize: 16 },
  actionBtnTextDisabled: { color: '#E2DDD4' },
  note: { fontSize: 12, color: '#9A9A8E', lineHeight: 18, fontStyle: 'italic' },
});
