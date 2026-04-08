'use client';

// Auth pages depend on runtime env vars and the user's session — never pre-render
export const dynamic = 'force-dynamic';

import { useState } from 'react';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { Logo } from '@/components/logo';

export default function SignInPage(): JSX.Element {
  const [email, setEmail] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [oauthLoading, setOauthLoading] = useState<'google' | 'apple' | null>(null);
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
      setMessage({ type: 'success', text: 'Check your email for a sign-in link.' });
    }
  }

  async function handleOAuth(provider: 'google' | 'apple'): Promise<void> {
    setOauthLoading(provider);
    setMessage(null);
    const supabase = createSupabaseBrowserClient();
    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: `${window.location.origin}/auth/callback` },
    });
    if (error) {
      setMessage({ type: 'error', text: `${provider === 'google' ? 'Google' : 'Apple'} sign-in failed. Please try again.` });
      setOauthLoading(null);
    }
    // On success the browser is redirected by Supabase — no need to reset state
  }

  return (
    <main className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-sm">
        {/* Card */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-8">
          <div className="mb-8">
            <Logo size="md" />
            <h1 className="text-xl font-semibold text-slate-900 mt-6">Sign in to Clarobill</h1>
            <p className="text-sm text-slate-500 mt-1">Catch errors on your medical bills in minutes.</p>
          </div>

          {/* OAuth buttons */}
          <div className="space-y-3 mb-6">
            <button
              onClick={() => handleOAuth('google')}
              disabled={oauthLoading !== null || isLoading}
              className="w-full flex items-center justify-center gap-3 border border-slate-200 rounded-lg py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 transition-colors disabled:opacity-50"
            >
              <GoogleIcon />
              {oauthLoading === 'google' ? 'Redirecting…' : 'Continue with Google'}
            </button>
            <button
              onClick={() => handleOAuth('apple')}
              disabled={oauthLoading !== null || isLoading}
              className="w-full flex items-center justify-center gap-3 bg-slate-900 rounded-lg py-2.5 text-sm font-medium text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
            >
              <AppleIcon />
              {oauthLoading === 'apple' ? 'Redirecting…' : 'Continue with Apple'}
            </button>
          </div>

          {/* Divider */}
          <div className="flex items-center gap-3 mb-6">
            <div className="flex-1 h-px bg-slate-100" />
            <span className="text-xs text-slate-400">or</span>
            <div className="flex-1 h-px bg-slate-100" />
          </div>

          {/* Magic link form */}
          <form onSubmit={handleMagicLink} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-slate-700 mb-1">
                Email address
              </label>
              <input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-brand-600 focus:border-transparent transition"
              />
            </div>

            {message && (
              <p
                role="alert"
                className={`text-sm rounded-lg px-3 py-2.5 ${
                  message.type === 'success'
                    ? 'bg-green-50 text-green-900'
                    : 'bg-red-50 text-red-700'
                }`}
              >
                {message.text}
              </p>
            )}

            <button
              type="submit"
              disabled={isLoading || oauthLoading !== null}
              className="w-full bg-brand-600 text-white rounded-lg py-2.5 text-sm font-semibold hover:bg-brand-700 disabled:opacity-50 transition-colors"
            >
              {isLoading ? 'Sending…' : 'Send magic link'}
            </button>
          </form>
        </div>

        {/* Trust signal */}
        <p className="text-center text-2xs text-slate-400 mt-6 leading-relaxed">
          Protected by 256-bit AES encryption. Your data is never sold or shared.
        </p>
      </div>
    </main>
  );
}

function GoogleIcon(): JSX.Element {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M17.64 9.205c0-.639-.057-1.252-.164-1.841H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z" fill="#4285F4"/>
      <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
      <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
      <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
    </svg>
  );
}

function AppleIcon(): JSX.Element {
  return (
    <svg width="16" height="18" viewBox="0 0 814 1000" fill="currentColor" xmlns="http://www.w3.org/2000/svg">
      <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76 0-103.7 40.8-165.9 40.8s-105-57.8-155.5-127.4C46 336.8 97.9 241.4 97.9 174c0-65.1 37.7-114.2 79.3-159.1 56.2-60 142.4-106.8 233.6-106.8 76.4 0 138.2 31.7 185.2 82.8 0-.1 0 0 0 .1 64.6 71 80.1 138.5 80.1 139.7zm-353.8-170.2c12-45.9 41.7-99.5 76.2-136.9 36-39.6 86.1-67.7 128.3-67.7 6.8 0 8.9.6 14.5.9-11.6 47.5-41.3 95.6-76.2 127.9-34 31.4-81 57.1-125.5 57.1-5.6 0-8.5-.6-17.3-1.3z"/>
    </svg>
  );
}
