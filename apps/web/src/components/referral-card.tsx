'use client';

import { useState } from 'react';

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
    <section className="bg-gradient-to-br from-brand-600 to-brand-700 rounded-2xl p-6 text-white">
      {/* Headline */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold">Give $5, Get $5</h2>
          <p className="text-sm text-brand-100 mt-1">
            Share your link — your friend gets $5 off their first report, and you earn $5 credit when they purchase.
          </p>
        </div>
        {creditsEarned > 0 && (
          <div className="shrink-0 bg-white/15 rounded-xl px-3 py-2 text-center">
            <p className="text-lg font-bold">${(creditsEarned / 100).toFixed(0)}</p>
            <p className="text-2xs text-brand-100 uppercase tracking-wide">Earned</p>
          </div>
        )}
      </div>

      {/* Referral link */}
      <div className="mt-5 flex gap-2">
        <div className="flex-1 bg-white/10 border border-white/20 rounded-lg px-3 py-2.5 text-sm font-mono text-brand-100 truncate">
          clarobill.com/ref/{referralCode}
        </div>
        <button
          onClick={handleCopy}
          className={`shrink-0 px-4 py-2.5 rounded-lg text-sm font-semibold transition-colors ${
            copied
              ? 'bg-green-400 text-white'
              : 'bg-white text-brand-700 hover:bg-brand-50'
          }`}
        >
          {copied ? 'Copied!' : 'Copy link'}
        </button>
      </div>

      {/* Stats */}
      {convertedCount > 0 && (
        <p className="mt-3 text-xs text-brand-100">
          {convertedCount} friend{convertedCount > 1 ? 's' : ''} referred · ${(convertedCount * 5).toFixed(0)} total earned
        </p>
      )}
    </section>
  );
}
