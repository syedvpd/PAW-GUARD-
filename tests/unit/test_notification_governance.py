"""Unit test suite for PawGuard Centralized Push Notification Governance Engine."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ForbiddenError, ValidationFailedError
from pawguard.modules.auth.models import User
from pawguard.modules.notifications.governance_service import NotificationGovernanceService
from pawguard.modules.notifications.models import (
    NotificationApprovalQueue,
    NotificationGlobalConfig,
    NotificationGovernanceAuditLog,
    NotificationModuleConfig,
    NotificationTriggerConfig,
)


@pytest.fixture
async def admin_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"admin-{uuid.uuid4().hex[:6]}@pawguard.org",
        full_name="Test Admin User",
        hashed_password="hashed_pass_test",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def gov_service(db_session: AsyncSession) -> NotificationGovernanceService:
    service = NotificationGovernanceService(db_session)
    await service.ensure_seed_defaults()
    return service


@pytest.mark.asyncio
async def test_disabled_trigger_blocks_notification(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    # Disable trigger
    (
        await db_session.execute(
            NotificationTriggerConfig.__table__.select().where(
                NotificationTriggerConfig.trigger_code == "rescue_dispatched"
            )
        )
    ).first()
    await db_session.execute(
        NotificationTriggerConfig.__table__.update()
        .where(NotificationTriggerConfig.trigger_code == "rescue_dispatched")
        .values(push_status="DISABLED")
    )

    action, item = await gov_service.process_event(
        trigger_code="rescue_dispatched",
        module_name="rescue",
        title="Officer Dispatched",
        body="Team en route",
    )
    assert action == "BLOCKED"
    assert item is not None
    assert item.status == "BLOCKED"


@pytest.mark.asyncio
async def test_global_pause_blocks_notification(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    await db_session.execute(
        NotificationGlobalConfig.__table__.update().values(
            push_status="PAUSED", reason="Superadmin pause"
        )
    )

    action, item = await gov_service.process_event(
        trigger_code="rescue_dispatched",
        module_name="rescue",
        title="Officer Dispatched",
        body="Team en route",
    )
    assert action == "PAUSED"
    assert item is not None
    assert item.status == "PAUSED"
    assert item.pause_reason == "Global push notifications paused: Superadmin pause"


@pytest.mark.asyncio
async def test_module_pause_blocks_notification(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    await db_session.execute(
        NotificationModuleConfig.__table__.update()
        .where(NotificationModuleConfig.module_name == "lost_found")
        .values(push_status="PAUSED", reason="Lost & Found audit in progress")
    )

    action, item = await gov_service.process_event(
        trigger_code="lost_found_sighting",
        module_name="lost_found",
        title="Pet Sighting",
        body="Dog seen near park",
    )
    assert action == "PAUSED"
    assert item is not None
    assert item.status == "PAUSED"


@pytest.mark.asyncio
async def test_trigger_pause_blocks_notification(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    await db_session.execute(
        NotificationTriggerConfig.__table__.update()
        .where(NotificationTriggerConfig.trigger_code == "inventory_low_stock")
        .values(push_status="PAUSED")
    )

    action, item = await gov_service.process_event(
        trigger_code="inventory_low_stock",
        module_name="inventory",
        title="Low Stock Alert",
        body="Bandages running low",
    )
    assert action == "PAUSED"
    assert item is not None
    assert item.status == "PAUSED"


@pytest.mark.asyncio
async def test_approval_required_creates_pending_item(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    # lost_found_broadcast requires_approval=True by default
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Golden Retriever",
        body="Last seen at Central Mall",
    )
    assert action == "PENDING_APPROVAL"
    assert item is not None
    assert item.status == "PENDING_APPROVAL"


@pytest.mark.asyncio
async def test_approval_dispatches_notification(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Golden Retriever",
        body="Last seen at Central Mall",
    )
    assert item is not None

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        approved_item = await gov_service.approve_notification(
            queue_id=item.id,
            actor_user_id=admin_user.id,
        )
        assert approved_item.status == "SENT"
        assert approved_item.approved_at is not None
        mock_fcm.assert_called_once()


@pytest.mark.asyncio
async def test_rejection_prevents_dispatch(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog Broadcast",
        body="Missing puppy",
    )
    assert item is not None

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        rejected_item = await gov_service.reject_notification(
            queue_id=item.id,
            actor_user_id=admin_user.id,
            reason="Incorrect description",
        )
        assert rejected_item.status == "REJECTED"
        assert rejected_item.rejection_reason == "Incorrect description"
        mock_fcm.assert_not_called()


@pytest.mark.asyncio
async def test_paused_notification_does_not_dispatch(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog",
        body="Missing pet",
    )
    assert item is not None

    paused_item = await gov_service.pause_notification(
        queue_id=item.id,
        actor_user_id=admin_user.id,
        reason="Verification needed",
    )
    assert paused_item.status == "PAUSED"

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        with pytest.raises(ValidationFailedError):
            await gov_service.approve_notification(queue_id=item.id, actor_user_id=admin_user.id)
        mock_fcm.assert_not_called()


@pytest.mark.asyncio
async def test_resume_allows_dispatch(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog Broadcast",
        body="Missing beagle",
    )
    assert item is not None

    await gov_service.pause_notification(queue_id=item.id, actor_user_id=admin_user.id)
    resumed_item = await gov_service.resume_notification(
        queue_id=item.id, actor_user_id=admin_user.id
    )
    assert resumed_item.status == "PENDING_APPROVAL"

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        approved_item = await gov_service.approve_notification(
            queue_id=item.id, actor_user_id=admin_user.id
        )
        assert approved_item.status == "SENT"
        mock_fcm.assert_called_once()


@pytest.mark.asyncio
async def test_disabled_after_creation_blocks_approval(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog Broadcast",
        body="Missing terrier",
    )
    assert item is not None

    # Superadmin disables trigger after item entered approval queue
    await db_session.execute(
        NotificationTriggerConfig.__table__.update()
        .where(NotificationTriggerConfig.trigger_code == "lost_found_broadcast")
        .values(push_status="DISABLED")
    )

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        with pytest.raises(ForbiddenError):
            await gov_service.approve_notification(queue_id=item.id, actor_user_id=admin_user.id)
        mock_fcm.assert_not_called()


@pytest.mark.asyncio
async def test_duplicate_approval_only_dispatches_once(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog Broadcast",
        body="Missing husky",
    )
    assert item is not None

    with patch.object(gov_service, "_dispatch_fcm", new_callable=AsyncMock) as mock_fcm:
        first_approval = await gov_service.approve_notification(
            queue_id=item.id, actor_user_id=admin_user.id
        )
        assert first_approval.status == "SENT"
        assert mock_fcm.call_count == 1

        with pytest.raises(ValidationFailedError):
            await gov_service.approve_notification(queue_id=item.id, actor_user_id=admin_user.id)
        assert mock_fcm.call_count == 1


@pytest.mark.asyncio
async def test_expired_notification_cannot_be_approved(
    gov_service: NotificationGovernanceService, admin_user: User, db_session: AsyncSession
) -> None:
    action, item = await gov_service.process_event(
        trigger_code="lost_found_broadcast",
        module_name="lost_found",
        title="Lost Dog Broadcast",
        body="Missing lab",
    )
    assert item is not None

    # Set item as expired in past
    await db_session.execute(
        NotificationApprovalQueue.__table__.update()
        .where(NotificationApprovalQueue.id == item.id)
        .values(expires_at=datetime.now(UTC) - timedelta(hours=1))
    )

    with pytest.raises(ValidationFailedError, match="Notification has expired"):
        await gov_service.approve_notification(queue_id=item.id, actor_user_id=admin_user.id)


@pytest.mark.asyncio
async def test_audit_log_created_for_every_action(
    gov_service: NotificationGovernanceService, db_session: AsyncSession
) -> None:
    uuid.uuid4()
    action, item = await gov_service.process_event(
        trigger_code="rescue_dispatched",
        module_name="rescue",
        title="Dispatch Officer",
        body="Emergency alert",
    )

    logs = (
        await db_session.execute(
            NotificationGovernanceAuditLog.__table__.select().where(
                NotificationGovernanceAuditLog.trigger_code == "rescue_dispatched"
            )
        )
    ).all()
    assert len(logs) >= 1
    assert logs[-1].action == "SENT"
