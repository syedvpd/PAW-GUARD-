"""Logical database backup and restore (PRR 2.1: Super Administrator data backups).

A backup is one gzipped JSON document: ``{"format", "created_at", "alembic_version",
"tables": {name: [row, ...]}}`` with tables in foreign-key order. Short-lived auth
secrets (sessions, refresh/reset/verification tokens) are left out: a restore
signs everyone out, which is what you want after recovering a database.
"""

import base64
import gzip
import io
import json
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.db.base import Base

BACKUP_FORMAT = "pawguard-backup-v1"
EXCLUDED_TABLES = frozenset(
    {"user_sessions", "refresh_tokens", "password_reset_tokens", "email_verification_tokens"}
)


def _encode(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (uuid.UUID, Decimal)):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"$b64": base64.b64encode(bytes(value)).decode()}
    raise TypeError(f"Cannot serialise {type(value).__name__}")


def backup_tables() -> list:
    return [t for t in Base.metadata.sorted_tables if t.name not in EXCLUDED_TABLES]


async def _alembic_version(db: AsyncSession) -> str | None:
    try:
        async with db.begin_nested():
            return (await db.execute(text("SELECT version_num FROM alembic_version"))).scalar()
    except Exception:
        return None


async def build_backup(db: AsyncSession) -> tuple[bytes, dict[str, int]]:
    # ponytail: whole dump held in memory; stream to object storage if the DB outgrows RAM.
    counts: dict[str, int] = {}
    header = {
        "format": BACKUP_FORMAT,
        "created_at": datetime.now(UTC).isoformat(),
        "alembic_version": await _alembic_version(db),
    }
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb") as gz:
        gz.write(json.dumps(header)[:-1].encode() + b', "tables": {')
        for i, table in enumerate(backup_tables()):
            rows = (await db.execute(select(table))).mappings().all()
            counts[table.name] = len(rows)
            prefix = (", " if i else "") + json.dumps(table.name) + ": "
            gz.write(prefix.encode())
            gz.write(json.dumps([dict(r) for r in rows], default=_encode).encode())
        gz.write(b"}}")
    return buf.getvalue(), counts


def _decode(column, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict) and set(value) == {"$b64"}:
        return base64.b64decode(value["$b64"])
    try:
        python_type = column.type.python_type
    except NotImplementedError:
        return value
    if python_type is datetime:
        return datetime.fromisoformat(value)
    if python_type is date:
        return date.fromisoformat(value)
    if python_type is time:
        return time.fromisoformat(value)
    if python_type is uuid.UUID:
        return uuid.UUID(value)
    if python_type is Decimal:
        return Decimal(value)
    if isinstance(python_type, type) and issubclass(python_type, Enum):
        return python_type(value)
    return value


def read_backup(raw: bytes) -> dict[str, Any]:
    document = json.loads(gzip.decompress(raw))
    if document.get("format") != BACKUP_FORMAT:
        raise ValueError(f"Not a {BACKUP_FORMAT} file.")
    return document


async def restore_backup(db: AsyncSession, document: dict[str, Any]) -> dict[str, int]:
    """Load every row into a database migrated to the same revision that holds no users.

    Rows seeded by migrations (roles, permissions, settings) are cleared first so the
    backup's own IDs win and every foreign key lines up.
    """
    restored: dict[str, int] = {}
    tables = document["tables"]
    for table in reversed(backup_tables()):
        await db.execute(table.delete())
    for table in backup_tables():
        rows = tables.get(table.name) or []
        if not rows:
            continue
        columns = {c.name: c for c in table.columns}
        values = [
            {k: _decode(columns[k], v) for k, v in row.items() if k in columns} for row in rows
        ]
        await db.execute(table.insert(), values)
        restored[table.name] = len(values)
    return restored
