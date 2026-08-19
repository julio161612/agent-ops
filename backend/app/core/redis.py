from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import settings


@lru_cache
def get_redis() -> Redis:
    """Cached async Redis client, shared across the app's lifetime."""
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)
