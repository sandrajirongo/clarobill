"""FastAPI dependency injection providers."""

from functools import lru_cache

import anthropic
from supabase import Client, create_client

from app.core.config import settings
from app.services.ai_analysis import AiAnalysisService
from app.services.email_service import EmailService


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """Returns a Supabase client using the service-role key.

    The service-role key bypasses RLS — only use this in the engine,
    never expose it to the frontend. The engine acts on behalf of the
    authenticated user it receives from the Next.js API.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)


@lru_cache(maxsize=1)
def get_async_anthropic_client() -> anthropic.AsyncAnthropic:
    """Returns a shared async Anthropic client used as the AI fallback provider."""
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


@lru_cache(maxsize=1)
def get_ai_analysis_service() -> AiAnalysisService:
    """Returns the AI analysis service (Gemini primary, Claude fallback)."""
    return AiAnalysisService(client=get_async_anthropic_client())


@lru_cache(maxsize=1)
def get_email_service() -> EmailService:
    """Returns a shared email service instance."""
    return EmailService(
        api_key=settings.sendgrid_api_key,
        from_email=settings.sendgrid_from_email,
    )
