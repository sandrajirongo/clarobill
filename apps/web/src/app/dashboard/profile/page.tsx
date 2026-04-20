'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useTranslations } from 'next-intl';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';
import { MembersPanel } from '@/components/members-panel';
import { LanguageSwitcher } from '@/components/language-switcher';
import s from '../dashboard.module.css';

export default function ProfilePage(): JSX.Element {
  const t = useTranslations('profile');
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
          new Date(user.created_at).toLocaleDateString(undefined, {
            month: 'long', day: 'numeric', year: 'numeric',
          })
        );
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleDeleteAccount(): Promise<void> {
    setIsDeleting(true);
    setDeleteError(null);
    const res = await fetch('/api/user', { method: 'DELETE' });
    if (!res.ok) {
      setDeleteError(t('deleteError'));
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
        <h1 className={s.pageTitle}>{t('title')}</h1>
        <p className={s.pageSub}>{t('subtitle')}</p>
      </div>

      <MembersPanel />

      {/* Language */}
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>{t('language')}</p></div>
        <div className={s.cardBody}>
          <p style={{ fontSize: '.82rem', color: 'var(--txt2)', marginBottom: '.85rem' }}>
            {t('languageSubtitle')}
          </p>
          <LanguageSwitcher />
        </div>
      </div>

      {/* Account */}
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>{t('account')}</p></div>
        <div className={s.cardBody} style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className={s.profileAvatar}>{initial || '?'}</div>
          <div>
            <p className={s.profileEmail}>{email || '—'}</p>
            {memberSince && <p className={s.profileSince}>{t('memberSince', { date: memberSince })}</p>}
          </div>
        </div>
      </div>

      {/* Data & Privacy */}
      <div className={s.card}>
        <div className={s.cardHeader}><p className={s.cardTitle}>{t('dataPrivacy')}</p></div>
        <div className={s.cardBody}>
          <InfoRow label={t('dataStorage')}    value={t('dataStorageValue')} />
          <InfoRow label={t('fileRetention')}  value={t('fileRetentionValue')} />
          <InfoRow label={t('analysisResults')} value={t('analysisResultsValue')} />
          <InfoRow label={t('dataSharing')}    value={t('dataSharingValue')} />
        </div>
      </div>

      {/* Danger zone */}
      <div className={s.card} style={{ borderColor: '#FECACA' }}>
        <div className={s.dangerCardHeader}><p className={s.dangerCardTitle}>{t('dangerZone')}</p></div>
        <div className={s.cardBody}>
          <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1.5rem' }}>
            <div>
              <p style={{ fontSize: '.875rem', fontWeight: 600, color: 'var(--txt)', marginBottom: '.3rem' }}>
                {t('deleteAccount')}
              </p>
              <p style={{ fontSize: '.84rem', color: 'var(--txt2)', lineHeight: 1.6 }}>
                {t('deleteAccountDesc')}
              </p>
            </div>
            {!showDeleteConfirm && (
              <button onClick={() => setShowDeleteConfirm(true)} className={s.dangerBtn}>
                {t('deleteBtn')}
              </button>
            )}
          </div>

          {showDeleteConfirm && (
            <div className={s.dangerConfirm}>
              <p className={s.dangerConfirmText}>{t('deleteConfirm')}</p>
              {deleteError && <p className={s.dangerErrorText}>{deleteError}</p>}
              <div className={s.dangerActions}>
                <button
                  onClick={() => { setShowDeleteConfirm(false); setDeleteError(null); }}
                  disabled={isDeleting}
                  className={s.cancelBtn}
                >
                  {t('cancel')}
                </button>
                <button
                  onClick={handleDeleteAccount}
                  disabled={isDeleting}
                  className={s.confirmDeleteBtn}
                >
                  {isDeleting ? t('deleting') : t('confirmDelete')}
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
