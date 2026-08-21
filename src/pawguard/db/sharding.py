import uuid
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class ShardRegistry:
    """Registry to keep track of engine connections for different database shards.

    Demonstrates design pattern to scale database boundaries horizontally (PRR 3.33).
    """

    def __init__(self) -> None:
        self._engines: dict[str, AsyncEngine] = {}
        self._sessionmakers: dict[str, async_sessionmaker[AsyncSession]] = {}

    def register_shard(self, shard_key: str, database_url: str, **engine_kwargs: Any) -> None:
        """Register a database engine connection for a specific shard key (e.g., 'us-east', 'eu-west')."""
        engine = create_async_engine(database_url, **engine_kwargs)
        self._engines[shard_key] = engine
        self._sessionmakers[shard_key] = async_sessionmaker(
            bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
        )

    def get_sessionmaker(self, shard_key: str) -> async_sessionmaker[AsyncSession] | None:
        return self._sessionmakers.get(shard_key)

    async def close_all(self) -> None:
        for engine in self._engines.values():
            await engine.dispose()


class ShardedSessionManager:
    """Manager that resolves the appropriate database session based on a routing shard key."""

    def __init__(self, registry: ShardRegistry) -> None:
        self.registry = registry

    def get_session_for_shard(self, shard_key: str) -> AsyncSession:
        """Resolves the session maker for the specified shard key, or raises ValueError if not registered."""
        sessionmaker = self.registry.get_sessionmaker(shard_key)
        if sessionmaker is None:
            raise ValueError(f"No registered database shard found for key: {shard_key}")
        return sessionmaker()

    def get_shard_key_for_shelter(self, shelter_id: uuid.UUID) -> str:
        """Example routing strategy: shard database by region group based on shelter ID prefix."""
        id_str = str(shelter_id)
        if id_str.startswith(("0", "1", "2")):
            return "shard_east"
        return "shard_west"
