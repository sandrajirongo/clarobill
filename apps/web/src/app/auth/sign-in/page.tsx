'use client';

// Auth pages depend on runtime env vars and the user's session — never pre-render
export const dynamic = 'force-dynamic';

import { useState } from 'react';
import type { FormEvent } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { CheckIcon } from '@/components/icons';
import s from './sign-in.module.css';

type Mode = 'magic-link' | 'password';
type PasswordSubMode = 'signin' | 'signup' | 'forgot';
type Msg = { type: 'success' | 'error'; text: string };

// ─── Password strength ────────────────────────────────────────────────────────

type StrengthLevel = 'too-short' | 'weak' | 'fair' | 'good' | 'strong';
interface PasswordStrength { score: 0 | 1 | 2 | 3 | 4; level: StrengthLevel; label: string }

function getPasswordStrength(pw: string): PasswordStrength {
  if (pw.length === 0) return { score: 0, level: 'too-short', label: '' };
  if (pw.length < 8)   return { score: 0, level: 'too-short', label: 'Too short' };
  const hasNumber  = /\d/.test(pw);
  const hasSpecial = /[^a-zA-Z0-9]/.test(pw);
  const isLong     = pw.length >= 12;
  if (isLong && hasNumber && hasSpecial) return { score: 4, level: 'strong', label: 'Strong' };
  if (hasNumber && hasSpecial)           return { score: 3, level: 'good',   label: 'Good' };
  if (hasNumber || hasSpecial)           return { score: 2, level: 'fair',   label: 'Fair' };
  return                                        { score: 1, level: 'weak',   label: 'Weak' };
}

const STRENGTH_COLOR: Record<StrengthLevel, string> = {
  'too-short': 'var(--border)',
  weak:        '#ef4444',
  fair:        '#f59e0b',
  good:        'var(--accent-dark, #84cc16)',
  strong:      'var(--sage)',
};

export default function SignInPage(): JSX.Element {
  const [mode, setMode] = useState<Mode>('magic-link');

  return (
    <main className={s.root}>
      <div className={s.card}>
        <div className={s.logoRow}>
          <div className={s.logoMark}>C</div>
          <span className={s.logoText}>Claro<em style={{ fontStyle: 'italic' }}>Bill</em></span>
        </div>

        <h1 className={s.heading}>Sign in to Claro<em style={{ fontStyle: 'italic' }}>Bill</em></h1>
        <p className={s.sub}>Catch errors on your medical bills in minutes.</p>

        <div className={s.tabs} role="tablist">
          <button
            role="tab"
            aria-selected={mode === 'magic-link'}
            className={`${s.tab}${mode === 'magic-link' ? ` ${s.tabActive}` : ''}`}
            onClick={() => setMode('magic-link')}
          >
            Magic link
          </button>
          <button
            role="tab"
            aria-selected={mode === 'password'}
            className={`${s.tab}${mode === 'password' ? ` ${s.tabActive}` : ''}`}
            onClick={() => setMode('password')}
          >
            Email &amp; password
          </button>
        </div>

        {mode === 'magic-link' ? <MagicLinkForm /> : <PasswordForm />}

        <div className={s.benefits}>
          <div className={s.benefitItem}>
            <span className={s.benefitIcon}><CheckIcon size={14} /></span>
            <span>Finds billing errors — duplicate charges, unbundled codes, inflated fees</span>
          </div>
          <div className={s.benefitItem}>
            <span className={s.benefitIcon}><CheckIcon size={14} /></span>
            <span>Compares your charges against Medicare benchmarks in 30 seconds</span>
          </div>
          <div className={s.benefitItem}>
            <span className={s.benefitIcon}><CheckIcon size={14} /></span>
            <span>Generates a ready-to-send dispute letter with every report</span>
          </div>
        </div>
      </div>

      <p className={s.note}>
        Protected by 256-bit AES encryption. Your data is never sold or shared.
      </p>
    </main>
  );
}

// ─── Magic link form ──────────────────────────────────────────────────────────

function MagicLinkForm(): JSX.Element {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<Msg | null>(null);

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setIsLoading(true);
    setMessage(null);
    const { error } = await createSupabaseBrowserClient().auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    setIsLoading(false);
    if (error) {
      setMessage({ type: 'error', text: 'Failed to send magic link. Please try again.' });
    } else {
      setMessage({
        type: 'success',
        text: 'Check your email — a sign-in link is on its way. Some providers (including Proton Mail) may block these links. If it does not arrive, use the Email & password tab instead.',
      });
    }
  }

  return (
    <form onSubmit={handleSubmit} className={s.form}>
      <div>
        <label htmlFor="ml-email" className={s.label}>Email address</label>
        <input
          id="ml-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className={s.input}
        />
      </div>
      {message && (
        <p role="alert" className={message.type === 'success' ? s.msgSuccess : s.msgError}>
          {message.text}
        </p>
      )}
      <button type="submit" disabled={isLoading} className={s.btn}>
        {isLoading ? 'Sending…' : 'Send magic link'}
      </button>
    </form>
  );
}

// ─── Email + password form ────────────────────────────────────────────────────

