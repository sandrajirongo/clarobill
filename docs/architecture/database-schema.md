# Database schema

ClaroBill uses two databases. This doc is a hand-written summary of both. The
authoritative source for Postgres is `supabase/migrations/*.sql`; for BigQuery
it's the table definitions in the ETL scripts. Re-read those when in doubt —
this page describes intent.

## Postgres (Supabase)

Application data. Service-role key bypasses RLS; the engine uses it. The
anon key honors RLS so the frontend can never read another user's data.

### User-scoped tables (RLS enabled)

| Table | Primary purpose | Key columns | Constraints worth knowing |
|---|---|---|---|
| `bills` | One row per uploaded bill | `id`, `user_id`, `file_path` (unique), `status`, OCR-extracted `hospital_*` fields, confirmed `payer_name`, `plan_name`, `profile_member_id`, `error_count`, `total_potential_savings` | `mime_type` ∈ {pdf, jpeg, png}; `status` ∈ {uploading, ocr_processing, analyzing, complete, failed}; `file_size` ≤ 20 MB |
| `line_items` | Parsed CPT codes + charges per bill | `bill_id`, `cpt_code`, `service_date`, `quantity`, `unit_charge`, `total_charge`, `modifier`, `diagnosis_pointers` | `quantity > 0`; charges `≥ 0`; FK cascade-deletes on bill delete |
| `analysis_results` | One-to-one with `bills`. Rules engine output + AI summary + report URLs | `bill_id` (unique), `errors` (JSONB camelCase BillingError[]), `total_charges`, `estimated_fair_value`, `total_potential_savings`, `ai_summary`, `report_url`, `dispute_letter_url` | `bill_id` UNIQUE — re-analyze uses upsert (`ON CONFLICT DO UPDATE`) so re-running is safe |
| `payments` | Stripe payment records | `user_id`, `bill_id`, `stripe_session_id` (unique), `amount_cents`, `status` | `amount_cents >= 0`; `status` ∈ {pending, complete, failed, refunded} |
| `profile_members` | Insured members per account (account holder + dependents) | `user_id`, `full_name`, `date_of_birth`, `state`, `county`, `zip_code`, `is_primary` | One `is_primary=true` per `user_id` (partial unique index); `state` is uppercase CMS state name |
| `insurance_plans` | One member can hold N plans | `profile_member_id`, `payer_name`, `plan_name`, `member_id`, `plan_type`, `is_primary_plan` | `plan_type` ∈ {commercial, medicare, medicaid, tricare, self_pay} |
| `user_profiles` | Account-holder identity (name + email sync) | `id` (FK → auth.users), `email`, `first_name`, `last_name`, `created_at`, `updated_at` | Auto-created by `on_auth_user_created` trigger on signup; email synced by `on_auth_user_email_updated` trigger. Used by `PATCH /api/user/profile` and Stripe webhook email lookup. |
| `referral_codes` | Per-user referral code | `user_id` (unique), `code` (unique), `credits` | Each user gets exactly one code on signup |
| `referrals` | Tracks who referred whom | `referrer_user_id`, `referred_user_id`, `referral_code_id`, `status` | `status` ∈ {pending, complete}; one `referred_user_id` ever; settled to `complete` in Stripe webhook |
| `deleted_bill_files` | Tombstone for retention/GDPR delete | `user_id`, `file_path`, `deleted_at` | Used by retention purge job |

#### RLS policy shape

Every user-scoped table has the same logical policy:
- Direct-user tables (`bills`, `payments`, `profile_members`, `user_profiles`, `referral_codes`): `auth.uid() = user_id` (or `= id` for `user_profiles`)
- Indirect tables (`line_items`, `analysis_results`, `insurance_plans`): `EXISTS` join through the parent that owns `user_id`
- `referrals`: SELECT only for participants (`referrer_user_id = auth.uid() OR referred_user_id = auth.uid()`); writes via service role only

Reference tables are public-readable, never user-scoped.

### Reference tables (service-role access only)

These are bulk-loaded from CMS data via `scripts/load_*.py`. The engine reads
them through the service-role key during analysis. RLS is enabled on all of
them with no policies — deny by default for all non-service-role requests.

