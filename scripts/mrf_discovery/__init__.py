"""MRF discovery pipeline.

Stages of the pipeline (see docs/future_improvements/mrf-discovery-pipeline.md
and docs/future_improvements/pra-pipeline-build.md):

  Stage 1  Fetch sitemap.xml from hospitalpricingfiles.org
  Stage 2  Render each /details/{uuid} in Playwright, extract hospital fields
  Stage 3  Cross-reference CCN -> NPI via the CMS Provider of Services file
  Stage 4  MERGE results into hospital_directory and pra_facility_index
  Stage 5  Existing weekly scraper picks up new mrf_urls and archives to GCS
           with pricing_effective_year, then loads to hospital_charges

This package only contains stages 1-4. Stage 5 lives in pipeline/.
"""