function PasswordForm(): JSX.Element {
  const [subMode, setSubMode] = useState<PasswordSubMode>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<Msg | null>(null);

  function switchTo(next: PasswordSubMode): void {
    setSubMode(next);
    setMessage(null);
    setPassword('');
    setConfirmPassword('');
  }

  async function handleSignIn(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setIsLoading(true);
    setMessage(null);
    const { error } = await createSupabaseBrowserClient().auth.signInWithPassword({ email, password });
    setIsLoading(false);
    if (error) {
      setMessage({ type: 'error', text: 'Incorrect email or password.' });
    } else {
      window.location.href = '/dashboard';
    }
  }

  async function handleSignUp(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    if (password.length < 8) {
      setMessage({ type: 'error', text: 'Password must be at least 8 characters.' });
      return;
    }
    if (password !== confirmPassword) {
      setMessage({ type: 'error', text: 'Passwords do not match.' });
      return;
    }
    setIsLoading(true);
    setMessage(null);
    const { data, error } = await createSupabaseBrowserClient().auth.signUp({
      email,
      password,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    setIsLoading(false);
    if (error) {
      setMessage({ type: 'error', text: error.message });
    } else if (data.session) {
      // Email confirmation disabled in project — logged in immediately
      window.location.href = '/dashboard';
    } else {
      setMessage({ type: 'success', text: 'Account created. Check your email for a confirmation link before signing in.' });
    }
  }

  async function handleForgotPassword(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setIsLoading(true);
    setMessage(null);
    const { error } = await createSupabaseBrowserClient().auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/auth/update-password`,
    });
    setIsLoading(false);
    setMessage(error
      ? { type: 'error', text: 'Failed to send reset link. Please try again.' }
      : { type: 'success', text: 'Check your email for a password reset link.' }
    );
  }

  if (subMode === 'forgot') {
    return (
      <form onSubmit={handleForgotPassword} className={s.form}>
        <div>
          <label htmlFor="fp-email" className={s.label}>Email address</label>
          <input
            id="fp-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className={s.input}
          />
        </div>
        {message && (
          <p role="alert" className={message.type === 'success' ? s.msgSuccess : s.msgError}>
            {message.text}
          </p>
        )}
        <button type="submit" disabled={isLoading} className={s.btn}>
          {isLoading ? 'Sending…' : 'Send reset link'}
        </button>
        <div className={s.switchRow}>
          <button type="button" className={s.switchLink} onClick={() => switchTo('signin')}>
            ← Back to sign in
          </button>
        </div>
      </form>
    );
  }

  if (subMode === 'signup') {
    return (
      <form onSubmit={handleSignUp} className={s.form}>
        <div>
          <label htmlFor="su-email" className={s.label}>Email address</label>
          <input
            id="su-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            className={s.input}
          />
        </div>
        <div>
          <label htmlFor="su-pw" className={s.label}>Password</label>
          <input
            id="su-pw"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 8 characters"
            className={s.input}
          />
          {password.length > 0 && (() => {
            const st = getPasswordStrength(password);
            const color = STRENGTH_COLOR[st.level];
            return (
              <div className={s.strengthMeter}>
                <div className={s.strengthBar}>
                  {([1, 2, 3, 4] as const).map((seg) => (
                    <div
                      key={seg}
                      className={s.strengthSegment}
                      style={{ background: st.score >= seg ? color : undefined }}
                    />
                  ))}
                </div>
                {st.label && <span className={s.strengthLabel} style={{ color }}>{st.label}</span>}
              </div>
            );
          })()}
          <ul className={s.requirements}>
            <li className={`${s.req} ${password.length >= 8 ? s.reqMet : ''}`}>
              At least 8 characters
            </li>
            <li className={`${s.req} ${/\d/.test(password) ? s.reqMet : ''}`}>
              Contains a number
            </li>
            <li className={`${s.req} ${/[^a-zA-Z0-9]/.test(password) ? s.reqMet : ''}`}>
              Contains a special character (!@#$%&amp;*)
            </li>
          </ul>
        </div>
        <div>
          <label htmlFor="su-cpw" className={s.label}>Confirm password</label>
          <input
            id="su-cpw"
            type="password"
            required
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            placeholder="Re-enter password"
            className={s.input}
          />
        </div>
        {message && (
          <p role="alert" className={message.type === 'success' ? s.msgSuccess : s.msgError}>
            {message.text}
          </p>
        )}
        <button type="submit" disabled={isLoading} className={s.btn}>
          {isLoading ? 'Creating account…' : 'Create account'}
        </button>
        <div className={s.switchRow}>
          Already have an account?{' '}
          <button type="button" className={s.switchLink} onClick={() => switchTo('signin')}>
            Sign in
          </button>
        </div>
      </form>
    );
  }

  // Default: sign in
  return (
    <form onSubmit={handleSignIn} className={s.form}>
      <div>
        <label htmlFor="si-email" className={s.label}>Email address</label>
        <input
          id="si-email"
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@example.com"
          className={s.input}
        />
      </div>
      <div>
        <label htmlFor="si-pw" className={s.label}>Password</label>
        <input
          id="si-pw"
          type="password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Your password"
          className={s.input}
        />
        <div className={s.forgotRow}>
          <button type="button" className={s.forgotLink} onClick={() => switchTo('forgot')}>
            Forgot password?
          </button>
        </div>
      </div>
      {message && (
        <p role="alert" className={message.type === 'success' ? s.msgSuccess : s.msgError}>
          {message.text}
        </p>
      )}
      <button type="submit" disabled={isLoading} className={s.btn}>
        {isLoading ? 'Signing in…' : 'Sign in'}
      </button>
      <div className={s.switchRow}>
        New to ClaroBill?{' '}
        <button type="button" className={s.switchLink} onClick={() => switchTo('signup')}>
          Create an account
        </button>
      </div>
    </form>
  );
}
