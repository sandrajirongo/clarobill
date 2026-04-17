import Link from 'next/link';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
import { BillUploader } from '@/components/bill-uploader';
import { SavingsTracker } from '@/components/savings-tracker';
import { ReferralCard } from '@/components/referral-card';
import s from './dashboard.module.css';

const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  uploading:      { label: 'Needs review', cls: 'badgePending'  },
  pending:        { label: 'Pending',       cls: 'badgePending'  },
  ocr_processing: { label: 'Reading…',      cls: 'badgeReading'  },
  analyzing:      { label: 'Analyzing…',    cls: 'badgeReading'  },
  complete:       { label: 'Ready',         cls: 'badgeReady'    },
  failed:         { label: 'Failed',        cls: 'badgeFailed'   },
};

export default async function DashboardPage(): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  const supabase = await createSupabaseServerClient();

  const [billsResult, analysesResult, referralResult, membersResult] = await Promise.all([
    supabase
      .from('bills')
      .select('id, file_name, status, created_at')
      .order('created_at', { ascending: false }),
    supabase
      .from('analysis_results')
      .select('total_potential_savings, total_charges, errors'),
    supabase
      .from('referral_codes')
      .select('code, credits_cents')
      .eq('user_id', user!.id)
      .maybeSingle(),
    supabase
      .from('profile_members')
      .select('id', { count: 'exact', head: true })
      .eq('user_id', user!.id),
  ]);

  const bills = billsResult.data ?? [];
  const analyses = analysesResult.data ?? [];
  const referralCode = referralResult.data;
  const hasMember = (membersResult.count ?? 0) > 0;

  const totalSavings = analyses.reduce((sum, a) => sum + Number(a.total_potential_savings), 0);
  const totalErrors  = analyses.reduce((sum, a) => sum + ((a.errors as unknown[]).length), 0);
  const totalChargesReviewed = analyses.reduce((sum, a) => sum + Number(a.total_charges), 0);

  const { data: referrals } = await supabase
    .from('referrals')
    .select('status')
    .eq('referrer_user_id', user!.id);

  const convertedCount = (referrals ?? []).filter((r) => r.status === 'converted').length;

  return (
    <main className={s.page}>
      {analyses.length > 0 && (
        <SavingsTracker
          totalSavings={totalSavings}
          totalErrors={totalErrors}
          totalBills={analyses.length}
          totalChargesReviewed={totalChargesReviewed}
        />
      )}

      {/* Onboarding nudge — shown to new users before their first upload */}
      {!hasMember && bills.length === 0 && (
        <div className={s.onboardingNudge}>
          <div className={s.onboardingIcon}>👤</div>
          <div>
            <p className={s.onboardingTitle}>Set up your profile first</p>
            <p className={s.onboardingText}>
              Add yourself and your insurance plan so we can check if your provider
              billed above your insurer&apos;s contracted rate — often the biggest savings.
            </p>
          </div>
          <Link href="/dashboard/profile" className={s.onboardingBtn}>
            Set up profile →
          </Link>
        </div>
      )}

      <section>
        <h1 className={s.pageTitle}>{bills.length > 0 ? 'Analyze a New Bill' : 'Analyze a Bill'}</h1>
        <p className={s.pageSub}>Upload a medical bill, EOB, or superbill — PDF, JPEG, or PNG</p>
        <div style={{ marginTop: '1.25rem' }}>
          <BillUploader />
        </div>
      </section>

      {bills.length > 0 && (
        <section>
          <p className={s.sectionLabel}>Previous Uploads</p>
          <ul className={s.billList}>
            {bills.map((bill) => {
              const st = STATUS_BADGE[bill.status];
              const isComplete = bill.status === 'complete';
              const isUploading = bill.status === 'uploading';
              const isProcessing = bill.status === 'ocr_processing' || bill.status === 'analyzing';
              const uploadedDate = new Date(bill.created_at).toLocaleDateString('en-US', {
                month: 'short', day: 'numeric', year: 'numeric',
              });
              const deleteAfter = new Date(
                new Date(bill.created_at).getTime() + 60 * 24 * 60 * 60 * 1000
              ).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });

              return (
                <li key={bill.id} className={s.billItem}>
                  <div style={{ minWidth: 0 }}>
                    <p className={s.billName}>{bill.file_name}</p>
                    <p className={s.billMeta}>
                      Uploaded {uploadedDate}
                      {' · '}
                      <span className={s.billRetention}>Deleted {deleteAfter}</span>
                    </p>
                  </div>
                  <div className={s.billActions}>
                    <span className={`${s.badge} ${s[st?.cls ?? 'badgePending']}`}>
                      {st?.label ?? bill.status}
                    </span>
                    {isComplete && (
                      <Link href={`/dashboard/bills/${bill.id}`} className={s.viewLink}>
                        View →
                      </Link>
                    )}
                    {isUploading && (
                      <Link href={`/dashboard/bills/${bill.id}/verify`} className={s.verifyLink}>
                        Verify & Analyze →
                      </Link>
                    )}
                    {isProcessing && (
                      <Link href={`/dashboard/bills/${bill.id}`} className={s.viewLink}>
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
