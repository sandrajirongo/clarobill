'use client';

// Must be dynamic — reads ?code= at runtime and calls the Supabase client
export const dynamic = 'force-dynamic';

import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import { useSearchParams } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import s from '../sign-in/sign-in.module.css';

type Msg = { type: 'success' | 'error'; text: string };

export default function UpdatePasswordPage(): JSX.Element {
  const searchParams = useSearchParams();
  const [ready, setReady] = useState(false);
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<Msg | null>(null);

  // Exchange the reset code for a recovery session on mount.
  // We do NOT let the middleware redirect this to /auth/callback — see middleware.ts.
  useEffect(() => {
    const code = searchParams.get('code');
    if (!code) {
      setMessage({ type: 'error', text: 'Invalid or expired reset link. Please request a new one from the sign-in page.' });
      return;
    }
    createSupabaseBrowserClient()
      .auth.exchangeCodeForSession(code)
      .then(({ error }) => {
        if (error) {
          setMessage({ type: 'error', text: 'This reset link has expired or already been used. Please request a new one.' });
        } else {
          setReady(true);
        }
      });
  }, [searchParams]);

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
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
    const { error } = await createSupabaseBrowserClient().auth.updateUser({ password });
    setIsLoading(false);
    if (error) {
      setMessage({ type: 'error', text: 'Failed to update password. Please try again.' });
    } else {
      window.location.href = '/dashboard';
    }
  }

  return (
    <main className={s.root}>
      <div className={s.card}>
        <div className={s.logoRow}>
          <div className={s.logoMark}>C</div>
          <span className={s.logoText}>Claro<em style={{ fontStyle: 'italic' }}>Bill</em></span>
        </div>

        <h1 className={s.heading}>Set a new password</h1>
        <p className={s.sub}>Enter your new password below.</p>

        {/* Show error if code is missing or expired before the form renders */}
        {!ready && message && (
          <p role="alert" className={s.msgError}>{message.text}</p>
        )}

        {ready && (
          <form onSubmit={handleSubmit} className={s.form}>
            <div>
              <label htmlFor="np" className={s.label}>New password</label>
              <input
                id="np"
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className={s.input}
                autoFocus
              />
            </div>
            <div>
              <label htmlFor="cp" className={s.label}>Confirm new password</label>
              <input
                id="cp"
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
              {isLoading ? 'Updating…' : 'Update password'}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
