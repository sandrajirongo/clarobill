import Link from 'next/link';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
import { BillUploader } from '@/components/bill-uploader';
import { SavingsTracker } from '@/components/savings-tracker';
import { ReferralCard } from '@/components/referral-card';

const STATUS_LABELS: Record<string, { label: string; className: string }> = {
  pending:        { label: 'Pending',     className: 'bg-slate-100 text-slate-500' },
  ocr_processing: { label: 'Reading…',   className: 'bg-blue-50 text-blue-600' },
  analyzing:      { label: 'Analyzing…', className: 'bg-blue-50 text-blue-600' },
  complete:       { label: 'Ready',       className: 'bg-green-50 text-green-700' },
  failed:         { label: 'Failed',      className: 'bg-red-50 text-red-600' },
};

export default async function DashboardPage(): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  const supabase = await createSupabaseServerClient();

  // Fetch bills, analyses, and referral data in parallel
  const [billsResult, analysesResult, referralResult] = await Promise.all([
    supabase
      .from('bills')
      .select('id, file_name, status, created_at, delete_after')
      .order('created_at', { ascending: false }),

    supabase
      .from('analysis_results')
      .select('total_potential_savings, total_charges, errors'),

    supabase
      .from('referral_codes')
      .select('code, credits_cents')
      .eq('user_id', user!.id)
      .maybeSingle(),
  ]);

  const bills = billsResult.data ?? [];
  const analyses = analysesResult.data ?? [];
  const referralCode = referralResult.data;

  // Aggregate savings stats
  const totalSavings = analyses.reduce(
    (sum, a) => sum + Number(a.total_potential_savings), 0
  );
  const totalErrors = analyses.reduce(
    (sum, a) => sum + ((a.errors as unknown[]).length), 0
  );
  const totalChargesReviewed = analyses.reduce(
    (sum, a) => sum + Number(a.total_charges), 0
  );

  // Completed referrals for this user
  const { data: referrals } = await supabase
    .from('referrals')
    .select('status')
    .eq('referrer_user_id', user!.id);

  const convertedCount = (referrals ?? []).filter((r) => r.status === 'converted').length;

  const hasBills = bills.length > 0;
  const hasAnalyses = analyses.length > 0;

  return (
    <main className="max-w-3xl mx-auto px-6 py-8 space-y-10">

      {/* Savings tracker — only shown when there is something to show */}
      {hasAnalyses && (
        <SavingsTracker
          totalSavings={totalSavings}
          totalErrors={totalErrors}
          totalBills={analyses.length}
          totalChargesReviewed={totalChargesReviewed}
        />
      )}

      {/* Upload */}
      <section>
        <div className="mb-4">
          <h1 className="text-xl font-semibold text-slate-900">
            {hasBills ? 'Analyze a New Bill' : 'Your Bills'}
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Upload a medical bill, EOB, or superbill — PDF, JPEG, or PNG
          </p>
        </div>
        <BillUploader />
      </section>

      {/* Previous bills */}
      {hasBills && (
        <section>
          <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">
            Previous Uploads
          </h2>
          <ul className="space-y-2">
            {bills.map((bill) => {
              const status = STATUS_LABELS[bill.status];
              const isComplete = bill.status === 'complete';

              const uploadedDate = new Date(bill.created_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
              });

              const deleteAfter = bill.delete_after
                ? new Date(bill.delete_after as string).toLocaleDateString('en-US', {
                    month: 'short', day: 'numeric', year: 'numeric',
                  })
                : null;

              return (
                <li
                  key={bill.id}
                  className="bg-white rounded-xl border border-slate-100 shadow-sm px-5 py-4 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-900 truncate">{bill.file_name}</p>
                    <p className="text-xs text-slate-400 mt-0.5">
                      Uploaded {uploadedDate}
                      {deleteAfter && (
                        <> · <span className="text-amber-500">File deleted {deleteAfter}</span></>
                      )}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-xs font-medium px-2.5 py-1 rounded-full ${status?.className ?? 'bg-slate-100 text-slate-500'}`}>
                      {status?.label ?? bill.status}
                    </span>
                    {isComplete && (
                      <Link
                        href={`/dashboard/bills/${bill.id}`}
                        className="text-xs font-semibold text-brand-600 hover:text-brand-700 transition-colors"
                      >
                        View →
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* Referral card — shown once user has a referral code (after migration runs) */}
      {referralCode && (
        <ReferralCard
          referralCode={referralCode.code}
          convertedCount={convertedCount}
          creditsEarned={referralCode.credits_cents}
        />
      )}

    </main>
  );
}
