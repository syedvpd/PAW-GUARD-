"""Unit of Work pattern: one atomic, short-lived transaction boundary per request/operation.

Per AGENTS.md TRANSACTION RULES, never perform email/SMS/push/HTTP/file-upload work
inside the `async with` block — queue it (e.g. via ARQ) after the transaction commits.
"""

from collections.abc import AsyncGenerator
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.db.session import AsyncSessionLocal


class UnitOfWork:
    def __init__(self) -> None:
        self._session_factory = AsyncSessionLocal
        self.session: AsyncSession | None = None

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self._session_factory()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        assert self.session is not None
        try:
            if exc_type is None:
                await self.session.commit()
            else:
                await self.session.rollback()
        finally:
            await self.session.close()

    async def commit(self) -> None:
        assert self.session is not None
        await self.session.commit()

    async def rollback(self) -> None:
        assert self.session is not None
        await self.session.rollback()


async def get_unit_of_work() -> AsyncGenerator[UnitOfWork]:
    async with UnitOfWork() as uow:
        yield uow
