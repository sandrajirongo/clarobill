"""PostHog analytics client — module-level singleton.

Import `posthog_client` for event capture. The client is a no-op when
POSTHOG_API_KEY is not set (local dev without analytics configured).
"""

import atexit
import logging

from posthog import Posthog

from app.core.config import settings

logger = logging.getLogger(__name__)

posthog_client: Posthog = Posthog(
    settings.posthog_api_key or "disabled",  # project_api_key (positional in posthog>=7.x)
    host=settings.posthog_host,
    enable_exception_autocapture=True,
    disabled=not bool(settings.posthog_api_key),
)

# Flush buffered events before the process exits so no analytics are lost
atexit.register(posthog_client.shutdown)
