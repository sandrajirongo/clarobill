# ClaroBill MRF Pipeline — Cloud Run Jobs image
#
# This image serves two Cloud Run Jobs:
#   clarobill-mrf-scraper   CMD: python scrape_hospital_mrfs.py
#   clarobill-mrf-parser    CMD: python parse_hospital_mrfs.py
#
# Both jobs use Application Default Credentials — the Cloud Run runtime SA
# (clarobill-pipeline-sa) is attached to each job at deploy time.
#
# Build context: REPO ROOT (not pipeline/), because Phase 4's archive_writer.py
# imports the canonical `archive_layout` from scripts/mrf_discovery/ — using a
# repo-root context lets us COPY both directories into one image without
# inlining the layout code (which would risk silent drift between the
# scraper's idea of an archive URI and the discovery's). Same convention as
# pipeline/Dockerfile.discovery.
#
# Build and push (from repo root):
#   gcloud builds submit \
#     --config <(cat <<EOF
#   steps:
#     - name: 'gcr.io/cloud-builders/docker'
#       args: ['build', '-f', 'pipeline/Dockerfile', '-t', '<IMAGE>', '.']
#   images: ['<IMAGE>']
#   EOF) .

FROM python:3.11-slim

WORKDIR /app

# Dependencies first so this layer caches across code-only changes.
COPY pipeline/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pipeline source — all .py files at /app/ root.
COPY pipeline/archive_writer.py     /app/
COPY pipeline/csv_vendors.py        /app/
COPY pipeline/effective_year.py     /app/
COPY pipeline/hospital_mrf_utils.py /app/
COPY pipeline/parse_hospital_mrfs.py /app/
COPY pipeline/scrape_hospital_mrfs.py /app/

# Canonical archive_layout — single source of truth shared with the discovery
# image. archive_writer.py adds /app/scripts/ to sys.path then imports
# `from mrf_discovery import archive_layout`. The __init__.py keeps it a
# real Python package.
COPY scripts/mrf_discovery/__init__.py        /app/scripts/mrf_discovery/__init__.py
COPY scripts/mrf_discovery/archive_layout.py  /app/scripts/mrf_discovery/archive_layout.py
COPY scripts/mrf_discovery/bq_checkpoint.py   /app/scripts/mrf_discovery/bq_checkpoint.py

ENV LOG_LEVEL=INFO

# Default to the scraper — override with --command when creating the parser job.
CMD ["python", "scrape_hospital_mrfs.py"]
