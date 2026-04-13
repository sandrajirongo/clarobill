-- Add hospital_npi to bills table.
-- Populated by OCR extraction + Luhn validation during the analysis pipeline.
-- Used as the lookup key for hospital charge comparison in BigQuery (Phase 2).
-- hospital_name is the human-readable name matched from hospital_directory.
alter table public.bills
    add column if not exists hospital_npi text,
    add column if not exists hospital_name text;
