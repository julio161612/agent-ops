import time
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass
class RateLimitStatus:
    allowed: bool
    current: int
    limit: int


class RateLimiter:
    """Sliding-window-log rate limiter for "N per minute", in Redis — scoped
    by whatever ``key`` the caller passes (a tenant id for the internal
    tenant-wide limit, an API key id for the public API's per-key limit).

    Chosen over the alternatives:
    - A fixed window (e.g. a counter keyed by ``tenant:minute``) is simpler but
      lets a tenant send up to 2x the limit in a burst straddling two windows
      (e.g. the limit at :00:59 and again at :01:00).
    - A token bucket is the better fit when you want to *allow* controlled
      bursts with smooth refill, but that's not what "N per minute" asks for
      here, and its continuous-refill math is harder to reason about and to
      assert on precisely in tests than a plain rolling count.

    A sliding window log (a Redis sorted set of request timestamps, pruned to
    the last 60s on every check) gives an exact rolling count with a handful
    of cheap O(log n) Redis ops, and is trivial to test deterministically.
    """

    _WINDOW_SECONDS = 60

    def __init__(self, redis: Redis):
        self._redis = redis

    async def check_and_increment(self, *, key: str, limit_per_minute: int) -> RateLimitStatus:
        """``key`` scopes the sliding window — e.g. a tenant id for the
        tenant-wide limit, or an API key id for the public API's stricter
        per-key limit. Each distinct key gets its own independent window.
        """
        redis_key = f"rate_limit:{key}"
        now = time.time()
        member = f"{now}:{uuid.uuid4()}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, now - self._WINDOW_SECONDS)
        pipe.zadd(redis_key, {member: now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, self._WINDOW_SECONDS)
        _, _, count, _ = await pipe.execute()

        if count > limit_per_minute:
            await self._redis.zrem(redis_key, member)
            return RateLimitStatus(allowed=False, current=count - 1, limit=limit_per_minute)
        return RateLimitStatus(allowed=True, current=count, limit=limit_per_minute)
