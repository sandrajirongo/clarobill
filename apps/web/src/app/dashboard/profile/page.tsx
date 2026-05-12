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
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [isSavingName, setIsSavingName] = useState(false);
  const [nameSaved, setNameSaved] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const router = useRouter();
  const supabase = createSupabaseBrowserClient();

  useEffect(() => {
    supabase.auth.getSession().then(async ({ data }) => {
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

      const { data: profile } = await supabase
        .from('user_profiles')
        .select('first_name, last_name')
        .eq('id', user.id)
        .single();

      if (profile) {
        setFirstName(profile.first_name ?? '');
        setLastName(profile.last_name ?? '');
      }
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSaveName(e: React.FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setIsSavingName(true);
    setNameError(null);
    setNameSaved(false);

    const res = await fetch('/api/user/profile', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_name: firstName.trim() || null,
        last_name: lastName.trim() || null,
      }),
    });

    if (!res.ok) {
      setNameError(t('nameError'));
      setIsSavingName(false);
      return;
    }

    setNameSaved(true);
    setIsSavingName(false);
    setTimeout(() => setNameSaved(false), 3000);
  }

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

  const initial = (firstName.charAt(0) || email.charAt(0)).toUpperCase();

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
        <div className={s.cardBody} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* Avatar + email row */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <div className={s.profileAvatar}>{initial || '?'}</div>
            <div>
              <p className={s.profileEmail}>{email || '—'}</p>
              {memberSince && <p className={s.profileSince}>{t('memberSince', { date: memberSince })}</p>}
            </div>
          </div>

          {/* Name form */}
          <form onSubmit={handleSaveName} style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '.65rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '.3rem' }}>
                <span className={s.infoLabel}>{t('firstName')}</span>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  placeholder={t('firstNamePlaceholder')}
                  maxLength={100}
                  className={s.profileInput}
                  disabled={isSavingName}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '.3rem' }}>
                <span className={s.infoLabel}>{t('lastName')}</span>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  placeholder={t('lastNamePlaceholder')}
                  maxLength={100}
                  className={s.profileInput}
                  disabled={isSavingName}
                />
              </label>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem' }}>
              <button type="submit" className={s.savePlanBtn} disabled={isSavingName}>
                {isSavingName ? t('savingName') : t('saveName')}
              </button>
              {nameSaved && (
                <span style={{ fontSize: '.8rem', color: 'var(--sage)' }}>{t('nameUpdated')}</span>
              )}
              {nameError && (
                <span style={{ fontSize: '.8rem', color: '#b91c1c' }}>{nameError}</span>
              )}
            </div>
          </form>
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
