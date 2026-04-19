import Link from 'next/link';
import { redirect } from 'next/navigation';
import { getTranslations, getLocale } from 'next-intl/server';
import { getAuthenticatedUser, createSupabaseServerClient } from '@/lib/supabase/server';
import { BillUploader } from '@/components/bill-uploader';
import { SavingsTracker } from '@/components/savings-tracker';
import { ReferralCard } from '@/components/referral-card';
import s from './dashboard.module.css';

export default async function DashboardPage(): Promise<JSX.Element> {
  const [t, locale, user] = await Promise.all([
    getTranslations('dashboard'),
    getLocale(),
    getAuthenticatedUser(),
  ]);
  const supabase = await createSupabaseServerClient();

  const { count: memberCount } = await supabase
    .from('profile_members')
    .select('id', { count: 'exact', head: true })
    .eq('user_id', user!.id);

  if (!memberCount || memberCount === 0) redirect('/onboarding');

  const [billsResult, analysesResult, referralResult] = await Promise.all([
    supabase
      .from('bills')
      .select('id, file_name, display_name, status, created_at')
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

  const totalSavings = analyses.reduce((sum, a) => sum + Number(a.total_potential_savings), 0);
  const totalErrors  = analyses.reduce((sum, a) => sum + ((a.errors as unknown[]).length), 0);
  const totalChargesReviewed = analyses.reduce((sum, a) => sum + Number(a.total_charges), 0);

  const { data: referrals } = await supabase
    .from('referrals')
    .select('status')
    .eq('referrer_user_id', user!.id);

  const convertedCount = (referrals ?? []).filter((r) => r.status === 'converted').length;

  const STATUS_LABEL: Record<string, string> = {
    uploading:      t('status.needsReview'),
    pending:        t('status.pending'),
    ocr_processing: t('status.reading'),
    analyzing:      t('status.analyzing'),
    complete:       t('status.ready'),
    failed:         t('status.failed'),
  };

  const STATUS_CLS: Record<string, string> = {
    uploading:      'badgePending',
    pending:        'badgePending',
    ocr_processing: 'badgeReading',
    analyzing:      'badgeReading',
    complete:       'badgeReady',
    failed:         'badgeFailed',
  };

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

      {bills.length === 0 && (
        <div className={s.onboardingNudge}>
          <p className={s.onboardingTitle}>{t('noBillsTitle')}</p>
          <p className={s.onboardingText}>{t('noBillsText')}</p>
        </div>
      )}

      <section>
        <h1 className={s.pageTitle}>{bills.length > 0 ? t('analyzeNewBill') : t('analyzeBill')}</h1>
        <p className={s.pageSub}>{t('analyzeSub')}</p>
        <div style={{ marginTop: '1.25rem' }}>
          <BillUploader />
        </div>
      </section>

      {bills.length > 0 && (
        <section>
          <p className={s.sectionLabel}>{t('previousUploads')}</p>
          <ul className={s.billList}>
            {bills.map((bill) => {
              const statusLabel = STATUS_LABEL[bill.status] ?? bill.status;
              const statusCls   = STATUS_CLS[bill.status] ?? 'badgePending';
              const isComplete   = bill.status === 'complete';
              const isUploading  = bill.status === 'uploading';
              const isProcessing = bill.status === 'ocr_processing' || bill.status === 'analyzing';
              const isFailed     = bill.status === 'failed';
              const uploadedDate = new Date(bill.created_at).toLocaleDateString(locale, {
                month: 'short', day: 'numeric', year: 'numeric',
              });

              return (
                <li key={bill.id} className={s.billItem}>
                  <div style={{ minWidth: 0 }}>
                    <p className={s.billName}>{bill.display_name ?? bill.file_name}</p>
                    {bill.display_name && (
                      <p className={s.billFileName}>{bill.file_name}</p>
                    )}
                    {isFailed ? (
                      <p className={s.billFailedNote}>{t('failedNote')}</p>
                    ) : (
                      <p className={s.billMeta}>{t('uploaded')} {uploadedDate}</p>
                    )}
                  </div>
                  <div className={s.billActions}>
                    <span className={`${s.badge} ${s[statusCls]}`}>
                      {statusLabel}
                    </span>
                    {isComplete && (
                      <Link href={`/dashboard/bills/${bill.id}`} className={s.viewLink}>
                        {t('view')}
                      </Link>
                    )}
                    {isUploading && (
                      <Link href={`/dashboard/bills/${bill.id}/verify`} className={s.verifyLink}>
                        {t('analyze')}
                      </Link>
                    )}
                    {isProcessing && (
                      <Link href={`/dashboard/bills/${bill.id}`} className={s.viewLink}>
                        {t('view')}
                      </Link>
                    )}
                    {isFailed && (
                      <Link href={`/dashboard/bills/${bill.id}/verify`} className={s.verifyLink}>
                        {t('retry')}
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
