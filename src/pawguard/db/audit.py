"""Request-scoped actor tracking for automatic audit-stamp population.

Routers resolve the current user via the auth dependencies in
``pawguard.modules.auth.dependencies``. Those dependencies call :func:`set_actor`
so the value is available later when SQLAlchemy flushes pending changes.

A ``before_flush`` listener then stamps ``created_by`` / ``updated_by`` on every
``AuditMixin`` row that is inserted or updated, using the actor captured for the
current request. Background tasks and system processes run without an actor, so
the columns stay NULL (a deliberate "system" marker).

This keeps the audit trail consistent across *all* modules without duplicating
stamping logic in every service (RULE-003: services own behaviour; this is
cross-cutting infrastructure).
"""

from contextvars import ContextVar
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.orm import Session

from pawguard.db.mixins import AuditMixin

# None => no authenticated actor (system / background work).
_actor_id: ContextVar[UUID | None] = ContextVar("audit_actor_id", default=None)


def set_actor(user_id: UUID | None) -> None:
    """Record the acting user for the current execution context.

    Safe to call within a request task; the value is local to that task's
    context and does not leak across requests.
    """

    _actor_id.set(user_id)


def get_actor() -> UUID | None:
    return _actor_id.get()


@event.listens_for(Session, "before_flush")
def _stamp_audit_columns(
    session: Session, flush_context: object, instances: object
) -> None:
    actor = _actor_id.get()
    if actor is None:
        return

    for instance in session.new:
        if isinstance(instance, AuditMixin):
            if instance.created_by is None:
                instance.created_by = actor
            instance.updated_by = actor

    for instance in session.dirty:
        if not isinstance(instance, AuditMixin):
            continue
        if not session.is_modified(instance, include_collections=False):
            continue
        instance.updated_by = actor
