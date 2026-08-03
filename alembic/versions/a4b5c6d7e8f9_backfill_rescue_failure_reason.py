"""backfill_rescue_failure_reason

Revision ID: a4b5c6d7e8f9
Revises: f9e8d7c6b5a4
Create Date: 2026-08-02 15:00:00.000000

Backfills legacy free-text `rescue_dispatches.failure_reason` values to the
canonical `RescueFailureReason` outcome codes defined by PRR 3.3
(animal_fled / area_inaccessible / false_report /
local_intervention_blocked). Known labels map to their code; anything else
(including the old "Failed rescue" default) falls back to 'other' so a failed
rescue always keeps a usable, groupable reason.

The column stays String(255) (unchanged from the original core-modules
migration) - the enum is the authoritative Python-level contract, and the API
layer normalises legacy labels on input as well.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4b5c6d7e8f9"
down_revision: str | None = "f9e8d7c6b5a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FAILURE_REASON_ALIASES: dict[str, str] = {
    "animal fled": "animal_fled",
    "animal fled area": "animal_fled",
    "fled": "animal_fled",
    "area inaccessible": "area_inaccessible",
    "inaccessible": "area_inaccessible",
    "false report": "false_report",
    "false alarm": "false_report",
    "local intervention blocked": "local_intervention_blocked",
    "intervention blocked": "local_intervention_blocked",
    "blocked": "local_intervention_blocked",
    # Canonical values pass through unchanged so the backfill is idempotent.
    "animal_fled": "animal_fled",
    "area_inaccessible": "area_inaccessible",
    "false_report": "false_report",
    "local_intervention_blocked": "local_intervention_blocked",
    "other": "other",
}


def _canonical(value: str) -> str:
    return _FAILURE_REASON_ALIASES.get(value.strip().lower(), "other")


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT failure_reason FROM rescue_dispatches "
            "WHERE failure_reason IS NOT NULL"
        )
    ).fetchall()
    for (value,) in rows:
        canonical = _canonical(value)
        if canonical != value:
            conn.execute(
                sa.text(
                    "UPDATE rescue_dispatches SET failure_reason = :canonical "
                    "WHERE failure_reason = :value"
                ),
                {"canonical": canonical, "value": value},
            )


def downgrade() -> None:
    # Irreversible: the original free-text values are gone after backfill.
    pass
