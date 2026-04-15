FROM python:3.11-slim

# System dependencies required by weasyprint (Cairo, Pango, GDK-PixBuf)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
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
