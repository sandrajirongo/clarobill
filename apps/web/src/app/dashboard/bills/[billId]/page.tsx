import { redirect } from 'next/navigation';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { BillAnalysisResponse } from '@clarobill/shared';
import { BillResultsView } from '@/components/bill-results-view';

interface PageProps {
  params: Promise<{ billId: string }>;
  searchParams: Promise<{ payment?: string }>;
}

// Server Component — fetches analysis and payment status server-side.
// Only the teaser (first error) is passed to the client when the user hasn't paid.
export default async function BillResultsPage({ params, searchParams }: PageProps): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  const { billId } = await params;
  const { payment } = await searchParams;

  const supabase = await createSupabaseServerClient();

  // Fetch full analysis (RLS enforces ownership)
  const analysisRes = await fetch(
    `${process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000'}/api/bills/${billId}/analysis`,
    { headers: { Cookie: '' }, cache: 'no-store' }
  );

  if (!analysisRes.ok) redirect('/dashboard');

  const data: BillAnalysisResponse = await analysisRes.json();

  // Check if the user has a completed payment for this bill
  const { data: payment_record } = await supabase
    .from('payments')
    .select('status')
    .eq('bill_id', billId)
    .eq('status', 'complete')
    .maybeSingle();

  const hasPaid = payment_record !== null;

  // Enforce the paywall at the data layer — only pass all errors if paid
  const visibleErrors = hasPaid ? data.analysis.errors : data.analysis.errors.slice(0, 1);
  const hiddenErrorCount = hasPaid ? 0 : Math.max(0, data.analysis.errors.length - 1);

  return (
    <BillResultsView
      bill={data.bill}
      lineItems={data.lineItems}
      analysis={{ ...data.analysis, errors: visibleErrors }}
      hiddenErrorCount={hiddenErrorCount}
      hasPaid={hasPaid}
      paymentStatus={payment ?? null}
    />
  );
}
