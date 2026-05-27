import { useRef, useState } from 'react';
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
import { Link, useRouter } from 'expo-router';

import { BrandLogo } from '@/components/brand-logo';
import { useAuth } from '@/lib/auth/context';

export default function LoginScreen() {
  const { signInWithPassword } = useAuth();
  const router = useRouter();
  const passwordRef = useRef<TextInput>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit() {
    if (!email || !password) {
      setError('Enter your email and password.');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    const { error: signInError } = await signInWithPassword(email.trim(), password);
    setIsSubmitting(false);
    if (signInError) setError(signInError);
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
            <Text
              style={styles.heading}
              accessibilityRole="header"
            >
              Welcome back
            </Text>
            <Text style={styles.subhead}>Sign in to continue.</Text>

            <View style={styles.field}>
              <Text style={styles.label} nativeID="email-label">Email</Text>
              <TextInput
                value={email}
                onChangeText={setEmail}
                onSubmitEditing={() => passwordRef.current?.focus()}
                autoCapitalize="none"
                autoCorrect={false}
                autoComplete="email"
                keyboardType="email-address"
                textContentType="emailAddress"
                returnKeyType="next"
                placeholder="you@example.com"
                placeholderTextColor="#9A9A8E"
                style={styles.input}
                accessibilityLabel="Email"
                accessibilityLabelledBy="email-label"
              />
            </View>

            <View style={styles.field}>
              <View style={styles.labelRow}>
                <Text style={styles.label} nativeID="password-label">Password</Text>
                <Link
                  href="/forgot-password"
                  style={styles.inlineLink}
                  accessibilityRole="link"
                  accessibilityLabel="Forgot password?"
                >
                  Forgot?
                </Link>
              </View>
              <TextInput
                ref={passwordRef}
                value={password}
                onChangeText={setPassword}
                onSubmitEditing={handleSubmit}
                secureTextEntry
                autoCapitalize="none"
                autoComplete="current-password"
                textContentType="password"
                returnKeyType="go"
                placeholder="Your password"
                placeholderTextColor="#9A9A8E"
                style={styles.input}
                accessibilityLabel="Password"
                accessibilityLabelledBy="password-label"
              />
            </View>

            {error ? (
              <Text
                style={styles.error}
                accessibilityLiveRegion="polite"
                accessibilityRole="alert"
              >
                {error}
              </Text>
            ) : null}

            <Pressable
              onPress={handleSubmit}
              disabled={isSubmitting}
              accessibilityRole="button"
              accessibilityLabel="Sign in"
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
                <Text style={styles.buttonText}>Sign in</Text>
              )}
            </Pressable>

            <View style={styles.dividerRow}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <Pressable
              onPress={() => router.push('/magic-link')}
              accessibilityRole="button"
              accessibilityLabel="Email me a sign-in code instead"
              style={({ pressed }) => [
                styles.secondaryButton,
                pressed && styles.buttonPressed,
              ]}
            >
              <Text style={styles.secondaryButtonText}>Email me a code instead</Text>
            </Pressable>

            <View style={styles.footer}>
              <Text style={styles.footerText}>New to ClaroBill?</Text>
              <Link
                href="/signup"
                style={styles.footerLink}
                accessibilityRole="link"
                accessibilityLabel="Create an account"
              >
                Create an account
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
  scrollContent: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingVertical: 24,
    justifyContent: 'center',
  },
  brandRow: {
    alignItems: 'center',
    marginBottom: 40,
  },
  formCard: {
    width: '100%',
    maxWidth: 420,
    alignSelf: 'center',
  },
  heading: {
    fontFamily: Platform.select({ ios: 'Georgia', android: 'serif' }),
    fontSize: 32,
    fontWeight: '700',
    color: '#1A1A14',
    letterSpacing: -0.6,
    marginBottom: 6,
    textAlign: 'center',
  },
  subhead: {
    fontSize: 16,
    color: '#5A5A50',
    textAlign: 'center',
    marginBottom: 32,
  },
  field: { marginBottom: 16 },
  labelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  label: {
    fontSize: 12,
    fontWeight: '700',
    color: '#9A9A8E',
    letterSpacing: 1.2,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  inlineLink: {
    fontSize: 12,
    fontWeight: '700',
    color: '#2D4A2A',
    letterSpacing: 0.5,
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
  error: {
    color: '#B23A2A',
    fontSize: 14,
    marginTop: 4,
    marginBottom: 8,
    textAlign: 'center',
  },
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
  dividerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: 20,
    marginBottom: 16,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: '#E2DDD4' },
  dividerText: {
    marginHorizontal: 12,
    color: '#9A9A8E',
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 1,
    textTransform: 'uppercase',
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    borderRadius: 999,
    paddingVertical: 14,
    minHeight: 52,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5,
    borderColor: '#2D4A2A',
  },
  secondaryButtonText: { color: '#2D4A2A', fontWeight: '700', fontSize: 15 },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 6,
    marginTop: 24,
  },
  footerText: { color: '#5A5A50', fontSize: 14 },
  footerLink: { color: '#2D4A2A', fontSize: 14, fontWeight: '700' },
});
