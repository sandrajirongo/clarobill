"""Reference data tables for the rules engine.

Modules in this package contain hand-curated reference data — billing rules
that are NOT automatically derivable from a CMS download. Each module
documents the curation criteria and provenance of every entry.

Today this contains:
  - redundant_clinical_pairs: payer-policy redundancies that are NOT NCCI PTP
    edits but are commonly denied by commercial payers.

CMS-derived data (NCCI pairs, MUE limits, PFS rates, OPPS caps, etc.) is
loaded from Supabase tables at runtime — see app/api/v1/bills.py loaders.
"""
