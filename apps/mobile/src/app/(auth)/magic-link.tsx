import { useEffect, useRef, useState } from 'react';
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

// "Email me a code" flow. Sends a 6-digit OTP to the user's email and verifies
// it in-app — no deep linking required. Cleaner UX than magic links on mobile
// because the user stays inside the app.
// Matches Supabase's per-email OTP rate limit so we don't tempt the user
// into a tap that immediately errors with "email rate limit exceeded".
const RESEND_COOLDOWN_SECONDS = 30;
// Matches the OTP length configured in Supabase Dashboard → Authentication
// → Sign in / Providers → Email → OTP Length. Bump this if the dashboard
// setting changes.
const OTP_LENGTH = 8;

export default function MagicLinkScreen() {
  const { sendEmailOtp, verifyEmailOtp } = useAuth();
  const codeRef = useRef<TextInput>(null);
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isResending, setIsResending] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  // Countdown for the resend button. Decrements once per second while > 0.
  useEffect(() => {
    if (cooldown <= 0) return;
    const id = setInterval(() => setCooldown((s) => (s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(id);
  }, [cooldown]);

  async function handleSendCode() {
    if (!email) {
      setError('Enter your email.');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    const { error: otpError } = await sendEmailOtp(email.trim());
    setIsSubmitting(false);
    if (otpError) {
      setError(otpError);
      return;
    }
    setInfo('Code sent. Check your email.');
    setStep('code');
    setCooldown(RESEND_COOLDOWN_SECONDS);
    setTimeout(() => codeRef.current?.focus(), 100);
  }

  async function handleResend() {
    if (cooldown > 0 || isResending) return;
    setError(null);
    setInfo(null);
    setIsResending(true);
    const { error: otpError } = await sendEmailOtp(email.trim());
    setIsResending(false);
    if (otpError) {
      setError(otpError);
      return;
    }
    setInfo('New code sent. Check your email.');
    setCooldown(RESEND_COOLDOWN_SECONDS);
  }

  async function handleVerify() {
    if (code.length < OTP_LENGTH) {
      setError(`Enter the ${OTP_LENGTH}-digit code.`);
      return;
    }
    setError(null);
    setIsSubmitting(true);
    const { error: verifyError } = await verifyEmailOtp(email.trim(), code.trim());
    setIsSubmitting(false);
    if (verifyError) setError(verifyError);
    // success: auth state listener handles the redirect
  }

  function handleCodeChange(next: string) {
    // Clear stale info/error as the user types — the previous "Code sent"
    // banner shouldn't sit next to a fresh validation message.
    if (error) setError(null);
    if (info) setInfo(null);
    setCode(next);
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
              {step === 'email' ? 'Sign in with email' : 'Enter your code'}
            </Text>
            <Text style={styles.subhead}>
              {step === 'email'
                ? "We'll email you a 6-digit code."
                : `Code sent to ${email}.`}
            </Text>

            {step === 'email' ? (
              <View style={styles.field}>
                <Text style={styles.label} nativeID="otp-email-label">Email</Text>
                <TextInput
                  value={email}
                  onChangeText={setEmail}
                  onSubmitEditing={handleSendCode}
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
                  accessibilityLabelledBy="otp-email-label"
                />
              </View>
            ) : (
              <View style={styles.field}>
                <Text style={styles.label} nativeID="otp-code-label">{OTP_LENGTH}-digit code</Text>
                <TextInput
                  ref={codeRef}
                  value={code}
                  onChangeText={handleCodeChange}
                  onSubmitEditing={handleVerify}
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="number-pad"
                  textContentType="oneTimeCode"
                  maxLength={OTP_LENGTH}
                  returnKeyType="go"
                  placeholder={'0'.repeat(OTP_LENGTH)}
                  placeholderTextColor="#9A9A8E"
                  style={[styles.input, styles.codeInput]}
                  accessibilityLabel={`${OTP_LENGTH}-digit verification code`}
                  accessibilityLabelledBy="otp-code-label"
                />
              </View>
            )}

            {error ? (
              <Text style={styles.error} accessibilityLiveRegion="polite" accessibilityRole="alert">
                {error}
              </Text>
            ) : null}
            {info && step === 'code' ? (
              <Text style={styles.info} accessibilityLiveRegion="polite">
                {info}
              </Text>
            ) : null}

            <Pressable
              onPress={step === 'email' ? handleSendCode : handleVerify}
              disabled={isSubmitting}
              accessibilityRole="button"
              accessibilityLabel={step === 'email' ? 'Send code' : 'Verify code'}
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
                <Text style={styles.buttonText}>
                  {step === 'email' ? 'Send code' : 'Verify code'}
                </Text>
              )}
            </Pressable>

            {step === 'code' ? (
              <>
                <Pressable
                  onPress={handleResend}
                  disabled={cooldown > 0 || isResending}
                  accessibilityRole="button"
                  accessibilityLabel={
                    cooldown > 0
                      ? `Resend code in ${cooldown} seconds`
                      : 'Resend code'
                  }
                  accessibilityState={{
                    disabled: cooldown > 0 || isResending,
                    busy: isResending,
                  }}
                  style={styles.linkBtn}
                >
                  {isResending ? (
                    <ActivityIndicator color="#2D4A2A" />
                  ) : (
                    <Text
                      style={[
                        styles.linkBtnText,
                        cooldown > 0 && styles.linkBtnTextDisabled,
                      ]}
                    >
                      {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
                    </Text>
                  )}
                </Pressable>

                <Pressable
                  onPress={() => {
                    setStep('email');
                    setCode('');
                    setError(null);
                    setInfo(null);
                    setCooldown(0);
                  }}
                  accessibilityRole="button"
                  accessibilityLabel="Use a different email"
                  style={styles.linkBtn}
                >
                  <Text style={styles.linkBtnText}>Use a different email</Text>
                </Pressable>
              </>
            ) : null}

            <View style={styles.footer}>
              <Link
                href="/login"
                style={styles.footerLink}
                accessibilityRole="link"
                accessibilityLabel="Sign in with password instead"
              >
                Sign in with password instead
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
  codeInput: { fontSize: 22, letterSpacing: 6, textAlign: 'center', fontVariant: ['tabular-nums'] },
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
  linkBtn: { alignItems: 'center', paddingVertical: 14, minHeight: 44 },
  linkBtnText: { color: '#2D4A2A', fontSize: 14, fontWeight: '700' },
  linkBtnTextDisabled: { color: '#9A9A8E' },
  footer: { alignItems: 'center', marginTop: 8 },
  footerLink: { color: '#5A5A50', fontSize: 14, fontWeight: '700' },
});
