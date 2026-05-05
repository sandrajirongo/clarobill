/**
 * Tests for the BillResultsView — the component the S1 bug-fix campaign
 * was protecting. Pre-S1, a snake_case BillingError landing here would
 * crash the render path because the component reads `estimatedOvercharge`
 * (camelCase) directly.
 *
 * These tests mock Next.js navigation + fetch at the module boundary and
 * exercise:
 *   - paywall visibility logic (showPaywall = !hasPaid && hasErrors)
 *   - error rendering (per-finding card with severity badge)
 *   - "no errors" empty state
 *   - hidden-error count rendering (the teaser before payment)
 *   - loading state when analysis is null
 *   - post-payment download buttons
 *
 * The findings list IS the surface that broke under S1 — these tests are
 * the regression net.
 */

import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { AnalysisResult, Bill, BillingError, LineItem } from '@clarobill/shared';

// ── Mock next/navigation BEFORE importing the component ───────────────────────
vi.mock('next/navigation', () => ({
  useRouter: (): { refresh: () => void; push: (url: string) => void } => ({
    refresh: vi.fn(),
    push: vi.fn(),
  }),
}));

// next/link renders children with an href — fine to identity-passthrough.
vi.mock('next/link', () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => {
    return <a href={href}>{children}</a>;
  },
}));

// DownloadButton is a separate component that hits /api/bills — stub it so
// these tests don't need to wire up its dependencies.
vi.mock('@/components/download-button', () => ({
  DownloadButton: ({ label, type }: { label: string; type: string }) => (
    <button data-testid={`download-${type}`}>{label}</button>
  ),
}));

import { BillResultsView } from '@/components/bill-results-view';

// ── Test-data helpers ─────────────────────────────────────────────────────────

function makeBill(overrides: Partial<Bill> = {}): Bill {
  return {
    id: 'bill-1',
    userId: 'user-1',
    displayName: null,
    fileName: 'bill.pdf',
    filePath: 'user-1/bill-1.pdf',
    fileSize: 100_000,
    mimeType: 'application/pdf',
    status: 'complete',
    hospitalNpi: null,
    hospitalName: null,
    hospitalCity: null,
    hospitalState: null,
    hospitalZip: null,
    profileMemberId: null,
    payerName: null,
    planName: null,
    planType: null,
    confirmedAt: null,
    createdAt: '2026-03-15T00:00:00Z',
    updatedAt: '2026-03-15T00:00:00Z',
    ...overrides,
  };
}

function makeError(overrides: Partial<BillingError> = {}): BillingError {
  return {
    code: 'NCCI_UNBUNDLING',
    severity: 'critical',
    affectedLineItemIds: ['li-1'],
    description: 'CPT 27447 and 27486 are an NCCI bundled pair. Billing both is unbundling.',
    estimatedOvercharge: 500.0,
    benchmarkRate: 350.0,
    benchmarkSource: 'medicare',
    ...overrides,
  };
}

function makeAnalysis(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    id: 'analysis-1',
    billId: 'bill-1',
    errors: [],
    totalCharges: 1000.0,
    estimatedFairValue: 1000.0,
    totalPotentialSavings: 0.0,
    aiSummary: 'No issues found.',
    disputeLetterUrl: null,
    reportUrl: null,
    createdAt: '2026-03-15T00:00:00Z',
    ...overrides,
  };
}

const lineItems: LineItem[] = [];

beforeEach(() => {
  // Reset fetch mock — useEffect polls /api/bills/{id} and /api/bills/{id}/analysis.
  // Return a 200 with `complete` status so polling settles quickly.
  global.fetch = vi.fn(async () =>
    new Response(
      JSON.stringify({ status: 'complete', analysis: null }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    )
  ) as typeof fetch;
});

// ── Loading state ─────────────────────────────────────────────────────────────

describe('BillResultsView — loading state', () => {
  it('shows the analyzing message when analysis is null', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={null}
        hiddenErrorCount={0}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    expect(screen.getByText(/Analyzing your bill/)).toBeInTheDocument();
  });
});

// ── Empty state ───────────────────────────────────────────────────────────────

describe('BillResultsView — clean bill (no errors)', () => {
  const props = {
    bill: makeBill(),
    lineItems,
    analysis: makeAnalysis(),
    hiddenErrorCount: 0,
    hasPaid: false,
    paymentStatus: null,
  };

  it('shows the "no billing errors" message', () => {
    render(<BillResultsView {...props} />);
    expect(screen.getByText('No billing errors were detected.')).toBeInTheDocument();
  });

  it('does not show paywall CTA when there are no errors', () => {
    render(<BillResultsView {...props} />);
    // The Stripe button or beta button should NOT appear.
    expect(screen.queryByRole('button', { name: /unlock report|get my full report/i }))
      .not.toBeInTheDocument();
  });

  it('shows zero issues in the summary card', () => {
    render(<BillResultsView {...props} />);
    // "Issues Found" with value 0
    const issuesCard = screen.getByText('Issues Found').closest('div')!;
    expect(issuesCard).toHaveTextContent('0');
  });
});

// ── Errors render — the S1-protected surface ──────────────────────────────────

