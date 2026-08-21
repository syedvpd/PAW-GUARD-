"""Unit tests for reusable search/sort helpers (apply_sorting validation)."""

import pytest
from sqlalchemy import select

from pawguard.core.exceptions import ValidationFailedError
from pawguard.core.search import SortParams, apply_sorting
from pawguard.modules.notifications.models import Notification


def _stmt():
    return select(Notification)


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True}))


class TestApplySortingValidation:
    def test_valid_field_desc_default(self):
        stmt = apply_sorting(_stmt(), SortParams(sort_by="title"), {"title", "created_at"})
        assert "ORDER BY notifications.title DESC" in _sql(stmt)

    def test_valid_field_asc(self):
        stmt = apply_sorting(
            _stmt(), SortParams(sort_by="title", sort_order="asc"), {"title", "created_at"}
        )
        assert "ORDER BY notifications.title ASC" in _sql(stmt)

    def test_invalid_field_raises_422(self):
        with pytest.raises(ValidationFailedError) as exc_info:
            apply_sorting(_stmt(), SortParams(sort_by="bogus"), {"title", "created_at"})
        assert exc_info.value.status_code == 422
        assert "bogus" in exc_info.value.message
        assert "title" in exc_info.value.message

    def test_global_default_created_at_falls_back_when_not_allowed(self):
        # Modules like fleet fuel allow sort by "filled_at" but not "created_at";
        # the shared dependency defaults sort_by="created_at", which must be
        # treated as "no explicit choice" rather than rejected.
        stmt = apply_sorting(_stmt(), SortParams(), {"sent_at"}, default_field="sent_at")
        assert "ORDER BY notifications.sent_at DESC" in _sql(stmt)

    def test_default_sort_by_uses_allowed_created_at(self):
        stmt = apply_sorting(_stmt(), SortParams(), {"title", "created_at"})
        assert "ORDER BY notifications.created_at DESC" in _sql(stmt)
