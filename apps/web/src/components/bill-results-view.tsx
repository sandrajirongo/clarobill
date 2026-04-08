'use client';

import Link from 'next/link';
import { useState } from 'react';
import type { Bill, LineItem, AnalysisResult, BillingError } from '@clarobill/shared';
import s from './bill-results-view.module.css';

interface BillResultsViewProps {
  bill: Bill;
  lineItems: LineItem[];
  analysis: AnalysisResult;
  hiddenErrorCount: number;
  hasPaid: boolean;
  paymentStatus: string | null;
}

export function BillResultsView(props: BillResultsViewProps): JSX.Element {
  const { bill, analysis, hiddenErrorCount, hasPaid, paymentStatus } = props;
  const [isStartingCheckout, setIsStartingCheckout] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  async function handleGetFullReport(): Promise<void> {
    setIsStartingCheckout(true);
    setCheckoutError(null);
    try {
      const res = await fetch('/api/stripe/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ billId: bill.id }),
      });
      if (!res.ok) {
        setCheckoutError('Could not start checkout. Please try again.');
        return;
      }
      const { checkoutUrl } = await res.json() as { checkoutUrl: string };
      window.location.href = checkoutUrl;
    } finally {
      setIsStartingCheckout(false);
    }
  }

  return (
    <main className={s.main}>
      <div className={s.inner}>

        {paymentStatus === 'success' && (
          <div className={s.successBanner}>
            Access confirmed. Your full report and dispute letter are being prepared below.
          </div>
        )}

        {/* Header */}
        <div>
          <Link href="/dashboard" className={s.backLink}>← My Bills</Link>
          <h1 className={s.pageTitle}>Bill Analysis</h1>
          <p className={s.fileName}>{bill.fileName}</p>
        </div>

        {/* Summary cards */}
        <div className={s.summaryGrid}>
          <SummaryCard label="Total Charges" value={`$${analysis.totalCharges.toFixed(2)}`} />
          <SummaryCard
            label="Potential Savings"
            value={`$${analysis.totalPotentialSavings.toFixed(2)}`}
            highlight={analysis.totalPotentialSavings > 0}
          />
          <SummaryCard
            label="Issues Found"
            value={String(analysis.errors.length + hiddenErrorCount)}
          />
        </div>

        {/* AI Summary */}
        <div className={s.card}>
          <p className={s.cardLabel}>Summary</p>
          <p className={s.summaryText}>{analysis.aiSummary}</p>
        </div>

        {/* Findings */}
        <div className={s.card}>
          <p className={s.cardLabel}>Findings</p>
          {analysis.errors.length === 0 && hiddenErrorCount === 0 ? (
            <p className={s.emptyText}>No billing errors were detected.</p>
          ) : (
            <div className={s.errorList}>
              {analysis.errors.map((error, i) => (
                <ErrorCard key={i} error={error} />
              ))}
              {hiddenErrorCount > 0 && <PaywallCard count={hiddenErrorCount} />}
            </div>
          )}
        </div>

        {/* Paywall CTA */}
        {!hasPaid && (
          <div className={s.paywallCta}>
            <h2 className={s.paywallCtaTitle}>Get the Full Report</h2>
            <p className={s.paywallCtaSub}>
              Unlock all findings, a detailed PDF report, and a ready-to-send dispute letter.
            </p>
            <p className={s.paywallCtaPrice}>$9.99</p>
            {checkoutError && <p className={s.paywallError}>{checkoutError}</p>}
            <button
              onClick={handleGetFullReport}
              disabled={isStartingCheckout}
              className={s.paywallBtn}
            >
              {isStartingCheckout ? 'Redirecting…' : 'Get Full Report & Dispute Letter'}
            </button>
          </div>
        )}

        {/* Download links (post-payment) */}
        {hasPaid && (analysis.reportUrl || analysis.disputeLetterUrl) && (
          <div className={s.card}>
            <p className={s.cardLabel}>Your Documents</p>
            <p className={s.summaryText} style={{ marginBottom: '1rem' }}>
              Download your full report and dispute letter below.
            </p>
            <div className={s.downloadRow}>
              {analysis.reportUrl && (
                <DownloadButton billId={bill.id} type="report" label="Download Report" />
              )}
              {analysis.disputeLetterUrl && (
                <DownloadButton billId={bill.id} type="dispute-letter" label="Download Dispute Letter" />
              )}
            </div>
          </div>
        )}

      </div>
    </main>
  );
}

function SummaryCard({ label, value, highlight = false }: {
  label: string;
  value: string;
  highlight?: boolean;
}): JSX.Element {
  return (
    <div className={s.summaryCard}>
      <p className={`${s.summaryValue} ${highlight ? s.summaryValueHighlight : ''}`}>{value}</p>
      <p className={s.summaryLabel}>{label}</p>
    </div>
  );
}

function ErrorCard({ error }: { error: BillingError }): JSX.Element {
  const cardCls =
    error.severity === 'critical' ? s.errorCardCritical :
    error.severity === 'warning'  ? s.errorCardWarning :
    s.errorCardInfo;

  const badgeCls =
    error.severity === 'critical' ? s.errorBadgeCritical :
    error.severity === 'warning'  ? s.errorBadgeWarning :
    s.errorBadgeInfo;

  return (
    <div className={`${s.errorCard} ${cardCls}`}>
      <div className={s.errorTop}>
        <span className={`${s.errorBadge} ${badgeCls}`}>{error.severity.toUpperCase()}</span>
        <div>
          <p className={s.errorTitle}>{error.code.replace(/_/g, ' ')}</p>
          <p className={s.errorDesc}>{error.description}</p>
          {error.estimatedOvercharge > 0 && (
            <p className={s.errorOvercharge}>
              Estimated overcharge: ${error.estimatedOvercharge.toFixed(2)}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function PaywallCard({ count }: { count: number }): JSX.Element {
  return (
    <div className={s.paywallCard}>
      <p className={s.paywallText}>
        <span className={s.paywallCount}>{count} more issue{count > 1 ? 's' : ''}</span>{' '}
        hidden — unlock the full report to see all findings.
      </p>
    </div>
  );
}

function DownloadButton({ billId, type, label }: {
  billId: string;
  type: 'report' | 'dispute-letter';
  label: string;
}): JSX.Element {
  const [loading, setLoading] = useState(false);

  async function handleDownload(): Promise<void> {
    setLoading(true);
    try {
      const res = await fetch(`/api/bills/${billId}/download?type=${type}`);
      if (!res.ok) return;
      const { url } = await res.json() as { url: string };
      window.open(url, '_blank');
    } finally {
      setLoading(false);
    }
  }

  return (
    <button onClick={handleDownload} disabled={loading} className={s.downloadBtn}>
      {loading ? 'Generating link…' : label}
    </button>
  );
}
