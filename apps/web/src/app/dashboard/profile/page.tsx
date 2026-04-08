'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

export default function ProfilePage(): JSX.Element {
  const [email, setEmail] = useState('');
  const [memberSince, setMemberSince] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const router = useRouter();
  const supabase = createSupabaseBrowserClient();

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const user = data.session?.user;
      if (!user) return;
      setEmail(user.email ?? '');
      if (user.created_at) {
        setMemberSince(
          new Date(user.created_at).toLocaleDateString('en-US', {
            month: 'long', day: 'numeric', year: 'numeric',
          })
        );
      }
    });
  }, []);

  async function handleDeleteAccount(): Promise<void> {
    setIsDeleting(true);
    setDeleteError(null);
    const res = await fetch('/api/user', { method: 'DELETE' });
    if (!res.ok) {
      setDeleteError('Something went wrong. Please try again or contact support.');
      setIsDeleting(false);
      return;
    }
    await supabase.auth.signOut();
    router.push('/');
  }

  const initial = email.charAt(0).toUpperCase();

  return (
    <main className="max-w-2xl mx-auto px-6 py-8 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Profile</h1>

      {/* Account card */}
      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm">
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Account</h2>
        </div>
        <div className="px-6 py-6 flex items-center gap-4">
          <div className="w-14 h-14 rounded-full bg-brand-600 text-white text-xl font-bold flex items-center justify-center shrink-0">
            {initial || '?'}
          </div>
          <div>
            <p className="text-base font-semibold text-slate-900">{email || '—'}</p>
            {memberSince && (
              <p className="text-sm text-slate-400 mt-0.5">Member since {memberSince}</p>
            )}
          </div>
        </div>
      </section>

      {/* Data & privacy */}
      <section className="bg-white rounded-2xl border border-slate-100 shadow-sm">
        <div className="px-6 py-4 border-b border-slate-100">
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Data & Privacy</h2>
        </div>
        <div className="px-6 py-5 space-y-3">
          <InfoRow label="Data storage" value="AES-256 encryption at rest, TLS 1.3 in transit" />
          <InfoRow label="Bill file retention" value="Raw files deleted automatically after 60 days" />
          <InfoRow label="Analysis results" value="Kept indefinitely — accessible in Reports" />
          <InfoRow label="Data sharing" value="Never sold or shared with third parties" />
        </div>
      </section>

      {/* Danger zone */}
      <section className="bg-white rounded-2xl border border-red-100 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-red-100 bg-red-50">
          <h2 className="text-xs font-semibold text-red-600 uppercase tracking-wide">Danger Zone</h2>
        </div>
        <div className="px-6 py-6">
          <div className="flex items-start justify-between gap-6">
            <div>
              <p className="text-sm font-medium text-slate-900">Delete my account</p>
              <p className="text-sm text-slate-500 mt-1">
                Permanently removes your account, all uploaded bills, and analysis results. This cannot be undone.
              </p>
            </div>
            {!showDeleteConfirm && (
              <button
                onClick={() => setShowDeleteConfirm(true)}
                className="shrink-0 text-sm font-semibold text-red-600 border border-red-200 rounded-lg px-4 py-2 hover:bg-red-50 transition-colors"
              >
                Delete account
              </button>
            )}
          </div>

          {showDeleteConfirm && (
            <div className="mt-4 p-4 bg-red-50 rounded-xl border border-red-200">
              <p className="text-sm font-medium text-red-800 mb-3">
                This will permanently delete all your bills, analyses, and reports. Are you sure?
              </p>
              {deleteError && <p className="text-xs text-red-700 mb-2">{deleteError}</p>}
              <div className="flex gap-2">
                <button
                  onClick={() => { setShowDeleteConfirm(false); setDeleteError(null); }}
                  disabled={isDeleting}
                  className="text-sm text-slate-600 border border-slate-200 bg-white rounded-lg px-4 py-2 hover:bg-slate-50 transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={isDeleting}
                  className="text-sm font-semibold text-white bg-red-600 rounded-lg px-4 py-2 hover:bg-red-700 transition-colors disabled:opacity-50"
                >
                  {isDeleting ? 'Deleting…' : 'Yes, delete everything'}
                </button>
              </div>
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function InfoRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className="flex justify-between gap-4 text-sm">
      <span className="text-slate-500 shrink-0">{label}</span>
      <span className="text-slate-700 text-right">{value}</span>
    </div>
  );
}
