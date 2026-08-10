"""Maintenance: purge stale ARQ job/lock keys from Redis.

Use when a deploy or crash leaves jobs stuck as "already running elsewhere"
(the old worker died mid-job and its lock is still held). Safe to run anytime:
it only removes ARQ's in-progress/retry/lock/result keys — completed results and
scheduled cron state are rebuilt by the worker automatically.

Run against the same Redis the app uses:
    python -m scripts.clear_arq_queue
"""

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
