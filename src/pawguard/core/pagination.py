"""Offset-based pagination helpers shared by all list endpoints."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Query

from pawguard.core.responses import PaginationMeta


@dataclass(slots=True)
class PageParams:
    page: int = 1
    page_size: int = 20

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def page_params(
    page: Annotated[int, Query(ge=1, description="Page number (1-indexed)")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Number of items per page")] = 20,
) -> PageParams:
    return PageParams(page=page, page_size=page_size)


def build_pagination_meta(*, total: int, params: PageParams) -> PaginationMeta:
    total_pages = (total + params.page_size - 1) // params.page_size if total else 0
    return PaginationMeta(
        total=total,
        page=params.page,
        page_size=params.page_size,
        total_pages=total_pages,
    )
