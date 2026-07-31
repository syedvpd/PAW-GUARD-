"""Base service class providing reusable CRUD and paginated listing logic.

Services that extend this class get standard create / list / get / update / soft-delete
behaviour and only override the methods where custom business rules are needed.
"""

import uuid
from collections.abc import Sequence
from typing import Any, TypeVar

from pydantic import BaseModel
from sqlalchemy import func, select

from pawguard.core.exceptions import NotFoundError
from pawguard.core.pagination import PageParams, build_pagination_meta
from pawguard.core.responses import PaginatedResponse
from pawguard.core.search import SortParams, apply_sorting, build_search_filter
from pawguard.db.base import Base
from pawguard.db.mixins import SoftDeleteMixin

ModelT = TypeVar("ModelT", bound=Base)
CreateSchemaT = TypeVar("CreateSchemaT", bound=BaseModel)
UpdateSchemaT = TypeVar("UpdateSchemaT", bound=BaseModel)
ResponseSchemaT = TypeVar("ResponseSchemaT", bound=BaseModel)


class BaseService[
    ModelT: Base, CreateSchemaT: BaseModel, UpdateSchemaT: BaseModel, ResponseSchemaT: BaseModel
]:
    """Provides standard CRUD with soft-delete, pagination, search, filter, and sort.

    Subclasses set ``model_class`` and provide a ``_to_response`` mapping.
    """

    model_class: type[ModelT]
    search_fields: tuple[str, ...] = ()
    sortable_fields: set[str] | None = None
    default_sort_field: str = "created_at"

    def __init__(self, session: Any, repository: Any | None = None) -> None:
        self._session = session
        self._repo = repository

    async def create(self, payload: CreateSchemaT, **extra_fields: Any) -> ModelT:
        data = payload.model_dump()
        data.update(extra_fields)
        instance = self.model_class(**data)
        self._session.add(instance)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def get(self, id: uuid.UUID) -> ModelT:
        model_class = self.model_class
        instance = await self._get_by_id(id, model_class)
        if instance is None:
            raise NotFoundError(f"{model_class.__name__} not found.")
        return instance

    async def update(self, id: uuid.UUID, payload: UpdateSchemaT) -> ModelT:
        instance = await self.get(id)
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(instance, key, value)
        await self._session.flush()
        await self._session.refresh(instance)
        return instance

    async def soft_delete(self, id: uuid.UUID) -> None:
        instance = await self.get(id)
        from datetime import UTC, datetime
        instance.deleted_at = datetime.now(UTC)  # type: ignore[attr-defined]
        await self._session.flush()

    async def list_paginated(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        **filters: Any,
    ) -> tuple[Sequence[ModelT], int]:
        model_class = self.model_class
        stmt = select(model_class)

        if issubclass(model_class, SoftDeleteMixin):
            stmt = stmt.where(model_class.deleted_at.is_(None))

        search_filter = build_search_filter(model_class, search_term, self.search_fields)
        if search_filter is not None:
            stmt = stmt.where(search_filter)

        for field_name, value in filters.items():
            if value is not None:
                column = getattr(model_class, field_name, None)
                if column is not None:
                    stmt = stmt.where(column == value)

        valid_fields = self.sortable_fields or {c.name for c in model_class.__table__.columns}
        stmt = apply_sorting(stmt, sort, valid_fields, self.default_sort_field)

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar_one()

        stmt = stmt.offset(page_params.offset).limit(page_params.limit)
        results = (await self._session.execute(stmt)).scalars().all()

        return results, total

    async def get_paginated_response(
        self,
        page_params: PageParams,
        sort: SortParams,
        search_term: str | None = None,
        **filters: Any,
    ) -> PaginatedResponse[ResponseSchemaT]:
        results, total = await self.list_paginated(page_params, sort, search_term, **filters)
        return PaginatedResponse(
            data=[self._to_response(r) for r in results],
            meta=build_pagination_meta(total=total, params=page_params),
        )

    def _to_response(self, instance: ModelT) -> ResponseSchemaT:
        return ResponseSchemaT.model_validate(instance)  # type: ignore[misc,no-any-return]

    async def _get_by_id(
        self, id: uuid.UUID, model_class: type[ModelT] | None = None
    ) -> ModelT | None:
        mc = model_class or self.model_class
        stmt = select(mc).where(mc.id == id)  # type: ignore[attr-defined]
        if issubclass(mc, SoftDeleteMixin):
            stmt = stmt.where(mc.deleted_at.is_(None))
        return (  # type: ignore[no-any-return]
            await self._session.execute(stmt)
        ).scalar_one_or_none()
