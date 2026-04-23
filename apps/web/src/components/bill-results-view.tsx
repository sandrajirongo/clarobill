'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { Bill, LineItem, AnalysisResult, BillingError } from '@clarobill/shared';
import { getPriceTier } from '@/lib/pricing';
import { DownloadButton } from '@/components/download-button';
import s from './bill-results-view.module.css';

interface BillResultsViewProps {
  bill: Bill;
  lineItems: LineItem[];
  // null when the engine is still running — component renders a loading state
  analysis: AnalysisResult | null;
  hiddenErrorCount: number;
  hasPaid: boolean;
  paymentStatus: string | null;
}

export function BillResultsView(props: BillResultsViewProps): JSX.Element {
  const { bill, analysis, hiddenErrorCount, hasPaid, paymentStatus } = props;
  const [isStartingCheckout, setIsStartingCheckout] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);
  const [reportTimedOut, setReportTimedOut] = useState(false);
  const router = useRouter();

  // When analysis is still running, poll and refresh the server component when done.
  useEffect(() => {
    if (analysis !== null) return; // already have results
    let cancelled = false;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/bills/${bill.id}`);
        if (!res.ok || cancelled) return;
        const { status } = await res.json() as { status: string };
        if (status === 'complete' || status === 'failed') {
          clearInterval(interval);
          if (!cancelled) router.refresh(); // re-run Server Component to get results
        }
      } catch { /* network blip — keep polling */ }
    }, 2500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [analysis, bill.id, router]);

  // After payment, report + dispute letter are generated async.
  // Poll every 5s for up to 90s, then show a timeout state with a retry option.
  useEffect(() => {
    if (!hasPaid || analysis === null) return;
    if (analysis.reportUrl || analysis.disputeLetterUrl) return; // already ready

    let refreshCount = 0;
    const MAX_REFRESHES = 18; // 18 × 5s = 90s
    const interval = setInterval(() => {
      refreshCount++;
      router.refresh();
      if (refreshCount >= MAX_REFRESHES) {
        clearInterval(interval);
        setReportTimedOut(true);
      }
    }, 5000);
    return () => clearInterval(interval);
  }, [hasPaid, analysis, router]);

  // Loading state — engine still processing
  if (analysis === null) {
    return (
      <main className={s.main}>
        <div className={s.inner}>
          <Link href="/dashboard" className={s.backLink}>← My Bills</Link>
          <h1 className={s.pageTitle}>Analyzing your bill…</h1>
          <p className={s.fileName}>{bill.displayName ?? bill.fileName}</p>
          <div className={s.card} style={{ display: 'flex', alignItems: 'center', gap: '1rem', padding: '1.5rem' }}>
            <div style={{ width: 28, height: 28, borderRadius: '50%', border: '3px solid rgba(45,74,42,.12)', borderTopColor: 'var(--sage)', animation: 'spin .8s linear infinite', flexShrink: 0 }} />
            <div>
              <p style={{ fontSize: '.9rem', fontWeight: 600, color: 'var(--txt)', marginBottom: '.25rem' }}>Running 10 billing checks</p>
              <p style={{ fontSize: '.82rem', color: 'var(--txt2)' }}>Comparing charges against Medicare rates, your hospital&apos;s published prices, and your insurer&apos;s contracted rates. About 30 seconds.</p>
            </div>
          </div>
        </div>
      </main>
    );
  }

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

  // Only show paywall CTA when there are actually errors to unlock.
  // Showing it on a clean bill ("no issues found") would be misleading.
  const showPaywall = !hasPaid && (analysis.errors.length + hiddenErrorCount) > 0;

  const priceTier = getPriceTier(analysis.totalPotentialSavings);

  // Report generation is async on the engine — can take 15–60s after payment.
  // Show a pending card while we wait, then switch to download buttons on refresh.
  const reportPending = hasPaid && !analysis.reportUrl && !analysis.disputeLetterUrl;

  return (
    <main className={s.main}>
      <div className={s.inner}>

        {paymentStatus === 'success' && (
          <div className={s.successBanner}>
            {reportPending
              ? 'Payment confirmed — your report and dispute letter are being generated. This page updates automatically.'
              : 'Payment confirmed. Your documents are ready below.'}
          </div>
        )}

        {/* Header */}
        <div>
          <Link href="/dashboard" className={s.backLink}>← My Bills</Link>
          <h1 className={s.pageTitle}>{bill.displayName ?? bill.fileName}</h1>
          {bill.displayName && <p className={s.fileName}>{bill.fileName}</p>}
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

        {/* Paywall CTA — only shown when errors exist to unlock */}
        {showPaywall && (
          <div className={s.paywallCta}>
            <p className={s.paywallCtaPrice}>{priceTier.priceDisplay}</p>
            <p className={s.paywallOneTime}>one-time · no subscription</p>
            <div className={s.paywallBenefits}>
              <span>All findings</span>
              <span>PDF report</span>
              <span>Dispute letter</span>
            </div>
            {checkoutError && <p className={s.paywallError}>{checkoutError}</p>}
            <button
              onClick={handleGetFullReport}
              disabled={isStartingCheckout}
              className={s.paywallBtn}
            >
              {isStartingCheckout ? 'Redirecting…' : 'Unlock Report'}
            </button>
          </div>
        )}

        {/* Documents section (post-payment) */}
        {reportPending && (
          <div className={s.card}>
            <p className={s.cardLabel}>Your Documents</p>
            {reportTimedOut ? (
              <div className={s.reportPendingWrap}>
                <div>
                  <p className={s.reportPendingTitle}>Taking longer than expected</p>
                  <p className={s.reportPendingSub}>
                    Check your email — your report may already be there. If not, you can
                    visit the <Link href="/dashboard/reports" className={s.inlineLink}>Reports tab</Link> or try generating again.
                  </p>
                  <button onClick={handleGetFullReport} disabled={isStartingCheckout} className={s.retryBtn}>
                    {isStartingCheckout ? 'Please wait…' : 'Try again'}
                  </button>
                </div>
              </div>
            ) : (
              <div className={s.reportPendingWrap}>
                <div className={s.reportPendingSpinner} />
                <div>
                  <p className={s.reportPendingTitle}>Generating your report…</p>
                  <p className={s.reportPendingSub}>
                    Your full PDF report and ready-to-send dispute letter are being created.
                    This usually takes under a minute — the page will update automatically.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
        {hasPaid && (analysis.reportUrl || analysis.disputeLetterUrl) && (
          <div className={s.card}>
            <p className={s.cardLabel}>Your Documents</p>
            <div className={s.downloadRow}>
              {analysis.reportUrl && (
                <DownloadButton billId={bill.id} type="report" label="Download Report" className={s.downloadBtn} />
              )}
              {analysis.disputeLetterUrl && (
                <DownloadButton billId={bill.id} type="dispute-letter" label="Download Dispute Letter" className={s.downloadBtn} />
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
      <span className={s.paywallCount}>+{count} more hidden</span>
    </div>
  );
}

