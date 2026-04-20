'use client';

import { useState } from 'react';
import { useTranslations } from 'next-intl';
import s from '@/app/dashboard/dashboard.module.css';

interface ReferralCardProps {
  referralCode: string;
  convertedCount: number;
  creditsEarned: number;
}

export function ReferralCard({ referralCode, convertedCount, creditsEarned }: ReferralCardProps): JSX.Element {
  const t = useTranslations('dashboard.referral');
  const [copied, setCopied] = useState(false);

  const referralUrl =
    typeof window !== 'undefined'
      ? `${window.location.origin}/ref/${referralCode}`
      : `https://clarobill.com/ref/${referralCode}`;

  async function handleCopy(): Promise<void> {
    await navigator.clipboard.writeText(referralUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2500);
  }

  return (
    <section className={s.referralCard}>
      <div className={s.referralTop}>
        <div>
          <h2 className={s.referralH}>{t('heading')}</h2>
          <p className={s.referralSub}>{t('sub')}</p>
        </div>
        {creditsEarned > 0 && (
          <div className={s.creditsBadge}>
            <p className={s.creditsAmt}>${(creditsEarned / 100).toFixed(0)}</p>
            <p className={s.creditsLbl}>{t('earned')}</p>
          </div>
        )}
      </div>

      <div className={s.referralRow}>
        <div className={s.referralLink}>clarobill.com/ref/{referralCode}</div>
        <button
          onClick={handleCopy}
          className={`${s.copyBtn} ${copied ? s.copyBtnCopied : ''}`}
        >
          {copied ? t('copied') : t('copyLink')}
        </button>
      </div>

      {convertedCount > 0 && (
        <p className={s.referralStats}>
          {t('referralStats', { count: convertedCount, amount: `$${(convertedCount * 5).toFixed(0)}` })}
        </p>
      )}
    </section>
  );
}
