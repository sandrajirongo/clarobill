import { redirect } from 'next/navigation';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import { BillVerification } from '@/components/bill-verification';

interface PageProps {
  params: Promise<{ billId: string }>;
}

// Server Component — loads bill details to pass to the verification wizard.
// If the bill is already confirmed (confirmed_at set) or analysis has moved past
// 'uploading', we skip straight to results so users can't re-verify.
export default async function VerifyPage({ params }: PageProps): Promise<JSX.Element> {
  const user = await getAuthenticatedUser();
  if (!user) redirect('/auth/sign-in');

  const { billId } = await params;
  const supabase = await createSupabaseServerClient();

  const { data: bill } = await supabase
    .from('bills')
    .select('id, file_name, status, hospital_name, confirmed_at')
    .eq('id', billId)
    .single();

  if (!bill) redirect('/dashboard');

  // Redirect to results if already confirmed and past uploading.
  // Allow 'failed' through so users can retry without re-uploading.
  const canVerify = bill.status === 'uploading' || bill.status === 'failed';
  if (!canVerify) {
    redirect(`/dashboard/bills/${billId}`);
  }

  return (
    <BillVerification
      billId={billId}
      fileName={bill.file_name}
      ocrHospitalName={bill.hospital_name ?? null}
    />
  );
}
