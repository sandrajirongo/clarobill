import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { BillAnalysisResponse, ApiErrorResponse } from '@clarobill/shared';

// GET /api/bills/[billId]/analysis
// Returns the full bill analysis — bill, line items, and analysis result.
// Used by the results page to render findings and the paywall.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ billId: string }> }
): Promise<NextResponse<BillAnalysisResponse | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { billId } = await params;
  const supabase = await createSupabaseServerClient();

  // RLS ensures users can only access their own bills
  const { data: bill, error: billError } = await supabase
    .from('bills')
    .select('id, user_id, file_name, file_path, file_size, mime_type, status, hospital_npi, hospital_name, profile_member_id, payer_name, plan_name, confirmed_at, created_at, updated_at')
    .eq('id', billId)
    .single();

  if (billError || !bill) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Bill not found.', step: 'fetch_bill' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  const { data: lineItems } = await supabase
    .from('line_items')
    .select('id, bill_id, cpt_code, description, service_date, quantity, unit_charge, total_charge, modifier, diagnosis_pointers')
    .eq('bill_id', billId);

  const { data: analysis } = await supabase
    .from('analysis_results')
    .select('id, bill_id, errors, total_charges, estimated_fair_value, total_potential_savings, ai_summary, dispute_letter_url, report_url, created_at')
    .eq('bill_id', billId)
    .single();

  if (!analysis) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis not yet available.', step: 'fetch_analysis' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  return NextResponse.json({
    bill: {
      id: bill.id,
      userId: bill.user_id,
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
      confirmedAt: bill.confirmed_at ?? null,
      createdAt: bill.created_at,
      updatedAt: bill.updated_at,
    },
    lineItems: (lineItems ?? []).map((item) => ({
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
    })),
    analysis: {
      id: analysis.id,
      billId: analysis.bill_id,
      errors: analysis.errors,
      totalCharges: Number(analysis.total_charges),
      estimatedFairValue: Number(analysis.estimated_fair_value),
      totalPotentialSavings: Number(analysis.total_potential_savings),
      aiSummary: analysis.ai_summary,
      disputeLetterUrl: analysis.dispute_letter_url,
      reportUrl: analysis.report_url,
      createdAt: analysis.created_at,
    },
  } satisfies BillAnalysisResponse);
}
