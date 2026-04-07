import { NextResponse } from 'next/server';
import { createSupabaseServerClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { ApiErrorResponse } from '@medscan/shared';

// GET /api/bills/[billId]/download?type=report|dispute-letter
// Generates a short-lived signed URL for private Supabase Storage objects.
// PHI — the 'reports' bucket is private; never expose storage paths directly.
export async function GET(
  request: Request,
  { params }: { params: Promise<{ billId: string }> }
): Promise<NextResponse<{ url: string } | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();
  if (!user) {
    return NextResponse.json(
      { error: { code: 'UNAUTHORIZED', detail: 'Authentication required.' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  const { billId } = await params;
  const { searchParams } = new URL(request.url);
  const type = searchParams.get('type');

  if (type !== 'report' && type !== 'dispute-letter') {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Invalid download type.', step: 'download' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const supabase = await createSupabaseServerClient();

  // Verify ownership via RLS before generating the signed URL
  const { data: analysis } = await supabase
    .from('analysis_results')
    .select('report_url, dispute_letter_url, bill_id')
    .eq('bill_id', billId)
    .single();

  if (!analysis) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Analysis not found.', step: 'download' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  const storagePath = type === 'report' ? analysis.report_url : analysis.dispute_letter_url;

  if (!storagePath) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Document not yet generated.', step: 'download' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 404 }
    );
  }

  // Signed URL valid for 60 seconds — enough to open in a new tab
  const { data: signedUrl, error } = await supabase.storage
    .from('reports')
    .createSignedUrl(storagePath, 60);

  if (error || !signedUrl?.signedUrl) {
    return NextResponse.json(
      { error: { code: 'ANALYSIS_FAILED', detail: 'Could not generate download link.', step: 'download' }, requestId: crypto.randomUUID() } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json({ url: signedUrl.signedUrl });
}
