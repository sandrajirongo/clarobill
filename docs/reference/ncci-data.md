# NCCI Data — Reference

**Status: Fully loaded as of 2026-04-21.**

---

## Data Files

Located under `data/ncci/{year}/{source}/` for years 2020–2026.

Two source types:
- `mcd/` — CMS Medicaid files (`payer_type = medicaid`)
- `mcr/` — CMS Medicare files (`payer_type = medicare`)

### PTP (Procedure-to-Procedure edit pairs)

PTP files define code pairs where Col1 (comprehensive) cannot be billed together
with Col2 (component) on the same claim without a bypass modifier (typically 59).

| Source | Format | Naming | Years available |
|--------|--------|--------|-----------------|
| MCD | Tab-delimited `.txt`, 6 columns | `MCD-PTP-{ServiceType}-Effective_MMDDYYYY.txt` | 2026 Q1 only |
| MCR | Tab-delimited `.txt`/`.TXT`, 7 columns | `ccipra-v{ver}r0-f{n}.txt` (practitioner), `ccioph-v{ver}r0-f{n}.txt` (outpatient) | 2026 Q1 only |

MCR files have an extra Pre1996 indicator column at position 2 (empty or `*`) — the
loader detects this automatically by checking whether `row[2]` is a digit.

MCR deletion date sentinel is `*` (still active); MCD sentinels are `20991231` / `99991231`.

No DME MCR PTP files exist in the CMS Medicare release for this format.

### MUE (Medically Unlikely Edit limits)

MUE files define the maximum billable units of a HCPCS/CPT code per claim line per date.

| Source | Format | Naming | Years available |
|--------|--------|--------|-----------------|
| MCD | Tab-delimited `.txt`/`.TXT`, 3 columns, no adjudication indicator | `MCD-MUE-{ServiceType}-Effective[_-]MMDDYYYY[suffix].txt` | 2020–2026, quarterly |
| MCR | CSV, 4 columns, includes adjudication indicator | `MCR_MUE_{ServiceType}_Eff_MM-DD-YYYY[suffix].csv` | 2020–2026, quarterly |

MCD files store `adjudication_indicator = 0` (unknown) — engine treats this as a hard denial.

MCR adjudication indicators:
- `1` = Claim Edit — sum all lines for same code+date
- `2` = Date of Service: Policy — per-line hard denial
- `3` = Date of Service: Clinical — per-line, overridable with documentation

---

## Database Tables

### `ncci_edit_pairs`

```sql
column_one_code    text    -- comprehensive code (Col1)
column_two_code    text    -- component code (Col2)
effective_date     date
deletion_date      date    -- null = still active
modifier_indicator integer -- 0 = modifier not allowed, 1 = may override, 9 = N/A
service_type       text    -- practitioner | outpatient | dme
payer_type         text    -- medicare | medicaid
```

Unique constraint on `(column_one_code, column_two_code, service_type, payer_type)`.

**Loaded row counts (April 21 2026):**

| service_type | payer_type | rows |
|---|---|---|
| practitioner | medicare | 2,323,399 |
| practitioner | medicaid | 2,216,598 |
| outpatient | medicare | 1,781,974 |
| outpatient | medicaid | 1,809,816 |
| dme | medicaid | 45,202 |
| dme | medicare | 0 — no MCR DME PTP files published in this format |

### `ncci_mue_limits`

```sql
hcpcs_code              text
service_type            text    -- practitioner | outpatient | dme
payer_type              text    -- medicare | medicaid
effective_date          date
mue_value               integer -- max billable units; 0 = never separately payable
adjudication_indicator  integer -- 0 (unknown/MCD), 1, 2, or 3
mue_rationale           text
```

Unique constraint on `(hcpcs_code, service_type, payer_type, effective_date)`.

**Loaded row counts (April 21 2026):**

| service_type | payer_type | rows |
|---|---|---|
| practitioner | medicare | 359,406 |
| practitioner | medicaid | 343,599 |
| outpatient | medicare | 357,968 |
| outpatient | medicaid | 343,379 |
| dme | medicare | 72,570 |
| dme | medicaid | 56,013 |

---

## Loader Scripts

### `scripts/load_ncci_edits.py`

Loads PTP edit pairs. Handles both MCD (6-column) and MCR (7-column) formats automatically.

```bash
# Single file
python3 scripts/load_ncci_edits.py \
  --file data/ncci/2026/mcd/MCD-PTP-PractitionerServices-Effective_01012026.txt \
  --service-type practitioner --payer-type medicaid

# Quarterly refresh — deletes existing rows for this (service_type, payer_type) first
python3 scripts/load_ncci_edits.py \
  --file data/ncci/2026/mcr/ccipra-v321r0-f1.TXT \
  --service-type practitioner --payer-type medicare --replace
```

### `scripts/load_mue_limits.py`

Loads MUE limits. Effective date auto-detected from filename; can be overridden.

```bash
python3 scripts/load_mue_limits.py \
  --file data/ncci/2026/mcr/MCR_MUE_PractitionerServices_Eff_04-01-2026.csv \
  --service-type practitioner --payer-type medicare
```

### `scripts/load_ncci_all.sh`

Full load across all years. Safe to re-run — all operations are upserts.

```bash
bash scripts/load_ncci_all.sh
```

**Known behaviour:** Supabase's Cloudflare proxy occasionally returns 502 during
sustained bulk loads. The loaders retry with backoff (30/60/120/180s). If a file
fails after all retries, re-run it individually — upsert is idempotent.

---

## Quarterly Refresh

CMS publishes updated PTP and MUE files each quarter (Jan, Apr, Jul, Oct).

**PTP refresh** (use `--replace` to remove pairs dropped from the new release):
```bash
python3 scripts/load_ncci_edits.py \
  --file data/ncci/{year}/mcd/MCD-PTP-PractitionerServices-Effective_{date}.txt \
  --service-type practitioner --payer-type medicaid --replace
```

**MUE refresh** (no `--replace` needed — effective_date partitions the data naturally):
```bash
python3 scripts/load_mue_limits.py \
  --file data/ncci/{year}/mcr/MCR_MUE_PractitionerServices_Eff_{date}.csv \
  --service-type practitioner --payer-type medicare
```

For a full refresh across all service types, update `load_ncci_all.sh` to point at
the new year directory and re-run.
