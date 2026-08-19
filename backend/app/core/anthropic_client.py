from functools import lru_cache

from anthropic import AsyncAnthropic

from app.core.config import settings


@lru_cache
def get_anthropic_client() -> AsyncAnthropic:
    """Cached async Anthropic client, shared across the app's lifetime."""
    return AsyncAnthropic(
        api_key=settings.ANTHROPIC_API_KEY, timeout=settings.ANTHROPIC_TIMEOUT_SECONDS
    )
