-- Persist hospital address fields on the bill so the dispute letter
-- can include a complete provider mailing block.
--
-- Why on `bills` and not joined from `hospital_directory`:
--   - The bill's own header is the legally-correct address to send a
--     dispute to (the directory address may be slightly stale or a
--     system HQ; the bill prints the billing-office address).
--   - hospital_directory only covers the ~13k discovered hospitals;
--     bills can be uploaded for facilities outside our directory.
--   - One JOIN avoided per letter generation.
--
-- All three fields are NULLABLE — extraction is best-effort. The letter
-- generator falls back to safe placeholders when any field is missing,
-- never blocks letter generation on missing fields.
alter table public.bills
    add column if not exists hospital_city  text,
    add column if not exists hospital_state text,
    add column if not exists hospital_zip   text;
