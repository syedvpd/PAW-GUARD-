"""Minimal data-backup export for super_admin (PRR §2.1: "data backups").

Scope is intentionally export-only: triggers a full `pg_dump` of the
database, uploads it to the existing S3/media bucket under `backups/`, and
lists past exports for download. There is no restore-execution endpoint -
restoring a dump into a live database is a much higher-risk operation
(wrong target, downtime, silent data loss) that needs its own deliberate,
reviewed rollout rather than a generic API call. Until that exists, restoring
one of these dumps is an operator running `pg_restore` by hand.
"""

import asyncio
import uuid
from datetime import UTC, datetime

from pawguard.core.config import get_settings
from pawguard.core.exceptions import UpstreamServiceError
from pawguard.core.logging import get_logger
from pawguard.modules.auth.models import AuthAuditEventType
from pawguard.services.audit_service import AuditService
from pawguard.services.storage_service import StorageService

logger = get_logger(__name__)

BACKUP_PREFIX = "backups"


def _pg_dump_url(database_url: str) -> str:
    """pg_dump needs a plain postgresql:// URL; our configured database_url
    is normalized to the asyncpg driver form for SQLAlchemy."""
    if database_url.startswith("postgresql+asyncpg://"):
        return "postgresql://" + database_url[len("postgresql+asyncpg://") :]
    return database_url


class BackupService:
    def __init__(self, audit_service: AuditService, storage: StorageService | None = None) -> None:
        self._audit = audit_service
        self._storage = storage or StorageService()

    async def create_backup(
        self, *, actor_id: uuid.UUID, ip_address: str | None, user_agent: str | None
    ) -> dict:
        settings = get_settings()
        if not settings.database_url:
            raise UpstreamServiceError("No database configured to back up.")

        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        object_key = f"{BACKUP_PREFIX}/pawguard_{timestamp}.dump"

        dump_bytes = await asyncio.to_thread(self._run_pg_dump, settings.database_url)

        await asyncio.to_thread(
            self._storage.put_object,
            object_key=object_key,
            content=dump_bytes,
            content_type="application/octet-stream",
        )

        await self._audit.record(
            event_type=AuthAuditEventType.BACKUP_CREATED,
            actor_id=actor_id,
            ip_address=ip_address,
            user_agent=user_agent,
            metadata={"object_key": object_key, "size_bytes": len(dump_bytes)},
        )

        return {
            "key": object_key,
            "size_bytes": len(dump_bytes),
            "created_at": timestamp,
        }

    def _run_pg_dump(self, database_url: str) -> bytes:
        import subprocess

        pg_url = _pg_dump_url(database_url)
        try:
            result = subprocess.run(
                ["pg_dump", "--format=custom", "--no-owner", "--no-privileges", pg_url],
                capture_output=True,
                check=True,
                timeout=600,
            )
        except FileNotFoundError as exc:
            raise UpstreamServiceError(
                "pg_dump is not available on this server - install the PostgreSQL "
                "client tools to enable backups."
            ) from exc
        except subprocess.CalledProcessError as exc:
            logger.error("backup_pg_dump_failed", stderr=exc.stderr.decode(errors="replace"))
            raise UpstreamServiceError("Database backup failed - see server logs.") from exc
        except subprocess.TimeoutExpired as exc:
            raise UpstreamServiceError("Database backup timed out.") from exc
        return result.stdout

    def list_backups(self) -> list[dict]:
        objects = self._storage.list_objects(prefix=f"{BACKUP_PREFIX}/")
        return [
            {
                "key": obj["key"],
                "size_bytes": obj["size"],
                "created_at": obj["last_modified"],
                "download_url": self._storage.generate_presigned_download_url(
                    object_key=obj["key"]
                ),
            }
            for obj in objects
        ]


def _backup_created_event():
    from pawguard.modules.auth.models import AuthAuditEventType

    return AuthAuditEventType.BACKUP_CREATED
