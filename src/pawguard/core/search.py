"""Reusable search/filter/sort utilities for repository-level query building.

Provides helpers to apply dynamic filters, full-text search, and sorting
to SQLAlchemy queries in a consistent way across all modules.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Query
from sqlalchemy import ColumnElement, Unicode, asc, cast, desc

from pawguard.core.exceptions import ValidationFailedError


@dataclass(slots=True)
class SortParams:
    sort_by: str = "created_at"
    sort_order: str = "desc"

    @property
    def is_descending(self) -> bool:
        return self.sort_order.lower() == "desc"


def sort_params(
    sort_by: Annotated[str, Query(description="Field to sort by")] = "created_at",
    sort_order: Annotated[
        str, Query(pattern="^(asc|desc)$", description="Sort direction: asc or desc")
    ] = "desc",
) -> SortParams:
    return SortParams(sort_by=sort_by, sort_order=sort_order)


def apply_sorting(
    stmt: Any,
    sort: SortParams,
    valid_fields: set[str],
    default_field: str = "created_at",
) -> Any:
    if sort.sort_by in valid_fields:
        field = sort.sort_by
    elif sort.sort_by == "created_at":
        # The shared dependency defaults to `created_at` even when a module's
        # allowlist uses a different field (e.g. fleet fuel sorts by filled_at).
        # Treat that as "no explicit sort choice" and use the module default so
        # default-sorted requests keep working.
        field = default_field
    else:
        allowed = ", ".join(sorted(valid_fields))
        raise ValidationFailedError(f"Invalid sort_by '{sort.sort_by}'. Allowed fields: {allowed}.")
    column = getattr(stmt.get_final_froms()[0].columns, field, None)
    if column is None:
        return stmt
    order_fn = desc if sort.is_descending else asc
    return stmt.order_by(order_fn(column))


def build_search_filter(
    model: Any,
    search_term: str | None,
    search_fields: Sequence[str],
) -> ColumnElement[bool] | None:
    if not search_term:
        return None
    sanitized = search_term.strip().lower()
    if not sanitized:
        return None
    conditions: list[ColumnElement[bool]] = []
    search_pattern = f"%{sanitized}%"
    for field_name in search_fields:
        column = getattr(model, field_name, None)
        if column is not None:
            conditions.append(cast(column, Unicode).ilike(search_pattern))
    if not conditions:
        return None
    from sqlalchemy import or_

    return or_(*conditions)
