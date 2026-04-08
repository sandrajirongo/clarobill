import Link from 'next/link';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import s from '../dashboard.module.css';

export default async function BillingPage(): Promise<JSX.Element> {
  const supabase = await createSupabaseServerClient();

  const { data: payments } = await supabase
    .from('payments')
    .select('id, bill_id, amount_cents, currency, status, created_at, bills(file_name)')
    .order('created_at', { ascending: false });

  return (
    <main className={s.page}>
      <div>
        <h1 className={s.pageTitle}>Billing History</h1>
        <p className={s.pageSub}>All payments and reports unlocked</p>
      </div>

      {!payments || payments.length === 0 ? (
        <div className={s.emptyState}>
          <p className={s.emptyText}>
            No payments yet.<br />
            Your billing history will appear here after you unlock a full report.
          </p>
        </div>
      ) : (
        <div className={s.card}>
          <table className={s.table}>
            <thead className={s.tableHead}>
              <tr>
                <th className={s.th}>Date</th>
                <th className={s.th}>Bill</th>
                <th className={`${s.th} ${s.tdRight}`}>Amount</th>
                <th className={`${s.th} ${s.tdRight}`}>Status</th>
              </tr>
            </thead>
            <tbody>
              {payments.map((payment) => {
                const billName = (payment.bills as unknown as { file_name: string } | null)?.file_name ?? 'Bill';
                const amount = payment.amount_cents === 0
                  ? 'Free'
                  : `$${(payment.amount_cents / 100).toFixed(2)}`;
                const date = new Date(payment.created_at).toLocaleDateString('en-US', {
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
                      <StatusBadge status={payment.status} />
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

function StatusBadge({ status }: { status: string }): JSX.Element {
  const cls: Record<string, string> = {
    complete: s.badgeReady,
    pending:  s.badgePending,
    failed:   s.badgeFailed,
    refunded: s.badgePending,
  };
  const labels: Record<string, string> = {
    complete: 'Paid',
    pending:  'Pending',
    failed:   'Failed',
    refunded: 'Refunded',
  };
  return (
    <span className={`${s.badge} ${cls[status] ?? s.badgePending}`}>
      {labels[status] ?? status}
    </span>
  );
}