describe('BillResultsView — with detected errors (S1 regression net)', () => {
  it('renders one ErrorCard per BillingError', () => {
    const errors = [
      makeError({ code: 'NCCI_UNBUNDLING', description: 'Unbundling on knee codes' }),
      makeError({ code: 'DUPLICATE_CHARGE', severity: 'warning', description: 'Duplicate office visit' }),
    ];
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({ errors, totalPotentialSavings: 500 })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus="success"
      />
    );
    expect(screen.getByText('Unbundling on knee codes')).toBeInTheDocument();
    expect(screen.getByText('Duplicate office visit')).toBeInTheDocument();
  });

  it('renders the camelCase estimatedOvercharge to two decimals', () => {
    // S1 regression net: this is the field that crashed pre-fix when the
    // engine emitted snake_case `estimated_overcharge`.
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError({ estimatedOvercharge: 1234.5 })],
          totalPotentialSavings: 1234.5,
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByText(/Estimated overcharge: \$1234\.50/)).toBeInTheDocument();
  });

  it('hides the overcharge line for findings with $0 estimated overcharge', () => {
    // Some findings (e.g. INVALID_CPT_CODE without a benchmark) carry a $0
    // overcharge and should not display the redundant "$0.00" line.
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError({ estimatedOvercharge: 0, description: 'Code is informational' })],
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.queryByText(/Estimated overcharge:/)).not.toBeInTheDocument();
    expect(screen.getByText('Code is informational')).toBeInTheDocument();
  });

  it('renders severity badge text in uppercase', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [
            makeError({ severity: 'critical', description: 'Critical finding' }),
            makeError({ severity: 'warning', description: 'Warning finding' }),
            makeError({ severity: 'info', description: 'Informational finding' }),
          ],
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('CRITICAL')).toBeInTheDocument();
    expect(screen.getByText('WARNING')).toBeInTheDocument();
    expect(screen.getByText('INFO')).toBeInTheDocument();
  });

  it('replaces underscores in code names with spaces', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError({ code: 'HOSPITAL_CHARGE_OUTLIER' })],
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('HOSPITAL CHARGE OUTLIER')).toBeInTheDocument();
  });
});

// ── Paywall visibility logic ─────────────────────────────────────────────────

describe('BillResultsView — paywall logic', () => {
  it('shows paywall when unpaid AND there are errors', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError({ description: 'Visible finding' })],
          totalPotentialSavings: 500,
        })}
        hiddenErrorCount={0}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    // Beta-mode button copy lives in BETA_COPY.paywall.button.
    // Either copy should be present pre-payment.
    const paywallBtn = screen.getByRole('button', { name: /get my full report|unlock report/i });
    expect(paywallBtn).toBeInTheDocument();
  });

  it('shows paywall when only hiddenErrorCount > 0 (clean visible list)', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({ errors: [] })}
        hiddenErrorCount={3}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('+3 more hidden')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /get my full report|unlock report/i }))
      .toBeInTheDocument();
  });

  it('hides paywall when hasPaid is true', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError()],
          totalPotentialSavings: 500,
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus="success"
      />
    );
    expect(screen.queryByRole('button', { name: /get my full report|unlock report/i }))
      .not.toBeInTheDocument();
  });

  it('hides paywall when both visible and hidden error counts are zero', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis()}
        hiddenErrorCount={0}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    expect(screen.queryByRole('button', { name: /get my full report|unlock report/i }))
      .not.toBeInTheDocument();
  });
});

// ── Hidden error count teaser ─────────────────────────────────────────────────

describe('BillResultsView — hidden error count teaser', () => {
  it('renders "+N more hidden" when hiddenErrorCount > 0 and unpaid', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({ errors: [makeError()] })}
        hiddenErrorCount={5}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('+5 more hidden')).toBeInTheDocument();
  });

  it('rolls hiddenErrorCount into the summary "Issues Found" total', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({ errors: [makeError()] })}
        hiddenErrorCount={5}
        hasPaid={false}
        paymentStatus={null}
      />
    );
    // 1 visible + 5 hidden = 6 total
    const issuesCard = screen.getByText('Issues Found').closest('div')!;
    expect(issuesCard).toHaveTextContent('6');
  });
});

// ── Post-payment download surface ────────────────────────────────────────────

describe('BillResultsView — post-payment downloads', () => {
  it('shows both Download buttons when reportUrl + disputeLetterUrl present', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError()],
          reportUrl: 'user-1/bill-1/report.pdf',
          disputeLetterUrl: 'user-1/bill-1/dispute-letter.docx',
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByTestId('download-report')).toBeInTheDocument();
    expect(screen.getByTestId('download-dispute-letter')).toBeInTheDocument();
  });

  it('only shows the Report button when only reportUrl is present', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError()],
          reportUrl: 'user-1/bill-1/report.pdf',
          disputeLetterUrl: null,
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByTestId('download-report')).toBeInTheDocument();
    expect(screen.queryByTestId('download-dispute-letter')).not.toBeInTheDocument();
  });

  it('shows the report-pending state when paid but URLs not yet ready', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError()],
          reportUrl: null,
          disputeLetterUrl: null,
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus="success"
      />
    );
    // The progressive copy starts with "Generating your report…".
    expect(screen.getByText(/Generating your report/)).toBeInTheDocument();
  });
});

// ── Summary numbers ──────────────────────────────────────────────────────────

describe('BillResultsView — summary card numbers', () => {
  it('renders Total Charges with a dollar sign and 2 decimals', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({ totalCharges: 12_345.6 })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('$12345.60')).toBeInTheDocument();
  });

  it('renders Potential Savings with a dollar sign and 2 decimals', () => {
    render(
      <BillResultsView
        bill={makeBill()}
        lineItems={lineItems}
        analysis={makeAnalysis({
          errors: [makeError()],
          totalPotentialSavings: 999.99,
        })}
        hiddenErrorCount={0}
        hasPaid={true}
        paymentStatus={null}
      />
    );
    expect(screen.getByText('$999.99')).toBeInTheDocument();
  });
});
