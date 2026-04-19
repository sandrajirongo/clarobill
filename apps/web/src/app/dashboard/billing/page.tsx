import Link from 'next/link';
import { getTranslations, getLocale } from 'next-intl/server';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import s from '../dashboard.module.css';

export default async function BillingPage(): Promise<JSX.Element> {
  const [t, locale, supabase] = await Promise.all([
    getTranslations('billing'),
    getLocale(),
    createSupabaseServerClient(),
  ]);

  const { data: payments } = await supabase
    .from('payments')
    .select('id, bill_id, amount_cents, currency, status, created_at, bills(file_name)')
    .order('created_at', { ascending: false });

  const statusLabel = (status: string): string => {
    if (status === 'complete') return t('paid');
    if (status === 'pending')  return t('pending');
    if (status === 'failed')   return t('failed');
    if (status === 'refunded') return t('refunded');
    return status;
  };

  const statusCls = (status: string): string =>
    status === 'complete' ? (s.badgeReady ?? '') :
    status === 'failed'   ? (s.badgeFailed ?? '') :
    (s.badgePending ?? '');

  return (
    <main className={s.page}>
      <div>
        <h1 className={s.pageTitle}>{t('title')}</h1>
        <p className={s.pageSub}>{t('subtitle')}</p>
      </div>

      {!payments || payments.length === 0 ? (
        <div className={s.emptyState}>
          <p className={s.emptyText}>
            {t('emptyText')}<br />
            {t('emptySubtext')}
          </p>
        </div>
      ) : (
        <div className={s.card}>
          <table className={s.table}>
            <thead className={s.tableHead}>
              <tr>
                <th className={s.th}>{t('date')}</th>
                <th className={s.th}>{t('bill')}</th>
                <th className={`${s.th} ${s.tdRight}`}>{t('amount')}</th>
                <th className={`${s.th} ${s.tdRight}`}>{t('status')}</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((payment) => {
                const billName = (payment.bills as unknown as { file_name: string } | null)?.file_name ?? t('bill');
                const amount = payment.amount_cents === 0
                  ? t('free')
                  : `$${(payment.amount_cents / 100).toFixed(2)}`;
                const date = new Date(payment.created_at).toLocaleDateString(locale, {
                  month: 'short', day: 'numeric', year: 'numeric',
                });

                return (
                  <tr key={payment.id} className={s.tr}>
                    <td className={s.td}>{date}</td>
                    <td className={`${s.td} ${s.tdName}`}>
                      {payment.bill_id ? (
                        <Link href={`/dashboard/bills/${payment.bill_id}`} className={s.tableLink}>
                          {billName}
                        </Link>
                      ) : (
                        <span>{billName}</span>
                      )}
                    </td>
                    <td className={`${s.td} ${s.tdAmount}`}>{amount}</td>
                    <td className={`${s.td} ${s.tdRight}`}>
                      <span className={`${s.badge} ${statusCls(payment.status)}`}>
                        {statusLabel(payment.status)}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}
