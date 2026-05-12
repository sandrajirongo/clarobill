'use client';

import { useState } from 'react';
import s from '@/app/billing-traps-guide/billing-traps-guide.module.css';

type FormState = 'idle' | 'loading' | 'success' | 'error';

export function BillingTrapsForm(): JSX.Element {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<FormState>('idle');
  const [errorMsg, setErrorMsg] = useState('');

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setState('loading');
    setErrorMsg('');

    try {
      const res = await fetch('/api/lead-magnet/billing-traps', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      if (!res.ok) {
        const data = (await res.json()) as { error?: { detail?: string } };
        setErrorMsg(data.error?.detail ?? 'Something went wrong. Please try again.');
        setState('error');
        return;
      }

      setState('success');
    } catch {
      setErrorMsg('Something went wrong. Please try again.');
      setState('error');
    }
  }

  if (state === 'success') {
    return (
      <div className={s.success}>
        <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
          <circle cx="14" cy="14" r="14" fill="var(--sage, #2D4A2A)" />
          <path
            d="M8 14.5l4 4 8-9"
            stroke="var(--accent, #C8F060)"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <p className={s.successHeadline}>Check your inbox</p>
        <p className={s.successBody}>
          The guide is on its way. Check your spam folder if you do not see it within a minute.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className={s.form} noValidate>
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        className={s.input}
        disabled={state === 'loading'}
        aria-label="Email address"
      />
      <button type="submit" className={s.button} disabled={state === 'loading'}>
        {state === 'loading' ? 'Sending...' : 'Send me the free guide'}
      </button>
      {state === 'error' && <p className={s.formError}>{errorMsg}</p>}
    </form>
  );
}
