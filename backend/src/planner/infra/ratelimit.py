from datetime import UTC, datetime

from redis.asyncio import Redis


class RateLimiter:
    """Fixed one-minute windows in Redis. Fails open: a Redis outage must not lock users out."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def hit(self, key: str, limit_per_min: int, cost: int = 1) -> bool:
        """Returns False when the caller is over the limit."""
        bucket = f"rl:{key}:{datetime.now(UTC):%Y%m%d%H%M}"
        try:
            count = await self._redis.incrby(bucket, cost)
            if count == cost:
                await self._redis.expire(bucket, 120)
        except Exception:  # noqa: BLE001
            return True
        return count <= limit_per_min
