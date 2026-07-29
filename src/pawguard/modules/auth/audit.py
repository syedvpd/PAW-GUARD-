"""Convenience factory wiring AuditService into the auth module's DI chain."""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.db.session import get_db
from pawguard.services.audit_service import AuditService


def get_audit_service(db: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(db)
