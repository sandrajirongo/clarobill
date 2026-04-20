import { redirect } from 'next/navigation';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import { BillResultsView } from '@/components/bill-results-view';
import type { BillingError } from '@clarobill/shared';

interface PageProps {
  params: Promise<{ billId: string }>;
  searchParams: Promise<{ payment?: string }>;
}

// Server Component — queries Supabase directly (no HTTP self-call).
// Only the teaser (first error) is passed to the client when the user hasn't paid.
export default async function BillResultsPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  const { billId } = await params;
  const { payment } = await searchParams;

  const supabase = await createSupabaseServerClient();

  // Fetch bill — RLS enforces ownership
  const { data: bill } = await supabase
    .from('bills')
    .select('id, user_id, file_name, display_name, file_path, file_size, mime_type, status, hospital_npi, hospital_name, profile_member_id, payer_name, plan_name, plan_type, confirmed_at, created_at, updated_at')
    .eq('id', billId)
    .single();

  if (!bill) redirect('/dashboard');

  const { data: lineItems } = await supabase
    .from('line_items')
    .select('id, bill_id, cpt_code, description, service_date, quantity, unit_charge, total_charge, modifier, diagnosis_pointers')
    .eq('bill_id', billId);

  // Use the most recent analysis row. .single() would silently return null if the
  // bill was analyzed more than once (retry), so we take the latest row explicitly.
  const { data: analysis } = await supabase
    .from('analysis_results')
    .select('id, bill_id, errors, total_charges, estimated_fair_value, total_potential_savings, ai_summary, dispute_letter_url, report_url, created_at')
    .eq('bill_id', billId)
    .order('created_at', { ascending: false })
    .limit(1)
    .maybeSingle();

  const billProps = {
    id: bill.id,
    userId: bill.user_id,
    displayName: bill.display_name ?? null,
    fileName: bill.file_name,
    filePath: bill.file_path,
    fileSize: bill.file_size,
    mimeType: bill.mime_type,
    status: bill.status,
    hospitalNpi: bill.hospital_npi ?? null,
    hospitalName: bill.hospital_name ?? null,
    profileMemberId: bill.profile_member_id ?? null,
    payerName: bill.payer_name ?? null,
    planName: bill.plan_name ?? null,
    planType: (bill.plan_type ?? null) as import('@clarobill/shared').PlanType | null,
    confirmedAt: bill.confirmed_at ?? null,
    createdAt: bill.created_at,
    updatedAt: bill.updated_at,
  };

  // Analysis not ready yet — show a processing state instead of a broken redirect.
  // This handles: navigating directly to the URL while the engine is still running,
  // or refreshing the page mid-analysis.
  if (!analysis) {
    const isComplete = bill.status === 'complete';
    const inProgress = bill.status === 'ocr_processing' || bill.status === 'analyzing';

    if (inProgress) {
      return <BillResultsView
        bill={billProps}
        lineItems={[]}
        analysis={null}
        hiddenErrorCount={0}
        hasPaid={false}
        paymentStatus={payment ?? null}
      />;
    }

    // Bill is complete but analysis row is missing (engine wrote status before results,
    // or analysis was run twice and .maybeSingle() got confused). Show a no-errors
    // state rather than silently redirecting to the dashboard and losing the user.
    if (isComplete) {
      return <BillResultsView
        bill={billProps}
        lineItems={(lineItems ?? []).map((item) => ({
          id: item.id,
          billId: item.bill_id,
          cptCode: item.cpt_code,
          description: item.description,
          serviceDate: item.service_date,
          quantity: item.quantity,
          unitCharge: Number(item.unit_charge),
          totalCharge: Number(item.total_charge),
          modifier: item.modifier,
          diagnosisPointers: item.diagnosis_pointers,
        }))}
        analysis={{
          id: '',
          billId: billId,
          errors: [],
          totalCharges: 0,
          estimatedFairValue: 0,
          totalPotentialSavings: 0,
          aiSummary: '',
          disputeLetterUrl: null,
          reportUrl: null,
          createdAt: bill.updated_at,
        }}
        hiddenErrorCount={0}
        hasPaid={false}
        paymentStatus={payment ?? null}
      />;
    }

    redirect('/dashboard');
  }

  const { data: payment_record } = await supabase
    .from('payments')
    .select('status')
    .eq('bill_id', billId)
    .eq('status', 'complete')
    .maybeSingle();

  const hasPaid = payment_record !== null;

  // Sort by estimated overcharge descending so the teaser always shows the most
  // valuable finding. A zero-overcharge error as the first visible item kills
  // the paywall conversion — show the biggest dollar amount first.
  const errors = (analysis.errors as BillingError[]).sort(
    (a, b) => b.estimatedOvercharge - a.estimatedOvercharge
  );
  const visibleErrors = hasPaid ? errors : errors.slice(0, 1);
  const hiddenErrorCount = hasPaid ? 0 : Math.max(0, errors.length - 1);

  return (
    <BillResultsView
      bill={billProps}
      lineItems={(lineItems ?? []).map((item) => ({
        id: item.id,
        billId: item.bill_id,
        cptCode: item.cpt_code,
        description: item.description,
        serviceDate: item.service_date,
        quantity: item.quantity,
        unitCharge: Number(item.unit_charge),
        totalCharge: Number(item.total_charge),
        modifier: item.modifier,
        diagnosisPointers: item.diagnosis_pointers,
      }))}
      analysis={{
        id: analysis.id,
        billId: analysis.bill_id,
        errors: visibleErrors,
        totalCharges: Number(analysis.total_charges),
        estimatedFairValue: Number(analysis.estimated_fair_value),
        totalPotentialSavings: Number(analysis.total_potential_savings),
        aiSummary: analysis.ai_summary,
        disputeLetterUrl: analysis.dispute_letter_url,
        reportUrl: analysis.report_url,
        createdAt: analysis.created_at,
      }}
      hiddenErrorCount={hiddenErrorCount}
      hasPaid={hasPaid}
      paymentStatus={payment ?? null}
    />
  );
}
