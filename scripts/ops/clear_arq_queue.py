"""Operational: flushes pending background jobs from the Redis ARQ worker queue."""

import asyncio
import os

from redis.asyncio import Redis

from pawguard.core.config import get_settings


async def clear_arq_keys(redis_url: str) -> int:
    client = Redis.from_url(redis_url, decode_responses=True)
    try:
        keys = [key async for key in client.scan_iter(match="arq:*")]
        if keys:
            await client.delete(*keys)
        return len(keys)
    finally:
        await client.aclose()


async def main() -> None:
    url = os.environ.get("REDIS_URL") or get_settings().redis_url
    count = await clear_arq_keys(url)
    print(f"Removed {count} stale ARQ key(s) from {url}")


if __name__ == "__main__":
    asyncio.run(main())
