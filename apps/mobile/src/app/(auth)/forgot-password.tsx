import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Link } from 'expo-router';

import { BrandLogo } from '@/components/brand-logo';
import { useAuth } from '@/lib/auth/context';

export default function ForgotPasswordScreen() {
  const { resetPasswordForEmail } = useAuth();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit() {
    if (!email) {
      setError('Enter your email.');
      return;
    }
    setError(null);
    setInfo(null);
    setIsSubmitting(true);
    const { error: resetError } = await resetPasswordForEmail(email.trim());
    setIsSubmitting(false);
    if (resetError) {
      setError(resetError);
      return;
    }
    setInfo('Check your inbox for a reset link.');
  }

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'left', 'right']}>
      <StatusBar barStyle="dark-content" />
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.brandRow}>
            <BrandLogo size="md" />
          </View>

          <View style={styles.formCard}>
            <Text style={styles.heading} accessibilityRole="header">
              Reset your password
            </Text>
            <Text style={styles.subhead}>
              We'll email you a link to set a new one.
            </Text>

            <View style={styles.field}>
              <Text style={styles.label} nativeID="reset-email-label">Email</Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                onSubmitEditing={handleSubmit}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                keyboardType="email-address"
                textContentType="emailAddress"
                returnKeyType="go"
                placeholder="you@example.com"
                placeholderTextColor="#9A9A8E"
                style={styles.input}
                accessibilityLabel="Email"
                accessibilityLabelledBy="reset-email-label"
              />
            </View>

            {error ? (
              <Text style={styles.error} accessibilityLiveRegion="polite" accessibilityRole="alert">
                {error}
              </Text>
            ) : null}
            {info ? (
              <Text style={styles.info} accessibilityLiveRegion="polite">
                {info}
              </Text>
            ) : null}

            <Pressable
              onPress={handleSubmit}
              disabled={isSubmitting}
              accessibilityRole="button"
              accessibilityLabel="Send reset link"
              accessibilityState={{ disabled: isSubmitting, busy: isSubmitting }}
              style={({ pressed }) => [
                styles.button,
                pressed && styles.buttonPressed,
                isSubmitting && styles.buttonDisabled,
              ]}
            >
              {isSubmitting ? (
                <ActivityIndicator color="#ffffff" />
              ) : (
                <Text style={styles.buttonText}>Send reset link</Text>
              )}
            </Pressable>

            <View style={styles.footer}>
              <Link
                href="/login"
                style={styles.footerLink}
                accessibilityRole="link"
                accessibilityLabel="Back to sign in"
              >
                Back to sign in
              </Link>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#F4F2EC' },
  flex: { flex: 1 },
  scrollContent: { flexGrow: 1, paddingHorizontal: 24, paddingVertical: 24, justifyContent: 'center' },
  brandRow: { alignItems: 'center', marginBottom: 40 },
  formCard: { width: '100%', maxWidth: 420, alignSelf: 'center' },
  heading: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontSize: 30,
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.5,
    marginBottom: 6,
    textAlign: 'center',
  },
  subhead: { fontSize: 16, color: '#5A5A50', textAlign: 'center', marginBottom: 32 },
  field: { marginBottom: 16 },
  label: {
    fontSize: 12,
    fontWeight: '700',
    color: '#9A9A8E',
    letterSpacing: 1.2,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  input: {
    backgroundColor: '#ffffff',
    borderRadius: 12,
    paddingHorizontal: 16,
    paddingVertical: 14,
    fontSize: 16,
    color: '#1A1A14',
    borderWidth: 1,
    borderColor: '#E2DDD4',
    minHeight: 48,
  },
  error: { color: '#B23A2A', fontSize: 14, marginTop: 4, marginBottom: 8, textAlign: 'center' },
  info: { color: '#2D4A2A', fontSize: 14, marginTop: 4, marginBottom: 8, textAlign: 'center' },
  button: {
    marginTop: 12,
    backgroundColor: '#2D4A2A',
    borderRadius: 999,
    paddingVertical: 16,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
  },
  buttonPressed: { opacity: 0.85 },
  buttonDisabled: { opacity: 0.6 },
  buttonText: { color: '#ffffff', fontWeight: '700', fontSize: 16 },
  footer: { alignItems: 'center', marginTop: 24 },
  footerLink: { color: '#2D4A2A', fontSize: 14, fontWeight: '700' },
});
