'use client';

import { useState } from 'react';
import s from '@/app/dashboard/dashboard.module.css';

interface ReferralCardProps {
  referralCode: string;
  convertedCount: number;
  creditsEarned: number;
}

export function ReferralCard({
  referralCode,
  convertedCount,
  creditsEarned,
}: ReferralCardProps): JSX.Element {
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
          <h2 className={s.referralH}>Give $5, Get $5</h2>
          <p className={s.referralSub}>
            Share your link — your friend gets $5 off their first report, and you earn $5 credit when they purchase.
          </p>
        </div>
        {creditsEarned > 0 && (
          <div className={s.creditsBadge}>
            <p className={s.creditsAmt}>${(creditsEarned / 100).toFixed(0)}</p>
            <p className={s.creditsLbl}>Earned</p>
          </div>
        )}
      </div>

      <div className={s.referralRow}>
        <div className={s.referralLink}>clarobill.com/ref/{referralCode}</div>
        <button
          onClick={handleCopy}
          className={`${s.copyBtn} ${copied ? s.copyBtnCopied : ''}`}
        >
          {copied ? 'Copied!' : 'Copy link'}
        </button>
      </div>

      {convertedCount > 0 && (
        <p className={s.referralStats}>
          {convertedCount} friend{convertedCount > 1 ? 's' : ''} referred · ${(convertedCount * 5).toFixed(0)} total earned
        </p>
      )}
    </section>
  );
}
