"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All required settings. FastAPI startup fails if any are missing in production."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str

    # Anthropic is the AI fallback — used when Gemini (primary) fails.
    # Required so the fallback path is always available in production.
    anthropic_api_key: str

    # Prefer GOOGLE_CREDENTIALS_JSON (full JSON content) for containerised deployments.
    # Fall back to GOOGLE_APPLICATION_CREDENTIALS (file path) for local development.
    google_credentials_json: str = ""
    google_application_credentials: str = ""

    # BigQuery / GCS — hospital price transparency pipeline (Phase 1).
    # bq_reader_credentials_json: full JSON content of clarobill-bq-reader-sa key.
    # Leave empty in local dev if using GOOGLE_APPLICATION_CREDENTIALS as fallback.
    gcp_project_id: str = ""
    bigquery_dataset: str = "hospital_prices"

    # Vertex AI — used as fallback when Anthropic API is unavailable (e.g. 529 overloaded).
    # Uses Application Default Credentials; no separate key required.
    vertex_ai_location: str = "us-central1"

    gcs_mrf_staging_bucket: str = "mrf-staging"
    bq_reader_credentials_json: str = ""

    sendgrid_api_key: str
    sendgrid_from_email: str

    # Shared secret that Vercel must pass as X-Engine-Api-Key on every request.
    # Empty in local dev — key check is skipped when not set.
    engine_api_key: str = ""

    sentry_dsn: str = ""  # Optional — errors silently dropped if not set

    environment: str = "development"
    log_level: str = "INFO"
    allowed_origins: str = "http://localhost:3000"

    @property
    def is_production(self) -> bool:
        """True when running in production — used to tighten security checks."""
        return self.environment == "production"

    @property
    def cors_origins(self) -> list[str]:
        """Parsed list of allowed CORS origins."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


# Module-level singleton — import this, don't instantiate Settings directly
settings = Settings()
