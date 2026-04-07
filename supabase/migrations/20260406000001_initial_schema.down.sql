-- Rollback: 20260406000001_initial_schema
drop table if exists public.ncci_edit_pairs cascade;
drop table if exists public.medicare_fee_schedule cascade;
drop table if exists public.payments cascade;
drop table if exists public.analysis_results cascade;
drop table if exists public.line_items cascade;
drop table if exists public.bills cascade;
drop function if exists public.set_updated_at cascade;
