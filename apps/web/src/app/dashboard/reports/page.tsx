import Link from 'next/link';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export default async function ReportsPage(): Promise<JSX.Element> {
  const supabase = await createSupabaseServerClient();

  // Load analysis results that have at least one generated document,
  // joined with the bill for the file name and payment amount.
  const { data: results } = await supabase
    .from('analysis_results')
    .select(`
      id,
      bill_id,
      report_url,
      dispute_letter_url,
      total_charges,
      total_potential_savings,
      created_at,
      bills (
        id,
        file_name,
        payments ( amount_cents, status )
      )
    `)
    .order('created_at', { ascending: false });

  const reportsWithDocs = (results ?? []).filter(
    (r) => r.report_url || r.dispute_letter_url
  );

  return (
    <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Reports & Dispute Letters</h1>

      {reportsWithDocs.length === 0 ? (
        <EmptyState />
      ) : (
        <ul className="space-y-3">
          {reportsWithDocs.map((result) => {
            const bill = result.bills as unknown as {
              id: string;
              file_name: string;
              payments: Array<{ amount_cents: number; status: string }>;
            } | null;

            const fileName = bill?.file_name ?? 'Unknown bill';
            const payment = bill?.payments?.[0];
            const amountPaid = payment
              ? payment.amount_cents === 0 ? 'Free' : `$${(payment.amount_cents / 100).toFixed(2)}`
              : 'Free';

            const generatedDate = new Date(result.created_at).toLocaleDateString('en-US', {
              month: 'short', day: 'numeric', year: 'numeric',
            });

            return (
              <li key={result.id} className="bg-white rounded-2xl border border-slate-100 shadow-sm px-6 py-5">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <Link
                      href={`/dashboard/bills/${result.bill_id}`}
                      className="text-sm font-semibold text-slate-900 hover:text-brand-600 transition-colors truncate block"
                    >
                      {fileName}
                    </Link>
                    <p className="text-xs text-slate-400 mt-0.5">{generatedDate} · {amountPaid}</p>
                    {Number(result.total_potential_savings) > 0 && (
                      <p className="text-xs text-green-700 font-medium mt-1">
                        ${Number(result.total_potential_savings).toFixed(2)} potential savings identified
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2 shrink-0">
                    {result.report_url && (
                      <DownloadButton billId={result.bill_id} type="report" label="Report" />
                    )}
                    {result.dispute_letter_url && (
                      <DownloadButton billId={result.bill_id} type="dispute-letter" label="Dispute Letter" />
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </main>
  );
}

// Server-rendered placeholder; actual download requires a signed URL fetched client-side.
// We render an anchor that links to the download API route so it works without JS.
function DownloadButton({
  billId,
  type,
  label,
}: {
  billId: string;
  type: 'report' | 'dispute-letter';
  label: string;
}): JSX.Element {
  return (
    <a
      href={`/api/bills/${billId}/download?type=${type}`}
      target="_blank"
      rel="noopener noreferrer"
      className="text-xs font-semibold text-brand-600 border border-brand-600/20 bg-brand-50 rounded-lg px-3 py-2 hover:bg-brand-100 transition-colors"
    >
      ↓ {label}
    </a>
  );
}

function EmptyState(): JSX.Element {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm px-6 py-16 text-center">
      <p className="text-slate-400 text-sm">No reports generated yet.</p>
      <p className="text-slate-400 text-sm mt-1">
        Reports and dispute letters appear here after you unlock a full analysis.
      </p>
      <Link
        href="/dashboard"
        className="inline-block mt-4 bg-brand-600 text-white text-sm font-semibold rounded-lg px-5 py-2.5 hover:bg-brand-700 transition-colors"
      >
        Analyze a bill
      </Link>
    </div>
  );
}