| Table | Purpose |
|---|---|
| `cms_pfs_indicators` | Medicare Physician Fee Schedule RVU components per HCPC code, by quarter |
| `cms_localities` | GPCI multipliers per CMS MAC locality, by year |
| `cms_county_locality` | County → locality_code mapping (state + county + REST OF STATE + STATEWIDE rows) |
| `cms_anesthesia_base_units` | Anesthesia base units per CPT (anesthesia codes 00100-01999) |
| `cms_anesthesia_cf` | Anesthesia conversion factor per locality, by quarterly effective date |
| `cms_opps_cap` | OPPS payment cap per HCPC for facility-side outlier detection |
| `cms_ambulance_rates` | Ambulance fee schedule per HCPC + locality + year |
| `cms_ambulance_zip_locality` | ZIP → ambulance locality + rural indicator |
| `cms_hcpcs_codes` | HCPCS Level II metadata (coverage_code, pricing_indicator, termination_date) |
| `ncci_edit_pairs` | NCCI Procedure-to-Procedure unbundling pairs, by service_type + payer_type + effective_date |
| `ncci_mue_limits` | Medically Unlikely Edit thresholds per HCPC, by service_type + payer_type + effective_date |

### Update triggers

Tables with `updated_at` use a generic `set_updated_at()` plpgsql function.

Two additional triggers on `auth.users` maintain `user_profiles`:
- `on_auth_user_created` — inserts a `user_profiles` row on every new signup
- `on_auth_user_email_updated` — syncs `user_profiles.email` when a user changes their auth email

### Migration history

- `20260406000001` — initial schema (bills, line_items, analysis_results, payments, NCCI, MFS)
- `20260408000001-002` — bills retention + referrals
- `20260409000001-007` — CMS reference tables (PFS, anesthesia, county locality, OPPS)
- `20260410000008` — effective dates added to PFS + OPPS
- `20260413000009-012` — ambulance rates, HCPCS codes, hospital_npi on bills
- `20260416000013` — profile_members + insurance_plans + bills.payer_name/plan_name
- `20260417000014-015` — bills.display_name, referral trigger fix
- `20260418000016` — referral code generation fix
- `20260420000017-020` — NCCI insurance-aware MUE, RPC replacement
- `20260423000021` — modifier nullable on line_items
- `20260430000022` — bills.hospital_city/state/zip
- `20260504000023` — JSONB camelCase backfill on `analysis_results.errors` (S1 fix)
- `20260505000024` — bills columns patch (idempotent add for columns from earlier migrations)
- `20260505000025` — `user_profiles` table + `on_auth_user_created` / `on_auth_user_email_updated` triggers + backfill from `auth.users`
- `20260505000026` — additional bills columns patch
- `20260511000027` — `first_name` + `last_name` (nullable) added to `user_profiles`
- `20260521000028` — `update_user_profile_name` RPC added (never used; dropped next migration)
- `20260521000029` — `error_count integer` + `total_potential_savings numeric(10,2)` added to `bills` (denormalized from `analysis_results` for dashboard summary display without join)
- `20260521000030` — drop `update_user_profile_name` RPC

## BigQuery (`clarobill-prd.hospital_prices`)

MRF data. Loaded via Cloud Run Jobs (annual + mid-year). See `docs/architecture/gcp-resources.md` for the full BigQuery section.

| Table | Purpose | Partitioning / clustering |
|---|---|---|
| `hospital_directory` | One row per US hospital. CCN, NPI, name, MRF URL, scrape state. ~13,833 rows. | Partitioned by `DATE(last_website_validated_at)`; clustered `(ccn, hospital_npi)` |
| `hospital_charges` | Per-hospital, per-CPT charges. Largest table; billions of rows at full coverage. Append-only; deduplication via `DENSE_RANK() OVER (ORDER BY pricing_effective_year DESC)` at query time. | RANGE partitioned by `pricing_effective_year` (2024–2034); clustered `(hospital_npi, code)` |
| `hospital_charges_legacy_stale` | Frozen pre-effective-dating snapshot. NEVER READ. | None — will be dropped 2026 H2 |
| `mrf_archive_index` | Canonical index of every MRF blob in the immutable GCS archive. Drives the parser's work queue. | Clustered `(hospital_npi, sha256)` |
| `mrf_discovery_checkpoint` | Per-stage state for the annual discovery pipeline. One row per `(run_id, ccn)`. | Clustered `(run_id, ccn)` |
| `mrf_discovery_runs` | Annual summary; one row per discovery run with coverage metrics. | None |
| `payer_name_aliases` | Canonical payer_group → known MRF aliases. Used by `_resolve_payer_aliases()` to normalize user-entered insurer names against MRF variants. | None |

