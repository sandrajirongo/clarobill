"""FastAPI application entry point for the Clarobill engine service.

Deployed via Cloud Build trigger `rmgpgab-clarobill-engine-us-central1-...`
on every push to main that touches `apps/engine/**`.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import cast

import sentry_sdk
from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.api.insurance_card import router as insurance_card_router
from app.api.v1.bills import router as bills_router
from app.core.config import settings
from app.core.security import verify_engine_api_key

logging.basicConfig(level=settings.log_level)
logger = logging.getLogger(__name__)

if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1 if settings.is_production else 1.0,
        # Never send PHI — strip request bodies which may contain bill data
        before_send=lambda event, hint: {
            **event,
            "request": {**event.get("request", {}), "data": "[redacted]"},
        } if event.get("request") else event,
    )

# Rate limiter — keyed by remote IP address.
# Analysis endpoint gets a tighter limit (expensive AI + OCR calls).
# Other endpoints get a generous default.
limiter = Limiter(key_func=get_remote_address, default_limits=["120/minute"])

app = FastAPI(
    title="Clarobill Engine",
    description="AI-powered medical bill analysis service",
    version="0.0.1",
    # Disable docs in production — internal service, not public API
    docs_url="/docs" if not settings.is_production else None,
    redoc_url=None,
)

app.state.limiter = limiter
# slowapi's handler signature narrows the second arg to RateLimitExceeded;
# Starlette's registry expects the broader Exception type. The runtime
# contract holds because Starlette only dispatches this handler for the
# registered exception class — cast it to the broader type Starlette wants.
_StarletteExceptionHandler = Callable[[Request, Exception], Response | Awaitable[Response]]
app.add_exception_handler(
    RateLimitExceeded,
    cast(_StarletteExceptionHandler, _rate_limit_exceeded_handler),
)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "Authorization", "X-PostHog-Distinct-Id", "X-PostHog-Session-Id"],
)

app.include_router(
    bills_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_engine_api_key)],
)

app.include_router(
    insurance_card_router,
    prefix="/api/v1",
    dependencies=[Depends(verify_engine_api_key)],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe for deployment platform health checks."""
    return {"status": "ok"}
