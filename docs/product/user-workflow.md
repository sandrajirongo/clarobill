# ClaroBill — User Workflow

This document describes the complete user journey from signup through receiving a
dispute letter. It covers both the current implemented state and the planned
verification flow that ensures maximum analysis accuracy.

---

## Guiding Principles

Medical overbilling is pervasive and often goes unchallenged because patients
lack the tools and information to identify errors. ClaroBill's design philosophy
is:

- **User-first accuracy.** A report is only as good as the data going in. We
  verify key inputs before running analysis to avoid a correct-but-useless result
  (e.g. benchmarking against the wrong hospital's prices).
- **No false confidence.** When we cannot identify the hospital or insurer with
  certainty, we tell the user — we don't silently run with bad data and produce
  a report that looks authoritative but isn't.
- **Maximum savings.** We run every rule we can. A user who uploaded a bill and
  confirmed their insurer gets 10 independent checks, not just one.
- **Plain language.** Every detected error is described in plain English with
  a specific dollar amount. No jargon, no code numbers without explanation.

---

## Account Structure

### Profiles support multiple insured members

One ClaroBill account can hold bills for multiple people (the account holder plus
dependents). Each insured person is a **profile member** with:

- Full name (for matching against OCR-extracted patient name)
- Date of birth (for identity confirmation)
- Insurance plan(s) (one member may have multiple plans: primary, secondary, etc.)

Bills are tagged to the profile member they belong to. Analysis runs against that
member's insurance data. This design:
- Supports families where parents manage children's bills
- Handles dual-coverage situations (Medicare + supplemental, etc.)
- Supports patients with multiple plans for different service types (e.g. dental/vision)

**Billing:** We charge per report, not per account member. Adding dependents is free.

---

## Step 1 — Signup

The user creates an account and sets up their primary profile:

1. **Email + password** (Supabase Auth)
2. **Primary member details:**
   - Full name
   - Date of birth
   - Home state and county (used for Medicare GPCI locality adjustment)
   - ZIP code (used for ambulance rural/urban rate tier)
3. **Insurance information (at least one plan):**
   - Insurer name (payer) — e.g. "Aetna", "Blue Cross Blue Shield of California"
   - Plan name — e.g. "PPO Gold", "HMO Select Plus"
   - Member ID (optional — not used for analysis; auto-filled into the dispute letter when present, otherwise left as a `[YOUR MEMBER ID]` placeholder)
   - Plan type: Commercial / Medicare / Medicaid / Tricare / Self-pay
4. **Add dependents** (optional — can be done later from account settings)

Insurance information is stored per profile member and can be updated at any time.
Multiple plans per member are supported (for dual coverage).

---

## Step 2 — Upload a Bill

The user uploads a medical bill:

1. **Select profile member** — whose bill is this?
2. **Upload file** — PDF, JPG, or PNG (max 20MB)
3. **Bill type** (optional — helps with context):
   - Hospital/Facility bill
   - Physician/Provider bill
   - Ambulance bill
   - Insurance Explanation of Benefits (EOB)

The file is uploaded to Supabase Storage (encrypted at rest). OCR begins
immediately in the background.

---

## Step 3 — Pre-Analysis Verification

**This step is the key to accurate analysis.** Before running the rules engine,
we surface what OCR extracted and ask the user to confirm or correct it.

The verification screen presents four confirmation panels:

### Panel 1 — Patient Identity
OCR attempts to extract the patient name from the bill header.

| State | What the user sees |
|-------|--------------------|
| OCR found a name | "We found this patient name on your bill: **[OCR name]** — is this correct?" |
| OCR found a name that matches a profile member | Auto-confirmed, shown as green ✓ with the matched profile member |
| OCR found a name that does NOT match any profile member | Warning: "The name on this bill (**[OCR name]**) doesn't match any member on your account. Please confirm which member this bill belongs to, or add them to your account." |
| OCR could not find a name | "We couldn't read the patient name on this bill. Please select the member this bill belongs to." |

The user confirms (or selects) the profile member. This ensures analysis uses
the correct location (for GPCI) and insurance data (for rate benchmarking).

### Panel 2 — Hospital / Provider
OCR attempts to extract the NPI (National Provider Identifier) and/or the
hospital/facility name from the bill header.

| State | What the user sees |
|-------|--------------------|
| NPI found and matches a known hospital | "We identified your hospital: **[Hospital Name]** — is this correct?" |
| Hospital name found (no NPI) | "We found this provider name: **[Name]** — does this match your hospital?" |
| Neither found | "We couldn't identify the hospital on this bill. Please search for your hospital." |

The user confirms or corrects. If incorrect, they can search by:
- Hospital name (free text search against `hospital_directory`)
- Location (city/state filter)

**Why this matters:** The hospital identification determines which hospital's
published prices we benchmark against. Benchmarking against the wrong hospital
produces meaningless results.

If the user cannot identify the hospital (e.g. a small independent clinic not in
our database), we proceed without hospital-specific benchmarks — the Medicare
and insurer rate rules still run.

### Panel 3 — Insurance Plan
The user's saved insurance plans are shown. They select which plan covers this
specific bill.

| State | What the user sees |
|-------|--------------------|
| User has exactly one plan for this member | Auto-selected, shown as "Using your plan: **[Insurer] [Plan Name]**. Correct?" |
| User has multiple plans | "Which insurance plan covers this bill?" with a list of their saved plans |
| User has no plans saved | "Add your insurance to get the most accurate analysis. This unlocks the negotiated rate check." + option to add plan inline |

The user can also select "Self-pay / No insurance" which disables the negotiated
rate rule and adjusts the report language.

**Why this matters:** Knowing the insurer and plan enables the NEGOTIATED_RATE_EXCEEDED
rule — the most powerful check in the engine. Without it, we can only benchmark
against Medicare rates and the hospital's own gross charge list.

### Panel 4 — Service Dates
OCR attempts to extract the service date range from the bill.

| State | What the user sees |
|-------|--------------------|
| Single service date found | "Service date: **[date]** — correct?" |
| Date range found | "Service dates: **[start] — [end]** — correct?" |
| No dates found | "We couldn't read the service dates. Please enter them." |

**Why this matters:** CMS fee schedules change quarterly. The service date
determines which quarterly release of Medicare rates, OPPS caps, and HCPCS
termination dates we benchmark against. A wrong date means potentially using
stale rates.

### Proceeding
Once the user has reviewed and confirmed all four panels, a "Run Analysis" button
is enabled. The confirmed values are submitted to the engine alongside the bill.

If any panel could not be auto-confirmed and the user skips it without fixing it,
a warning is shown in the final report: "Note: [panel name] could not be confirmed.
This check may be less accurate."

---

## Step 4 — Analysis

The engine runs all applicable rules:

1. **OCR text → parsed line items** (CPT codes, charges, dates)
2. **Medicare rate benchmarks** loaded from CMS PFS tables
3. **NCCI edit pair** violations checked
4. **Non-payable / terminated codes** checked
5. **Anesthesia outliers** checked (if anesthesia codes present)
6. **OPPS facility caps** checked (if outpatient facility bill)
7. **Ambulance fee schedule** checked (if ambulance codes present)
8. **Hospital gross charges** loaded from BigQuery MRF data (if hospital identified)
9. **Negotiated rates** loaded from BigQuery MRF data (if insurer + plan confirmed)
10. **AI analysis** (Gemini primary, Claude fallback) generates plain-English summary

Typical processing time: 15–45 seconds.

The frontend polls the bill status and shows a progress indicator during analysis.

---

## Step 5 — Results Teaser

The user sees a summary screen showing:

- Total charges on the bill
- Number of potential errors found
- **Estimated potential savings** (sum of all estimated overcharges)
- Severity breakdown (critical / warning)
- A blurred/locked list of the detected errors

The teaser is designed to clearly communicate the value before payment. If
significant errors are found, the user has strong motivation to unlock the full
report.

**Free preview:**
- The most critical error is shown in full (as a preview of the report quality)
- Total potential savings is always shown

**Locked (requires payment):**
- Full list of all errors with complete descriptions
- AI-generated analysis narrative
- Dispute letter (personalized to the specific errors found)

---

## Step 6 — Payment

Stripe Checkout (one-time payment per report). After successful payment:
- The full report PDF is generated
- A personalized dispute letter is generated
- Both are emailed to the user
- The user can download them from the results page

---

## Step 7 — The Report

The PDF report contains:

### Section 1 — Bill Summary
- Hospital/provider name, service date(s), total charges
- Total potential savings identified
- Breakdown by error severity

### Section 2 — Error Details
For each detected error:
- **Plain-English description** of what was wrong
- **The charge vs. the benchmark** (e.g. "You were charged $850 vs. the $142 contracted rate")
- **Estimated overcharge** in dollars
- **How to dispute it** — specific language to use with the provider or insurer

### Section 3 — AI Analysis
AI narrative synthesis of the findings (Gemini primary, Claude fallback) — explains patterns across multiple
errors, contextualizes the significance, and gives the patient a confident,
informed framing for approaching the dispute.

### Section 4 — Dispute Letter
Pre-written, personalized dispute letter addressed to the provider's billing
department. Cites the specific CPT codes, amounts, and regulatory basis for each
dispute. Ready to send.

The closing block is auto-filled from the user's profile when the data is
available — letterhead date is the report-generation date, recipient is the
hospital from OCR, and the signature block uses `profile_members.full_name`,
`profile_members.date_of_birth`, the bill's confirmed `payer_name`, and
`insurance_plans.member_id` (matched on the bill's confirmed payer + plan).
Any field that is missing falls back to a bracketed placeholder (`[YOUR NAME]`,
`[YOUR DATE OF BIRTH]`, `[YOUR MEMBER ID]`) so the user can hand-fill it.

---

## Verification Data Flow

```
Signup
  └── User saves: member profiles, insurance plans per member

Upload
  └── OCR extracts: patient name, NPI, hospital name, service dates, CPT codes

Pre-Analysis Verification screen
  └── User confirms / corrects:
        patient_name     → matched to profile member → state, county, ZIP for GPCI
        hospital_npi     → looked up in hospital_directory → enables hospital charge rules
        hospital_name    → fallback if no NPI
        payer_name       → from selected insurance plan → enables negotiated rate rule
        plan_name        → from selected insurance plan → enables negotiated rate rule
        service_date     → confirmed rate date → correct quarterly CMS rates loaded

Analysis pipeline
  └── RulesEngine receives:
        medicare_rates       (locality-adjusted using confirmed state/county)
        ncci_pairs           (structural)
        non_payable_codes    (code validity)
        anesthesia_cf        (locality-adjusted)
        opps_rates           (locality-adjusted)
        ambulance_rates      (ZIP-adjusted)
        hospital_charges     (gross_charge per CPT, from confirmed NPI)
        negotiated_charges   (negotiated_charge per CPT, from confirmed NPI + payer + plan)
```

---

## Edge Cases and Graceful Degradation

| Situation | Behavior |
|-----------|----------|
| Hospital not in our MRF database | Hospital charge rules skipped; all other rules run |
| Insurer name doesn't match any MRF payer | Negotiated rate rule skipped; note shown in report |
| OCR extracts no line items | Analysis returns 0 errors; report shows "No itemized charges found — try uploading a higher-resolution scan" |
| Service date not parseable | Falls back to today's date; user confirmed date is preferred |
| Self-pay patient | Negotiated rate rule skipped; discounted_cash_price from MRF shown as alternative benchmark if available |
| Bill is an EOB (not a provider bill) | PRICE_OUTLIER still runs; hospital charge rules run if hospital identified |

---

## Future Enhancements

- **Secondary insurance cross-check:** Flag when primary insurer processed less than
  expected and secondary insurance should have applied
- **Balance billing detection:** Flag when out-of-network provider bills above
  the in-network rate in No Surprises Act protected situations
- **Diagnosis code validation:** Cross-check that billed procedures are consistent
  with the diagnosis codes on the claim
- **Prior authorization flags:** Identify procedures that typically require prior auth
  and flag the absence of an auth number on the claim

---

_Last reviewed: 2026-05-05_
