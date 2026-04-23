import Link from 'next/link';
import { getTranslations, getLocale } from 'next-intl/server';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import { DownloadButton } from '@/components/download-button';
import s from '../dashboard.module.css';

export default async function ReportsPage(): Promise<JSX.Element> {
  const [t, locale, supabase] = await Promise.all([
    getTranslations('reports'),
    getLocale(),
    createSupabaseServerClient(),
  ]);

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
        display_name,
        payments ( amount_cents, status )
      )
    `)
    .order('created_at', { ascending: false });

  const allResults = results ?? [];

  return (
    <main className={s.page}>
      <div>
        <h1 className={s.pageTitle}>{t('title')}</h1>
        <p className={s.pageSub}>{t('subtitle')}</p>
      </div>

      {allResults.length === 0 ? (
        <div className={s.emptyState}>
          <p className={s.emptyText}>
            {t('emptyText')}<br />
            {t('emptySubtext')}
          </p>
          <Link href="/dashboard" className={s.emptyAction}>{t('analyzeBill')}</Link>
        </div>
      ) : (
        <ul style={{ display: 'flex', flexDirection: 'column', gap: '.75rem', listStyle: 'none', padding: 0, margin: 0 }}>
          {allResults.map((result) => {
            const bill = result.bills as unknown as {
              id: string;
              file_name: string;
              display_name: string | null;
              payments: Array<{ amount_cents: number; status: string }>;
            } | null;

            const fileName = bill?.display_name ?? bill?.file_name ?? 'Unknown bill';
            const payment = bill?.payments?.[0];
            const amountPaid = payment
              ? payment.amount_cents === 0 ? t('free') : `$${(payment.amount_cents / 100).toFixed(2)}`
              : t('free');
            const generatedDate = new Date(result.created_at).toLocaleDateString(locale, {
              month: 'short', day: 'numeric', year: 'numeric',
            });
            const isClean = !result.report_url && !result.dispute_letter_url;

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
                        {t('potentialSavings', { amount: `$${Number(result.total_potential_savings).toFixed(2)}` })}
                      </p>
                    )}
                    {isClean && (
                      <p className={s.reportSavings}>{t('cleanBill')}</p>
                    )}
                  </div>
                  <div className={s.reportBtns}>
                    {result.report_url && (
                      <DownloadButton billId={result.bill_id} type="report" label={`↓ ${t('report')}`} className={s.dlBtn} />
                    )}
                    {result.dispute_letter_url && (
                      <DownloadButton billId={result.bill_id} type="dispute-letter" label={`↓ ${t('disputeLetter')}`} className={s.dlBtn} />
                    )}
                    {isClean && (
                      <Link href={`/dashboard/bills/${result.bill_id}`} className={s.dlBtn}>
                        {t('viewResults')}
                      </Link>
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

