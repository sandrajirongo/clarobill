'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { MembersPanel } from '@/components/members-panel';
import s from '../dashboard.module.css';

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
    <main className={s.page}>
      <div>
        <h1 className={s.pageTitle}>Profile</h1>
        <p className={s.pageSub}>Manage your account and privacy settings</p>
      </div>

      {/* Members & Insurance */}
      <MembersPanel />

      {/* Account */}
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>Account</p></div>
        <div className={s.cardBody} style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className={s.profileAvatar}>{initial || '?'}</div>
          <div>
            <p className={s.profileEmail}>{email || '—'}</p>
            {memberSince && <p className={s.profileSince}>Member since {memberSince}</p>}
          </div>
        </div>
      </div>

      {/* Data & Privacy */}
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>Data & Privacy</p></div>
        <div className={s.cardBody}>
          <InfoRow label="Data storage" value="AES-256 encryption at rest, TLS 1.3 in transit" />
          <InfoRow label="Bill file retention" value="Raw files deleted automatically after 60 days" />
          <InfoRow label="Analysis results" value="Kept indefinitely — accessible in Reports" />
          <InfoRow label="Data sharing" value="Never sold or shared with third parties" />
        </div>
      </div>

      {/* Danger zone */}
      <div className={s.card} style={{ borderColor: '#FECACA' }}>
        <div className={s.dangerCardHeader}><p className={s.dangerCardTitle}>Danger Zone</p></div>
        <div className={s.cardBody}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1.5rem' }}>
            <div>
              <p style={{ fontSize: '.875rem', fontWeight: 600, color: 'var(--txt)', marginBottom: '.3rem' }}>
                Delete my account
              </p>
              <p style={{ fontSize: '.84rem', color: 'var(--txt2)', lineHeight: 1.6 }}>
                Permanently removes your account, all uploaded bills, and analysis results. This cannot be undone.
              </p>
            </div>
            {!showDeleteConfirm && (
              <button onClick={() => setShowDeleteConfirm(true)} className={s.dangerBtn}>
                Delete account
              </button>
            )}
          </div>

          {showDeleteConfirm && (
            <div className={s.dangerConfirm}>
              <p className={s.dangerConfirmText}>
                This will permanently delete all your bills, analyses, and reports. Are you sure?
              </p>
              {deleteError && <p className={s.dangerErrorText}>{deleteError}</p>}
              <div className={s.dangerActions}>
                <button
                  onClick={() => { setShowDeleteConfirm(false); setDeleteError(null); }}
                  disabled={isDeleting}
                  className={s.cancelBtn}
                >
                  Cancel
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={isDeleting}
                  className={s.confirmDeleteBtn}
                >
                  {isDeleting ? 'Deleting…' : 'Yes, delete everything'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function InfoRow({ label, value }: { label: string; value: string }): JSX.Element {
  return (
    <div className={s.infoRow}>
      <span className={s.infoLabel}>{label}</span>
      <span className={s.infoValue}>{value}</span>
    </div>
  );
}
