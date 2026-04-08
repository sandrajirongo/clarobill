'use client';

// Auth pages depend on runtime env vars and the user's session — never pre-render
export const dynamic = 'force-dynamic';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import s from './sign-in.module.css';

export default function SignInPage(): JSX.Element {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  async function handleMagicLink(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setIsLoading(true);
    setMessage(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: `${window.location.origin}/auth/callback` },
    });
    setIsLoading(false);
    if (error) {
      setMessage({ type: 'error', text: 'Failed to send magic link. Please try again.' });
    } else {
      setMessage({ type: 'success', text: 'Check your email — a sign-in link is on its way.' });
    }
  }

  return (
    <main className={s.root}>
      <div className={s.card}>
        {/* Logo */}
        <div className={s.logoRow}>
          <div className={s.logoMark}>C</div>
          <span className={s.logoText}>Claro<em style={{ fontStyle: 'italic' }}>Bill</em></span>
        </div>

        <h1 className={s.heading}>Sign in to Claro<em style={{ fontStyle: 'italic' }}>Bill</em></h1>
        <p className={s.sub}>Catch errors on your medical bills in minutes.</p>

        <form onSubmit={handleMagicLink} className={s.form}>
          <div>
            <label htmlFor="email" className={s.label}>Email address</label>
            <input
              id="email"
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
      </div>

      <p className={s.note}>
        Protected by 256-bit AES encryption. Your data is never sold or shared.
      </p>
    </main>
  );
}
