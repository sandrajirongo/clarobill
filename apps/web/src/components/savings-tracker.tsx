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
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-4">
        Your Savings Summary
      </h2>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <StatCard
          label="Potential Savings"
          value={`$${totalSavings.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
          highlight
        />
        <StatCard
          label="Errors Found"
          value={String(totalErrors)}
        />
        <StatCard
          label="Bills Analyzed"
          value={String(totalBills)}
        />
        <StatCard
          label="Charges Reviewed"
          value={`$${totalChargesReviewed.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`}
        />
      </div>
    </section>
  );
}

function StatCard({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}): JSX.Element {
  return (
    <div className="bg-white rounded-xl border border-slate-100 shadow-sm px-4 py-4 text-center">
      <p className={`text-lg font-bold ${highlight ? 'text-brand-600' : 'text-slate-900'}`}>
        {value}
      </p>
      <p className="text-2xs text-slate-400 uppercase tracking-wide mt-1">{label}</p>
    </div>
  );
}
