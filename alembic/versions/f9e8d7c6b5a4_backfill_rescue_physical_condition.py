"""backfill_rescue_physical_condition

Revision ID: f9e8d7c6b5a4
Revises: e2f4a6b8c0d2
Create Date: 2026-08-02 14:00:00.000000

Backfills legacy free-text `rescue_requests.physical_condition` values to the
canonical `RescuePhysicalCondition` enum values defined by PRR 3.2 intake
categories (critical_life_threatening / fractured_injured / contagious_sick /
malnourished / abandoned_stray). Any value that does not map to a known label
falls back to 'unknown' so no row loses the NOT NULL guarantee.

The column stays String(64) (same pattern as RescueStatus) - the enum is the
authoritative Python-level contract, and the API schema normalises legacy
labels on input as well.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f9e8d7c6b5a4"
down_revision: str | None = "e2f4a6b8c0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CONDITION_ALIASES: dict[str, str] = {
    "critical": "critical_life_threatening",
    "critical/life threatening": "critical_life_threatening",
    "life threatening": "critical_life_threatening",
    "injured": "fractured_injured",
    "fractured": "fractured_injured",
    "fractured/injured": "fractured_injured",
    "injured/fractured": "fractured_injured",
    "sick": "contagious_sick",
    "contagious": "contagious_sick",
    "contagious disease/sick": "contagious_sick",
    "malnourished": "malnourished",
    "stray": "abandoned_stray",
    "abandoned": "abandoned_stray",
    "abandoned/stray": "abandoned_stray",
    # Canonical values pass through unchanged so the backfill is idempotent
    # even when run against a DB that already holds canonical values
    # (malnourished and unknown are already self-mapped above).
    "critical_life_threatening": "critical_life_threatening",
    "fractured_injured": "fractured_injured",
    "contagious_sick": "contagious_sick",
    "abandoned_stray": "abandoned_stray",
}


def _canonical(value: str) -> str:
    key = value.strip().lower()
    return _CONDITION_ALIASES.get(key, "unknown")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT DISTINCT physical_condition FROM rescue_requests")
    ).fetchall()
    for (value,) in rows:
        canonical = _canonical(value)
        if canonical != value:
            conn.execute(
                sa.text(
                    "UPDATE rescue_requests SET physical_condition = :canonical "
                    "WHERE physical_condition = :value"
                ),
                {"canonical": canonical, "value": value},
            )


def downgrade() -> None:
    # Irreversible: the original free-text values are gone after backfill.
    pass
