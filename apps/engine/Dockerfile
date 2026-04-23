FROM python:3.11-slim

# DejaVu Sans — Unicode TTF fonts used by fpdf2 for PDF generation.
# fonts-dejavu-core only ships Regular + Bold; Oblique and BoldOblique are in
# fonts-dejavu (the full package). Install the full package so all four styles
# are available and PDF generation does not crash with a missing-font error.
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies before copying source — maximises layer cache hits.
# Build context is apps/engine/ (gcloud run deploy --source apps/engine).
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy application source
COPY . .

# Cloud Run injects PORT at runtime (default 8080). Explicit EXPOSE is documentation only.
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
