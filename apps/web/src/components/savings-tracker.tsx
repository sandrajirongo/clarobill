import s from '@/app/dashboard/dashboard.module.css';

interface SavingsTrackerProps {
  totalSavings: number;
  totalErrors: number;
  totalBills: number;
  totalChargesReviewed: number;
}

export function SavingsTracker({
  totalSavings,
  totalErrors,
  totalBills,
  totalChargesReviewed,
}: SavingsTrackerProps): JSX.Element {
  return (
    <section>
      <p className={s.sectionLabel}>Your Savings Summary</p>
      <div className={s.statGrid}>
        <div className={s.statBox}>
          <p className={`${s.statValue} ${s.statValueHighlight}`}>
            ${totalSavings.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className={s.statLabel}>Potential Savings</p>
        </div>
        <div className={s.statBox}>
          <p className={s.statValue}>{totalErrors}</p>
          <p className={s.statLabel}>Errors Found</p>
        </div>
        <div className={s.statBox}>
          <p className={s.statValue}>{totalBills}</p>
          <p className={s.statLabel}>Bills Analyzed</p>
        </div>
        <div className={s.statBox}>
          <p className={s.statValue}>
            ${totalChargesReviewed.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </p>
          <p className={s.statLabel}>Charges Reviewed</p>
        </div>
      </div>
    </section>
  );
}
