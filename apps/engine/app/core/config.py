"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All required settings. FastAPI startup fails if any are missing in production."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    supabase_url: str
    supabase_service_role_key: str

    anthropic_api_key: str

    # Prefer GOOGLE_CREDENTIALS_JSON (full JSON content) for containerised deployments.
    # Fall back to GOOGLE_APPLICATION_CREDENTIALS (file path) for local development.
    google_credentials_json: str = ""
    google_application_credentials: str = ""

    sendgrid_api_key: str
    sendgrid_from_email: str

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
settings = Settings()  # type: ignore[call-arg]
