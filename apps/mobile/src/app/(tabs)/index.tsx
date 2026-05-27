import { Platform, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { BrandLogo } from '@/components/brand-logo';
import { useAuth } from '@/lib/auth/context';

// Placeholder home — replaced in later steps with the real dashboard.
// Currently used to verify the auth session is live.
export default function HomeScreen() {
  const { user, signOut } = useAuth();

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <View style={styles.inner}>
        <View style={styles.brandRow}>
          <BrandLogo size="md" />
        </View>

        <View style={styles.body}>
          <Text style={styles.eyebrow}>SIGNED IN AS</Text>
          <Text
            style={styles.email}
            accessibilityLabel={`Signed in as ${user?.email ?? 'unknown'}`}
          >
            {user?.email ?? '—'}
          </Text>

          <Text style={styles.heading} accessibilityRole="header">
            Welcome.
          </Text>
          <Text style={styles.bodyText}>
            The dashboard, bill upload, and analysis screens are coming next. For now
            this confirms the auth session is restored on every app launch.
          </Text>

          <Pressable
            onPress={signOut}
            accessibilityRole="button"
            accessibilityLabel="Sign out"
            style={({ pressed }) => [styles.button, pressed && styles.buttonPressed]}
          >
            <Text style={styles.buttonText}>Sign out</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F4F2EC' },
  inner: { flex: 1, paddingHorizontal: 24 },
  brandRow: {
    alignItems: 'center',
    paddingVertical: 16,
    marginBottom: 24,
  },
  body: {
    flex: 1,
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
  },
  eyebrow: {
    fontSize: 12,
    fontWeight: '700',
    color: '#9A9A8E',
    letterSpacing: 1.2,
    marginBottom: 6,
  },
  email: {
    fontSize: 16,
    color: '#1A1A14',
    marginBottom: 32,
  },
  heading: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontSize: 32,
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.6,
    marginBottom: 12,
  },
  bodyText: {
    fontSize: 15,
    color: '#5A5A50',
    lineHeight: 22,
    marginBottom: 32,
  },
  button: {
    backgroundColor: '#2D4A2A',
    borderRadius: 999,
    paddingVertical: 14,
    paddingHorizontal: 32,
    minHeight: 48,
    alignSelf: 'flex-start',
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonPressed: { opacity: 0.85 },
  buttonText: { color: '#ffffff', fontWeight: '700', fontSize: 15 },
});
