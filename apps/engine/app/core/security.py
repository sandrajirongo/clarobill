"""Request authentication for the engine's internal API."""

from fastapi import Header, HTTPException, status

from app.core.config import settings


async def verify_engine_api_key(x_engine_api_key: str = Header(default="")) -> None:
    """Verify the shared API key passed by the Vercel frontend on every request.

    Skipped entirely in local development when ENGINE_API_KEY is not set,
    so the engine can be called without a key during development.
    In production, any request missing or presenting a wrong key gets a 401.
    """
    if not settings.engine_api_key:
        return
    if x_engine_api_key != settings.engine_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
