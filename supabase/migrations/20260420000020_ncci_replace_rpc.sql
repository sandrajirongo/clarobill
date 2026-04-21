-- Migration: 20260420000020_ncci_replace_rpc
--
-- The --replace path in load_ncci_edits.py issues a single DELETE for all
-- rows matching (service_type, payer_type). At 2.2M rows this exceeds
-- Supabase's 30s PostgREST statement timeout.
--
-- Fix: add an index so the delete is an index scan rather than a full table
-- scan, and expose an RPC function with statement_timeout = 300s so the
-- Python script calls it via client.rpc() instead of a direct DELETE.

create index if not exists ncci_edit_pairs_service_payer_idx
  on public.ncci_edit_pairs (service_type, payer_type);

create or replace function public.delete_ncci_pairs(
  p_service_type text,
  p_payer_type   text
) returns integer language plpgsql security definer
set statement_timeout = '300s'
set search_path = public
as $$
declare
  deleted_count integer;
begin
  delete from public.ncci_edit_pairs
  where service_type = p_service_type
    and payer_type   = p_payer_type;
  get diagnostics deleted_count = row_count;
  return deleted_count;
end;
$$;
