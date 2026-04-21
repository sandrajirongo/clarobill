/**
 * process-deleted-bill-files
 *
 * Deletes uploaded bill documents from Supabase Storage after the 60-day
 * retention period. Runs after the expire_bill_files() pg_cron job has
 * nulled out file_path on expired bill rows and queued those paths in
 * public.deleted_bill_files.
 *
 * Schedule: 02:15 UTC daily (15 minutes after the pg_cron retention job).
 * Configure in: Supabase Dashboard → Edge Functions → Cron schedule
 *   Cron expression: 15 2 * * *
 *
 * Required environment variables (auto-injected by Supabase):
 *   SUPABASE_URL
 *   SUPABASE_SERVICE_ROLE_KEY
 */

import { createClient } from 'https://esm.sh/@supabase/supabase-js@2';

const BATCH_SIZE = 100;

Deno.serve(async () => {
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!,
  );

  const { data: queued, error: fetchError } = await supabase
    .from('deleted_bill_files')
    .select('id, file_path')
    .order('queued_at', { ascending: true })
    .limit(BATCH_SIZE);

  if (fetchError) {
    console.error('Failed to fetch deletion queue:', fetchError.message);
    return new Response(JSON.stringify({ error: fetchError.message }), { status: 500 });
  }

  if (!queued || queued.length === 0) {
    return new Response(JSON.stringify({ deleted: 0 }), { status: 200 });
  }

  const filePaths = queued.map((row: { id: string; file_path: string }) => row.file_path);
  const rowIds = queued.map((row: { id: string; file_path: string }) => row.id);

  const { error: storageError } = await supabase.storage
    .from('bills')
    .remove(filePaths);

  if (storageError) {
    console.error('Storage deletion failed:', storageError.message);
    return new Response(JSON.stringify({ error: storageError.message }), { status: 500 });
  }

  const { error: clearError } = await supabase
    .from('deleted_bill_files')
    .delete()
    .in('id', rowIds);

  if (clearError) {
    console.error('Failed to clear deletion queue:', clearError.message);
    return new Response(JSON.stringify({ error: clearError.message }), { status: 500 });
  }

  console.log(`Deleted ${filePaths.length} bill files from storage.`);
  return new Response(JSON.stringify({ deleted: filePaths.length }), { status: 200 });
});
