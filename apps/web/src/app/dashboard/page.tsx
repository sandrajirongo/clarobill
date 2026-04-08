import Link from 'next/link';
import { createSupabaseServerClient } from '@/lib/supabase/server';
import { BillUploader } from '@/components/bill-uploader';

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  pending:       { label: 'Pending',    className: 'bg-gray-100 text-gray-500' },
  ocr_processing:{ label: 'Reading…',  className: 'bg-blue-50 text-blue-600' },
  analyzing:     { label: 'Analyzing…',className: 'bg-blue-50 text-blue-600' },
  complete:      { label: 'Ready',      className: 'bg-green-50 text-green-700' },
  failed:        { label: 'Failed',     className: 'bg-red-50 text-red-600' },
};

export default async function DashboardPage(): Promise<JSX.Element> {

  const supabase = await createSupabaseServerClient();
  const { data: bills } = await supabase
    .from('bills')
    .select('id, file_name, status, created_at')
    .order('created_at', { ascending: false });

  const hasBills = bills && bills.length > 0;

  return (
    <main className="max-w-3xl mx-auto px-6 py-8 space-y-10">

      {/* Upload section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">
              {hasBills ? 'Analyze a New Bill' : 'Your Bills'}
            </h1>
            <p className="text-sm text-gray-400 mt-0.5">
              Upload a medical bill, EOB, or superbill — PDF, JPEG, or PNG
            </p>
          </div>
        </div>
        <BillUploader />
      </section>

      {/* Previous analyses */}
      {hasBills && (
        <section>
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-4">
            Previous Analyses
          </h2>
          <ul className="space-y-2">
            {bills!.map((bill) => {
              const status = STATUS_LABELS[bill.status] ?? STATUS_LABELS['pending'];
              const isComplete = bill.status === 'complete';
              const date = new Date(bill.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              });

              return (
                <li
                  key={bill.id}
                  className="bg-white rounded-xl border border-gray-100 shadow-sm px-5 py-4 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{bill.file_name}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{date}</p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${status?.className ?? 'bg-gray-100 text-gray-500'}`}>
                      {status?.label ?? bill.status}
                    </span>
                    {isComplete && (
                      <Link
                        href={`/dashboard/bills/${bill.id}`}
                        className="text-xs font-semibold text-teal-600 hover:text-teal-700 transition-colors"
                      >
                        View Analysis →
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </main>
  );
}
