-- Rollback: 20260417000014_bills_display_name
alter table public.bills drop column if exists display_name;
