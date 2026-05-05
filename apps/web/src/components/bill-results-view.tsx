'use client';

import Link from 'next/link';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import type { Bill, LineItem, AnalysisResult, BillingError } from '@clarobill/shared';
import { getPriceTier } from '@/lib/pricing';
import { isBetaMode, BETA_COPY } from '@/lib/beta';
import { DownloadButton } from '@/components/download-button';
import {
  AnalysisUrlsResponseSchema,
  CheckoutResponseSchema,
  StatusResponseSchema,
  parseJsonResponse,
} from '@/lib/api/parsers';
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
        const { status } = await parseJsonResponse(res, StatusResponseSchema);
        if (status === 'complete' || status === 'failed') {
          clearInterval(interval);
          if (!cancelled) router.refresh(); // re-run Server Component to get results
        }
      } catch { /* network blip — keep polling */ }
    }, 2500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [analysis, bill.id, router]);

  // After payment, poll the analysis API directly every 5s for up to 7 min.
  // The report-generation pipeline (PDF + DOCX + email + storage upload)
  // takes ~3 min on average and occasionally up to ~5 min on Cloud Run cold
  // starts or large bills. The previous 120s ceiling was firing the
  // timeout state mid-generation while the email was still being sent
  // successfully — confusing users and offering them a "try again" button
  // that re-triggered Stripe checkout (catastrophically wrong since they
  // had already paid).
  //
  // 7 minutes (84 × 5s) gives comfortable headroom for the slowest legit
  // generation. The user does NOT need to stay on this page — the email
  // is the authoritative delivery; the in-page download is a convenience.
  // We tell them that explicitly in the progressive copy below.
  //
  // We don't call router.refresh() on every tick — router from useRouter()
  // is not a stable reference in Next.js App Router, so putting it in deps
  // causes the effect to re-run on every refresh and reset the counter
  // (infinite loop). Instead: poll the API directly, call router.refresh()
  // exactly once when the URL appears.
  const POLL_INTERVAL_MS = 5_000;
  const POLL_MAX_TICKS = 84; // 84 × 5 s = 420 s = 7 minutes
  const reportAlreadyReady = !!(analysis?.reportUrl || analysis?.disputeLetterUrl);
  const [pendingElapsedMs, setPendingElapsedMs] = useState(0);
  useEffect(() => {
    if (!hasPaid || !analysis || reportAlreadyReady) return;

    const billId = bill.id;
    let count = 0;

    const interval = setInterval(async () => {
      count++;
      setPendingElapsedMs(count * POLL_INTERVAL_MS);
      if (count >= POLL_MAX_TICKS) {
        clearInterval(interval);
        setReportTimedOut(true);
        return;
      }
      try {
        const res = await fetch(`/api/bills/${billId}/analysis`);
        if (!res.ok) return;
        const data = await parseJsonResponse(res, AnalysisUrlsResponseSchema);
        if (data.analysis?.reportUrl || data.analysis?.disputeLetterUrl) {
          clearInterval(interval);
          router.refresh();
        }
      } catch { /* network blip — keep polling */ }
    }, POLL_INTERVAL_MS);

    return () => clearInterval(interval);
  // router is captured in closure but not in deps — it's not a stable reference.
  // hasPaid and reportAlreadyReady are stable booleans that only change meaningfully.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasPaid, reportAlreadyReady]);

  // Progressive status copy — surfaces what the system is doing so the wait
  // doesn't feel broken. Tied to elapsed-time buckets, not real backend
  // signals (we don't have step-level progress events from the engine yet).
  function progressiveCopy(elapsedMs: number): { title: string; sub: string } {
    const seconds = Math.floor(elapsedMs / 1000);
    if (seconds < 30) {
      return {
        title: 'Generating your report…',
        sub: 'Building your PDF and dispute letter. This page updates automatically when they’re ready, and we’ll also email them. No need to stay here.',
      };
    }
    if (seconds < 90) {
      return {
        title: 'Still working. Most reports take about 3 minutes.',
        sub: 'Running our full audit across every line item on your bill.',
      };
    }
    if (seconds < 180) {
      return {
        title: 'Almost there. Finalizing your dispute letter…',
        sub: 'Pre-populating the recipient address and signature block. The downloads will appear here automatically.',
      };
    }
    if (seconds < 300) {
      return {
        title: 'Wrapping up. We’ve also emailed it to you.',
        sub: 'Generation occasionally takes up to 5 minutes for larger bills. The email is the authoritative copy. Feel free to close this page.',
      };
    }
    return {
      title: 'Taking a little longer than usual.',
      sub: 'Your report and dispute letter have been emailed (or will be shortly). They’ll also appear here when generation completes. Refresh this page in a minute or two.',
    };
  }

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
              <p style={{ fontSize: '.82rem', color: 'var(--txt2)' }}>Running a deep audit across every line item on your bill. This takes a few minutes.</p>
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
      const { checkoutUrl } = await parseJsonResponse(res, CheckoutResponseSchema);
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
              ? 'Payment confirmed. Your report and dispute letter are being generated. This page updates automatically.'
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
            {isBetaMode() ? (
              <>
                <div className={s.paywallBetaPriceRow}>
                  <span className={s.paywallStrikePrice}>{priceTier.priceDisplay}</span>
                  <span className={s.paywallFreePrice}>Free</span>
                </div>
                <p className={s.paywallBetaBadge}>{BETA_COPY.paywall.badge}</p>
                <p className={s.paywallOneTime}>
                  All findings, PDF report, and dispute letter. No card required.
                </p>
              </>
            ) : (
              <>
                <p className={s.paywallCtaPrice}>{priceTier.priceDisplay}</p>
                <p className={s.paywallOneTime}>
                  one-time · all findings + PDF report + dispute letter
                </p>
              </>
            )}
            {checkoutError && <p className={s.paywallError}>{checkoutError}</p>}
            <button
              onClick={handleGetFullReport}
              disabled={isStartingCheckout}
              className={s.paywallBtn}
            >
              {isStartingCheckout
                ? 'Redirecting…'
                : isBetaMode() ? BETA_COPY.paywall.button : 'Unlock Report'}
            </button>
          </div>
        )}

        {/* Documents section (post-payment) */}
        {reportPending && (
          <div className={s.card}>
            <p className={s.cardLabel}>Your Documents</p>
            {reportTimedOut ? (
              // Polling exhausted (7 min). Critically: do NOT offer a button
              // that retriggers Stripe checkout — the user has already paid.
              // The email is the authoritative delivery; this surface just
              // lets them refresh to pull the in-page download once Cloud
              // Run finishes the upload.
              <div className={s.reportPendingWrap}>
                <div>
                  <p className={s.reportPendingTitle}>Your report has been emailed.</p>
                  <p className={s.reportPendingSub}>
                    Check your inbox (and the spam folder) for your full PDF report and editable dispute letter. They’ll also appear here for direct download once the upload completes.
                  </p>
                  <button
                    onClick={() => router.refresh()}
                    className={s.retryBtn}
                    aria-label="Refresh page to check for downloads"
                  >
                    Refresh page
                  </button>
                </div>
              </div>
            ) : (
              <div className={s.reportPendingWrap}>
                <div className={s.reportPendingSpinner} />
                <div>
                  {(() => {
                    const copy = progressiveCopy(pendingElapsedMs);
                    return (
                      <>
                        <p className={s.reportPendingTitle}>{copy.title}</p>
                        <p className={s.reportPendingSub}>{copy.sub}</p>
                      </>
                    );
                  })()}
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

