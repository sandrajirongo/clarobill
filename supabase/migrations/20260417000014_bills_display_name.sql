-- Migration: 20260417000014_bills_display_name
-- Adds a user-facing display_name to bills.
-- The column is nullable — old rows without a name fall back to file_name in application code.
alter table public.bills add column display_name text;
comment on column public.bills.display_name is
  'User-supplied label for the bill (e.g. "January ER Visit"). Falls back to file_name when null.';
