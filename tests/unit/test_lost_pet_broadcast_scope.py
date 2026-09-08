"""Unit tests for the geo-scoped lost-pet broadcast recipient query."""

import uuid

from sqlalchemy.dialects import postgresql

from pawguard.core.config import get_settings
from pawguard.workers.jobs.lost_found_jobs import recipient_stmt


def _compile(stmt):
    return stmt.compile(dialect=postgresql.dialect())


def _sql(stmt) -> str:
    return str(_compile(stmt))


class TestRecipientStmt:
    def test_report_without_coordinates_reaches_everyone(self):
        sql = _sql(recipient_stmt(uuid.uuid4(), None, None))
        assert "radians" not in sql
        assert "users.latitude" not in sql

    def test_report_with_coordinates_bounds_the_radius(self):
        compiled = _compile(recipient_stmt(uuid.uuid4(), 17.385044, 78.486671))
        assert "radians" in str(compiled)
        assert get_settings().lost_pet_broadcast_radius_km in compiled.params.values()

    def test_users_without_coordinates_are_still_included(self):
        sql = _sql(recipient_stmt(uuid.uuid4(), 17.385044, 78.486671))
        assert "users.latitude IS NULL" in sql
        assert "users.longitude IS NULL" in sql

    def test_reporter_is_always_excluded(self):
        for coords in ((None, None), (17.385044, 78.486671)):
            assert "users.id != " in _sql(recipient_stmt(uuid.uuid4(), *coords))


class TestHaversineFormula:
    """The SQL expression mirrors this arithmetic, so pin the arithmetic."""

    @staticmethod
    def _distance_km(lat1, lng1, lat2, lng2):
        import math

        p1, p2 = math.radians(lat1), math.radians(lat2)
        l1, l2 = math.radians(lng1), math.radians(lng2)
        a = (
            math.sin((p2 - p1) / 2) ** 2
            + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
        )
        return 2 * 6371.0 * math.asin(math.sqrt(a))

    def test_zero_distance(self):
        assert self._distance_km(17.385044, 78.486671, 17.385044, 78.486671) == 0.0

    def test_hyderabad_to_bangalore_is_roughly_500km(self):
        km = self._distance_km(17.385044, 78.486671, 12.971599, 77.594566)
        assert 490 < km < 510

    def test_neighbouring_suburb_is_inside_the_default_radius(self):
        km = self._distance_km(17.385044, 78.486671, 17.44, 78.39)
        assert km < get_settings().lost_pet_broadcast_radius_km
