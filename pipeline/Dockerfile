# ClaroBill MRF Pipeline — Cloud Run Jobs image
#
# This image serves two Cloud Run Jobs:
#   clarobill-mrf-scraper   CMD: python scrape_hospital_mrfs.py
#   clarobill-mrf-parser    CMD: python parse_hospital_mrfs.py
#
# Both jobs use Application Default Credentials — the Cloud Run runtime SA
# (clarobill-pipeline-sa) is attached to each job at deploy time.
#
# Build and push (from repo root):
#   gcloud builds submit \
#     --tag us-central1-docker.pkg.dev/clarobill-prd/clarobill-pipeline/mrf-pipeline:latest \
#     pipeline/
#
# Note: The build context is the pipeline/ directory, so paths are relative to it.

FROM python:3.11-slim

WORKDIR /app

# Install dependencies before copying source so this layer is cached.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline source files.
COPY hospital_mrf_utils.py scrape_hospital_mrfs.py parse_hospital_mrfs.py ./

ENV LOG_LEVEL=INFO

# Default to the scraper — override with --command when creating the parser job.
CMD ["python", "scrape_hospital_mrfs.py"]
