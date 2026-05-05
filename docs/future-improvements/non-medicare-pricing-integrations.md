# Non-Medicare Pricing Data Integrations

**Status:** Planned, post-MRF-pipeline.
**Goal:** Make ClaroBill's audit engine comprehensive across every major US payer type, not just Medicare-certified civilian hospital MRFs.

This is the index. Each integration has its own detailed design doc. Read this page first to understand the shape of the work; then dive into the linked doc for any specific source.

---

## Why this exists

ClaroBill's current rules engine compares bills against MRF data — the chargemaster + negotiated rates that CMS-certified civilian hospitals are required to publish under 42 CFR 180. That data covers a huge share of US bills, but **leaves three patient populations unprotected**:

1. **TRICARE beneficiaries** (active military, retirees, dependents — ~9.6M people)
2. **Veterans Affairs beneficiaries** (~9M veterans enrolled)
3. **Medicaid beneficiaries** (~85M Americans)

For these patients, "billed more than the published rate" is still a violation worth catching — the published rate just lives in a *different* federally-mandated source than MRF.

## Out of scope for the MRF discovery pipeline

The MRF discovery pipeline (`docs/decisions/2026-04-28-cms-direct-mrf-discovery.md`) deliberately filters out:

- **DoD facilities** (Military Treatment Facilities) — 32 rows in Sandra's 2026-04-28 real run, identified by `hospital_type = 'Acute Care - Department of Defense'`
- **VA Medical Centers** — 132 rows in the same run, identified by `hospital_type = 'Acute Care - Veterans Administration'`

Both are excluded because they don't publish CMS MRFs. Their pricing lives in the integrations below.

---

## The integrations

### 1. TRICARE Maximum Allowable Charge (TMAC)

**Detailed design:** [`docs/decisions/2026-04-22-tricare-rate-integration.md`](../decisions/2026-04-22-tricare-rate-integration.md)

The DHA publishes annual rate files for civilian providers billing TRICARE. RVU-based methodology (similar to Medicare PFS) with TRICARE-specific conversion factors. Currently the engine uses Medicare PFS as a proxy with a 1.2× threshold.

**Adds coverage for:** TRICARE beneficiaries billed at civilian providers. (TRICARE bills from MTFs themselves are out of scope — see "DoD MTF self-billing rates" below.)

### 2. VA Community Care fee schedule

**Detailed design:** *(not yet written — when scoped, file as `docs/future_improvements/va-community-care-integration.md`)*

When veterans get care from non-VA providers through the VA Community Care Network, VA reimburses at a published rate (usually Medicare-equivalent + multipliers). The schedule is public at https://www.va.gov/COMMUNITYCARE/providers/Fee_Schedule.asp. Updated quarterly.

**Adds coverage for:** Veterans billed by civilian providers under VA Community Care.

### 3. State Medicaid fee schedules

**Detailed design:** [`docs/future_improvements/medicaid-state-rate-scraping.md`](medicaid-state-rate-scraping.md)

Each state runs its own Medicaid program with its own fee schedule. ~51 separate sources, varying formats (PDF, Excel, CSV, sometimes API). Phased approach: Top 10 states by Medicaid enrollment first (covers ~60% of beneficiaries), then expanded coverage.

**Adds coverage for:** Medicaid beneficiaries (~85M Americans, the largest payer category).

### 4. DoD MTF self-billing rates

**Detailed design:** *(not scoped — defer until ClaroBill has user volume of military families that would benefit.)*

When TRICARE beneficiaries get care at Military Treatment Facilities, most don't see a bill (Active Duty get free care; some retirees may have small copays). MTFs do bill third-party insurers when applicable, and those bills can be audited against published MTF rates. Likely requires a DoD partnership or FOIA request — not a public-data integration.

**Adds coverage for:** TRICARE beneficiaries billed by MTFs (when third-party insurance is involved).

### 5. Commercial payer Transparency in Coverage (TIC) files

**Detailed design:** [`docs/future_improvements/commercial-rate-benchmarking.md`](commercial-rate-benchmarking.md)

Major commercial health plans (Aetna, BCBS, UHC, Cigna, etc.) are required by 45 CFR Part 158 + 45 CFR §158.140 to publish their negotiated rates with every in-network provider in machine-readable JSON files. These complement hospital MRFs by giving us the *payer's* angle on the same negotiated rates.

**Adds coverage for:** Commercial-plan bills where MRF doesn't have the per-payer rate (gap-fill for `NEGOTIATED_RATE_EXCEEDED`).

---

## Architectural shape

Each integration produces its own table in BigQuery (`tricare_pricing`, `va_community_care_pricing`, `medicaid_pricing`, `tic_pricing`). The rules engine's pseudocode (post-Phase 5):

```python
if bill.insurance_type == 'Medicare':
    rates = query_hospital_charges(bill.hospital_npi, bill.service_year)
elif bill.insurance_type == 'TRICARE':
    rates = query_tricare_pricing(bill.region, bill.service_year)
elif bill.insurance_type == 'VA Community Care':
    rates = query_va_community_care(bill.service_year)
elif bill.insurance_type == 'Medicaid':
    rates = query_medicaid_pricing(bill.state, bill.service_year)
elif bill.insurance_type in ('Aetna', 'BCBS', 'UHC', 'Cigna', ...):
    rates = query_tic_pricing(bill.payer, bill.network_tier, bill.service_year)
```

The decision of which pricing source to use is at audit time, not at directory build time. The same hospital can have three or more different prices for the same procedure depending on insurance type. Our `hospital_charges` schema already supports this via the `payer_name`/`negotiated_charge` columns from MRF; the federal-program prices live in different tables. Schema can absorb them; the loaders are what's missing.

### Why NOT one giant pricing table

- Schema shapes diverge significantly (TIC has plan_id, MRF has CCN, Medicaid has state, etc.)
- Update cadences differ (annual for MRF, quarterly for VA, ad-hoc for state Medicaid)
- Discovery pipelines differ (MRF is ours, TMAC is a single download, Medicaid is 50 separate scrapes)
- A unified table would require lowest-common-denominator columns and force everything else into a JSON blob — which destroys the partitioning + clustering benefits BigQuery provides

Per-source tables with a thin abstraction layer in the rules engine is the right shape.

---

## Status

| Integration | Detailed design | Status | Estimated effort |
|---|---|---|---|
| MRF (Medicare civilian hospitals) | `docs/decisions/2026-04-28-cms-direct-mrf-discovery.md` | Phases 1-2 done; 3-6 in progress | (current pipeline) |
| TRICARE TMAC | `docs/decisions/2026-04-22-tricare-rate-integration.md` | Designed; not built | ~2 weeks |
| VA Community Care | *(not yet scoped)* | Not started | ~1 week once scoped |
| State Medicaid (top 10 states) | `docs/future_improvements/medicaid-state-rate-scraping.md` | Designed; not built | ~6-8 weeks |
| State Medicaid (remaining states) | Same doc | Not started | ~varies, depends on per-state source quality |
| DoD MTF | *(not scoped — needs DoD partnership)* | Deferred | Unknown; partnership-gated |
| Commercial TIC files | `docs/future_improvements/commercial-rate-benchmarking.md` | Designed; not built | ~4-6 weeks for largest payers |

---

*Document created: 2026-04-28*
*Owner: ClaroBill Engineering*
*Trigger to revisit: when MRF pipeline (Phases 4-6) ships and Sandra is ready to expand audit coverage beyond Medicare-certified civilian hospitals.*