### Why two databases

1. **Scale** — `hospital_charges` at full coverage exceeds Postgres practical limits (billions of rows, columnar reads).
2. **Write pattern** — bulk-load twice a year via `bigquery.LoadJob`; not random-update.
3. **Effective dating** — partition pruning by `pricing_effective_year` is critical for query cost.
4. **Query shape** — engine issues narrow point queries (`WHERE hospital_npi = X AND code IN (...)`); BigQuery's columnar layout makes these cheap.

The engine queries BigQuery using ADC via the `clarobill-vision-sa` service account. When `gcp_project_id` is unset (local dev without GCP creds), `_build_bq_client()` returns `None` and the BQ-backed rules silently no-op — so the engine still runs against Supabase data.

## GCS

`gs://mrf-archive-clarobill-prd` — Coldline bucket holding every MRF blob ever
downloaded, partitioned by `pricing-year={year}/{hospital_npi}/{sha256_first16}.{ext}`.
The pipeline service account has `objectCreator + objectViewer` only — no
delete permission, so this is the chain-of-custody vault.

## Engine ↔ DB mapping

| Engine module | Tables read | Tables written |
|---|---|---|
| `app/api/v1/bills.py::analyze_bill` | `bills`, `profile_members`, `insurance_plans` | `bills.status` |
| `app/api/v1/bills.py::_run_analysis_pipeline` | every `cms_*` + `ncci_*` reference table; `bills`; BQ `hospital_directory`, `hospital_charges`, `payer_name_aliases` | `bills.status`, `bills.hospital_*`, `bills.error_count`, `bills.total_potential_savings`, `line_items` (delete + insert), `analysis_results` (upsert) |
| `app/api/v1/bills.py::generate_report` | `bills`, `analysis_results`, `profile_members`, `insurance_plans` | `analysis_results.report_url`, `dispute_letter_url`; `bills.report_*` |
| `app/api/insurance_card.py` | none | none — stateless extraction |

## Schema invariants worth memorizing

1. **Every user-scoped table has RLS on.** Adding a new user-scoped table without RLS will leak data — there's no app-layer second line of defense.
2. **`analysis_results.bill_id` is UNIQUE.** Re-analyze uses `.upsert({...}, on_conflict="bill_id")` in `bills.py` — safe to re-run without error.
3. **`bills.file_path` is UNIQUE.** Two bills can't reference the same Storage object. Re-uploads must use a new path.
4. **`plan_type` is a closed set.** New values require a migration AND a coordinated update of `app/models/bill.py::PlanType`. The DB CHECK constraint is the second line of defense.
5. **`hospital_charges.pricing_effective_year` is NOT NULL.** Inserting a row without a vintage is impossible; this prevents historical bills from being benchmarked against a future chargemaster.
6. **`mrf_archive_index.parse_status` lifecycle:** `pending → parsed | failed | skipped`. The `skipped` state has no automatic reset path (Phase-8 SF1 backlog item).
7. **`user_profiles` is auto-populated.** Every `auth.users` row gets a `user_profiles` row via trigger. Never manually insert — the trigger handles it.

## Reading the migrations

`supabase/migrations/*.sql` is sequential. The last applied migration in prod
is recorded in `schema_migrations`. Local + CI use `supabase db start` to
boot a fresh Postgres in Docker and apply every migration in order — see
[../operations/ci-cd.md](../operations/ci-cd.md) for the migration-check
workflow.

---

_Last reviewed: 2026-05-25_
