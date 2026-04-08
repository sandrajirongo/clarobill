import Link from 'next/link';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import s from '../dashboard.module.css';

export default async function ReportsPage(): Promise<JSX.Element> {
  const supabase = await createSupabaseServerClient();

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
    <main className={s.page}>
      <div>
        <h1 className={s.pageTitle}>Reports & Dispute Letters</h1>
        <p className={s.pageSub}>Download your full analysis and ready-to-send dispute letter</p>
      </div>

      {reportsWithDocs.length === 0 ? (
        <div className={s.emptyState}>
          <p className={s.emptyText}>
            No reports generated yet.<br />
            Reports and dispute letters appear here after you unlock a full analysis.
          </p>
          <Link href="/dashboard" className={s.emptyAction}>Analyze a bill</Link>
        </div>
      ) : (
        <ul style={{ display: 'flex', flexDirection: 'column', gap: '.75rem', listStyle: 'none', padding: 0, margin: 0 }}>
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
              <li key={result.id} className={s.reportItem}>
                <div className={s.reportTop}>
                  <div style={{ minWidth: 0 }}>
                    <Link href={`/dashboard/bills/${result.bill_id}`} className={s.reportName}>
                      {fileName}
                    </Link>
                    <p className={s.reportMeta}>{generatedDate} · {amountPaid}</p>
                    {Number(result.total_potential_savings) > 0 && (
                      <p className={s.reportSavings}>
                        ${Number(result.total_potential_savings).toFixed(2)} potential savings identified
                      </p>
                    )}
                  </div>
                  <div className={s.reportBtns}>
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
      className={s.dlBtn}
    >
      ↓ {label}
    </a>
  );
}
