import { NextResponse } from 'next/server';
import { createSupabaseServerClient, createSupabaseServiceClient, getAuthenticatedUser } from '@/lib/supabase/server';
import type { BillUploadResponse, ApiErrorResponse } from '@clarobill/shared';

const STORAGE_BUCKET = 'bills';

// POST /api/bills/upload
// Returns a signed upload URL so the client can PUT the file directly to
// Supabase Storage without routing file bytes through this server.
export async function POST(request: Request): Promise<NextResponse<BillUploadResponse | ApiErrorResponse>> {
  const user = await getAuthenticatedUser();

  if (!user) {
    return NextResponse.json(
      {
        error: { code: 'UNAUTHORIZED', detail: 'You must be signed in to upload a bill.' },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 401 }
    );
  }

  let body: { fileName: string; fileSize: number; mimeType: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      {
        error: { code: 'ANALYSIS_FAILED', detail: 'Invalid request body.', step: 'upload' },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 400 }
    );
  }

  const { fileName, fileSize, mimeType } = body;

  if (fileSize > 20 * 1024 * 1024) {
    return NextResponse.json(
      {
        error: { code: 'FILE_TOO_LARGE', detail: 'File exceeds 20MB limit.', maxBytes: 20971520 },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 413 }
    );
  }

  const allowedMimeTypes = ['application/pdf', 'image/jpeg', 'image/png'];
  if (!allowedMimeTypes.includes(mimeType)) {
    return NextResponse.json(
      {
        error: { code: 'INVALID_FILE_TYPE', detail: 'Only PDF, JPEG, and PNG files are accepted.', receivedType: mimeType },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 415 }
    );
  }

  const supabase = await createSupabaseServerClient();

  // Create the bill record first so we have the ID for the storage path.
  // The storage path is scoped by user ID to enforce isolation at the filesystem level.
  const { data: bill, error: billError } = await supabase
    .from('bills')
    .insert({
      user_id: user.id,
      file_name: fileName,
      file_path: `${user.id}/placeholder`, // Updated after we know the billId
      file_size: fileSize,
      mime_type: mimeType,
      status: 'uploading',
    })
    .select('id')
    .single();

  if (billError || !bill) {
    console.error('[bills/upload] Failed to create bill record', { userId: user.id, error: billError?.message });
    return NextResponse.json(
      {
        error: { code: 'ANALYSIS_FAILED', detail: 'Failed to initialize upload. Please try again.', step: 'bill_create' },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  // Storage path: {userId}/{billId}/{fileName} — RLS policy on the bucket enforces userId
  const filePath = `${user.id}/${bill.id}/${fileName}`;

  // Update the bill record with the real file path
  await supabase
    .from('bills')
    .update({ file_path: filePath })
    .eq('id', bill.id);

  // Create a signed upload URL using the service role client —
  // the anon key lacks permission to create signed upload URLs.
  const serviceClient = createSupabaseServiceClient();
  const { data: signedUpload, error: signedError } = await serviceClient
    .storage
    .from(STORAGE_BUCKET)
    .createSignedUploadUrl(filePath);

  if (signedError || !signedUpload) {
    console.error('[bills/upload] Failed to create signed URL', { billId: bill.id, error: signedError?.message });
    return NextResponse.json(
      {
        error: { code: 'ANALYSIS_FAILED', detail: 'Failed to prepare upload. Please try again.', step: 'signed_url' },
        requestId: crypto.randomUUID(),
      } satisfies ApiErrorResponse,
      { status: 500 }
    );
  }

  return NextResponse.json(
    { billId: bill.id, uploadUrl: signedUpload.signedUrl } satisfies BillUploadResponse,
    { status: 200 }
  );
}
