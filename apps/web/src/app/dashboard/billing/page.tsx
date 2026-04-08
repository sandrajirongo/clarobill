import Link from 'next/link';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export default async function BillingPage(): Promise<JSX.Element> {
  const supabase = await createSupabaseServerClient();

  // Join payments with bills to get the file name per payment
  const { data: payments } = await supabase
    .from('payments')
    .select('id, bill_id, amount_cents, currency, status, created_at, bills(file_name)')
    .order('created_at', { ascending: false });

  return (
    <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <h1 className="text-xl font-semibold text-slate-900">Billing History</h1>

      {!payments || payments.length === 0 ? (
        <EmptyState />
      ) : (
        <section className="bg-white rounded-2xl border border-slate-100 shadow-sm overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-100 bg-slate-50">
                <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wide px-6 py-3">Date</th>
                <th className="text-left text-xs font-semibold text-slate-500 uppercase tracking-wide px-6 py-3">Bill</th>
                <th className="text-right text-xs font-semibold text-slate-500 uppercase tracking-wide px-6 py-3">Amount</th>
                <th className="text-right text-xs font-semibold text-slate-500 uppercase tracking-wide px-6 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {payments.map((payment) => {
                const billName = (payment.bills as unknown as { file_name: string } | null)?.file_name ?? 'Bill';
                const amount = payment.amount_cents === 0
                  ? 'Free'
                  : `$${(payment.amount_cents / 100).toFixed(2)}`;
                const date = new Date(payment.created_at).toLocaleDateString('en-US', {
                  month: 'short', day: 'numeric', year: 'numeric',
                });

                return (
                  <tr key={payment.id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-6 py-4 text-slate-500 whitespace-nowrap">{date}</td>
                    <td className="px-6 py-4 text-slate-900 max-w-xs">
                      {payment.bill_id ? (
                        <Link
                          href={`/dashboard/bills/${payment.bill_id}`}
                          className="hover:text-brand-600 transition-colors truncate block"
                        >
                          {billName}
                        </Link>
                      ) : (
                        <span className="text-slate-400 truncate block">{billName}</span>
                      )}
                    </td>
                    <td className="px-6 py-4 text-right font-medium text-slate-900 whitespace-nowrap">
                      {amount}
                    </td>
                    <td className="px-6 py-4 text-right whitespace-nowrap">
                      <StatusBadge status={payment.status} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  );
}

function StatusBadge({ status }: { status: string }): JSX.Element {
  const styles: Record<string, string> = {
    complete: 'bg-green-50 text-green-700',
    pending:  'bg-amber-50 text-amber-700',
    failed:   'bg-red-50 text-red-600',
    refunded: 'bg-slate-100 text-slate-500',
  };
  const labels: Record<string, string> = {
    complete: 'Paid',
    pending:  'Pending',
    failed:   'Failed',
    refunded: 'Refunded',
  };
  return (
    <span className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-full ${styles[status] ?? 'bg-slate-100 text-slate-500'}`}>
      {labels[status] ?? status}
    </span>
  );
}

function EmptyState(): JSX.Element {
  return (
    <div className="bg-white rounded-2xl border border-slate-100 shadow-sm px-6 py-16 text-center">
      <p className="text-slate-400 text-sm">No payments yet.</p>
      <p className="text-slate-400 text-sm mt-1">
        Your billing history will appear here after you unlock a full report.
      </p>
    </div>
  );
}
