'use client';

import { useState } from 'react';
import type { Bill, LineItem, AnalysisResult, BillingError } from '@medscan/shared';

interface BillResultsViewProps {
  bill: Bill;
  lineItems: LineItem[];
  analysis: AnalysisResult;
  hiddenErrorCount: number;
  hasPaid: boolean;
  paymentStatus: string | null;
}

const SEVERITY_STYLES: Record<string, string> = {
  critical: 'bg-red-50 border-red-200 text-red-800',
  warning: 'bg-amber-50 border-amber-200 text-amber-800',
  info: 'bg-blue-50 border-blue-200 text-blue-800',
};

const SEVERITY_BADGE: Record<string, string> = {
  critical: 'bg-red-100 text-red-700',
  warning: 'bg-amber-100 text-amber-700',
  info: 'bg-blue-100 text-blue-700',
};

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
    <main className="min-h-screen bg-gray-50 p-6 md:p-10">
      <div className="max-w-3xl mx-auto space-y-6">

        {/* Payment success banner */}
        {paymentStatus === 'success' && (
          <div className="bg-green-50 border border-green-200 rounded-xl p-4 text-green-800 text-sm">
            Payment confirmed. Your full report and dispute letter have been emailed to you.
          </div>
        )}

        {/* Header */}
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Bill Analysis</h1>
          <p className="text-sm text-gray-500 mt-1">{bill.fileName}</p>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-3 gap-4">
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
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
            Summary
          </h2>
          <p className="text-gray-700 leading-relaxed">{analysis.aiSummary}</p>
        </div>

        {/* Findings */}
        <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
            Findings
          </h2>

          {analysis.errors.length === 0 && hiddenErrorCount === 0 ? (
            <p className="text-gray-500 text-sm">No billing errors were detected.</p>
          ) : (
            <div className="space-y-3">
              {analysis.errors.map((error, i) => (
                <ErrorCard key={i} error={error} />
              ))}
              {hiddenErrorCount > 0 && <PaywallCard count={hiddenErrorCount} />}
            </div>
          )}
        </div>

        {/* Paywall CTA */}
        {!hasPaid && (
          <div className="bg-gray-900 text-white rounded-xl p-6 text-center space-y-4">
            <h2 className="text-lg font-bold">Get the Full Report</h2>
            <p className="text-gray-400 text-sm">
              Unlock all findings, a detailed PDF report, and a ready-to-send dispute letter.
            </p>
            <p className="text-3xl font-bold">$9.99</p>
            {checkoutError && (
              <p className="text-red-400 text-sm">{checkoutError}</p>
            )}
            <button
              onClick={handleGetFullReport}
              disabled={isStartingCheckout}
              className="w-full bg-white text-gray-900 font-semibold py-3 rounded-lg hover:bg-gray-100 transition-colors disabled:opacity-50"
            >
              {isStartingCheckout ? 'Redirecting...' : 'Get Full Report & Dispute Letter'}
            </button>
          </div>
        )}

        {/* Download links (post-payment) */}
        {hasPaid && (analysis.reportUrl || analysis.disputeLetterUrl) && (
          <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-6">
            <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
              Your Documents
            </h2>
            <p className="text-sm text-gray-500 mb-4">
              Your documents were also emailed to you. Use the links below to download them again.
            </p>
            <div className="flex gap-3">
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

function SummaryCard({ label, value, highlight = false }: { label: string; value: string; highlight?: boolean }): JSX.Element {
  return (
    <div className="bg-white rounded-xl border border-gray-100 shadow-sm p-4 text-center">
      <div className={`text-xl font-bold ${highlight ? 'text-green-600' : 'text-gray-900'}`}>
        {value}
      </div>
      <div className="text-xs text-gray-400 mt-1 uppercase tracking-wide">{label}</div>
    </div>
  );
}

function ErrorCard({ error }: { error: BillingError }): JSX.Element {
  return (
    <div className={`border rounded-lg p-4 ${SEVERITY_STYLES[error.severity] ?? 'bg-gray-50 border-gray-200'}`}>
      <div className="flex items-start gap-3">
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-full shrink-0 mt-0.5 ${SEVERITY_BADGE[error.severity] ?? 'bg-gray-100 text-gray-700'}`}>
          {error.severity.toUpperCase()}
        </span>
        <div>
          <p className="text-sm font-medium">{error.code.replace(/_/g, ' ')}</p>
          <p className="text-sm mt-1 opacity-80">{error.description}</p>
          {error.estimatedOvercharge > 0 && (
            <p className="text-sm font-semibold mt-2">
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
    <div className="border border-dashed border-gray-300 rounded-lg p-4 text-center">
      <p className="text-sm text-gray-500">
        <span className="font-semibold text-gray-700">{count} more issue{count > 1 ? 's' : ''}</span>{' '}
        hidden — unlock the full report to see all findings.
      </p>
    </div>
  );
}

function DownloadButton({ billId, type, label }: { billId: string; type: 'report' | 'dispute-letter'; label: string }): JSX.Element {
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
    <button
      onClick={handleDownload}
      disabled={loading}
      className="flex-1 border border-gray-200 text-gray-700 text-sm font-medium py-2 px-4 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
    >
      {loading ? 'Generating link...' : label}
    </button>
  );
}
