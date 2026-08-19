"""Central Push Notification Governance & Admin Approval Engine.

Implements the 3-tier governance check (Global -> Module -> Trigger), atomic
approval queue workflows, immutable audit logging, and FCM dispatch gating.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.exceptions import ForbiddenError, NotFoundError, ValidationFailedError
from pawguard.core.logging import get_logger
from pawguard.modules.notifications.models import (
    NotificationApprovalQueue,
    NotificationGlobalConfig,
    NotificationGovernanceAuditLog,
    NotificationModuleConfig,
    NotificationTriggerConfig,
)

logger = get_logger(__name__)

DEFAULT_TRIGGERS = [
    # Rescue
    ("rescue_incident_reported", "rescue", "Rescue Incident Reported", True, True, False, "HIGH"),
    ("rescue_dispatched", "rescue", "Rescue Officer Dispatched", True, True, False, "HIGH"),
    ("rescue_admitted", "rescue", "Animal Admitted to Shelter", True, True, False, "HIGH"),
    ("rescue_emergency", "rescue", "Emergency Rescue Escalated", True, True, False, "HIGH"),
    # Lost & Found
    ("lost_found_broadcast", "lost_found", "Lost Dog Area Broadcast", True, True, True, "HIGH"),
    ("lost_found_sighting", "lost_found", "Pet Sighting Reported", True, True, False, "HIGH"),
    ("lost_found_match", "lost_found", "Lost & Found Match Detected", True, True, False, "HIGH"),
    ("lost_found_claim", "lost_found", "Ownership Claim Update", True, True, False, "NORMAL"),
    # Adoption
    ("adoption_submitted", "adoption", "Adoption Application Received", True, True, False, "NORMAL"),
    ("adoption_approved", "adoption", "Adoption Application Approved", True, True, False, "HIGH"),
    ("adoption_rejected", "adoption", "Adoption Application Update", True, True, False, "NORMAL"),
    ("adoption_completed", "adoption", "Pet Adoption Completed", True, True, False, "HIGH"),
    # Foster
    ("foster_applied", "foster", "Foster Application Submitted", True, True, False, "NORMAL"),
    ("foster_approved", "foster", "Foster Profile Approved", True, True, False, "HIGH"),
    ("foster_placed", "foster", "Pet Placed with Foster", True, True, False, "HIGH"),
    # Companion Pet
    ("safety_tag_scanned", "companion_pet", "Safety Tag Scanned Alert", True, True, False, "HIGH"),
    ("pet_appointment_reminder", "companion_pet", "Veterinary Appointment Reminder", True, True, False, "NORMAL"),
    ("pet_vaccination_due", "companion_pet", "Pet Vaccination Due Alert", True, True, False, "NORMAL"),
    # Donation
    ("donation_received", "donation", "Donation Receipt & Thank You", True, True, False, "NORMAL"),
    ("sponsorship_created", "donation", "Pet Sponsorship Started", True, True, False, "NORMAL"),
    ("donation_campaign_alert", "donation", "Donation Campaign Alert", True, True, False, "NORMAL"),
    # Inventory
    ("inventory_low_stock", "inventory", "Low Stock Alert", True, True, False, "HIGH"),
    ("inventory_expiring", "inventory", "Medication Expiry Warning", True, True, False, "HIGH"),
    # Auth
    ("auth_password_reset", "auth", "Password Reset Requested", True, True, False, "HIGH"),
    ("auth_mfa_changed", "auth", "MFA Settings Updated", True, True, False, "HIGH"),
    # Grievance
    ("grievance_assigned", "grievance", "Grievance Assigned to Staff", True, True, False, "NORMAL"),
    ("grievance_escalated", "grievance", "Grievance SLA Escalation Alert", True, True, False, "HIGH"),
    # Fleet
    ("fleet_maintenance_due", "fleet", "Vehicle Maintenance Overdue", True, True, False, "HIGH"),
    ("fleet_equipment_overdue", "fleet", "Rescue Equipment Overdue", True, True, False, "HIGH"),
    # Volunteer
    ("volunteer_application_update", "volunteer", "Volunteer Application Update", True, True, False, "NORMAL"),
    ("volunteer_shift_reminder", "volunteer", "Volunteer Shift Reminder", True, True, False, "NORMAL"),
]


class GovernanceCheckResult:
    def __init__(self, action: str, reason: str | None = None, trigger_config: NotificationTriggerConfig | None = None) -> None:
        self.action = action  # "SEND_IMMEDIATELY", "BLOCKED", "PAUSED", "PENDING_APPROVAL"
        self.reason = reason
        self.trigger_config = trigger_config


class NotificationGovernanceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_seed_defaults(self) -> None:
        """Seed default global, module, and trigger configurations if missing."""
        global_cfg = (await self._session.execute(select(NotificationGlobalConfig))).scalars().first()
        if global_cfg is None:
            self._session.add(NotificationGlobalConfig(push_status="ENABLED"))

        existing_triggers = {
            t.trigger_code: t for t in (await self._session.execute(select(NotificationTriggerConfig))).scalars().all()
        }
        for code, mod, name, push_en, email_en, req_appr, prio in DEFAULT_TRIGGERS:
            if code not in existing_triggers:
                self._session.add(
                    NotificationTriggerConfig(
                        trigger_code=code,
                        module_name=mod,
                        display_name=name,
                        push_status="ENABLED" if push_en else "DISABLED",
                        email_enabled=email_en,
                        requires_approval=req_appr,
                        default_priority=prio,
                    )
                )

        existing_modules = {
            m.module_name: m for m in (await self._session.execute(select(NotificationModuleConfig))).scalars().all()
        }
        unique_modules = {mod for _, mod, _, _, _, _, _ in DEFAULT_TRIGGERS}
        for mod in unique_modules:
            if mod not in existing_modules:
                self._session.add(NotificationModuleConfig(module_name=mod, push_status="ENABLED"))

        await self._session.flush()

    async def evaluate_governance(self, trigger_code: str, module_name: str) -> GovernanceCheckResult:
        """Evaluate 3-tier governance rules (Global -> Module -> Trigger)."""
        await self.ensure_seed_defaults()

        # Level 1: Global check
        global_cfg = (await self._session.execute(select(NotificationGlobalConfig))).scalars().first()
        if global_cfg is not None:
            if global_cfg.push_status == "DISABLED":
                return GovernanceCheckResult("BLOCKED", "Global push notifications disabled by Superadmin.")
            if global_cfg.push_status == "PAUSED":
                return GovernanceCheckResult("PAUSED", f"Global push notifications paused: {global_cfg.reason or 'Superadmin pause'}")

        # Level 2: Module check
        mod_stmt = select(NotificationModuleConfig).where(NotificationModuleConfig.module_name == module_name)
        mod_cfg = (await self._session.execute(mod_stmt)).scalars().first()
        if mod_cfg is not None:
            if mod_cfg.push_status == "DISABLED":
                return GovernanceCheckResult("BLOCKED", f"Push notifications disabled for module '{module_name}'.")
            if mod_cfg.push_status == "PAUSED":
                return GovernanceCheckResult("PAUSED", f"Module '{module_name}' notifications paused: {mod_cfg.reason or 'Admin pause'}")

        # Level 3: Trigger check
        trig_stmt = select(NotificationTriggerConfig).where(NotificationTriggerConfig.trigger_code == trigger_code)
        trig_cfg = (await self._session.execute(trig_stmt)).scalars().first()
        if trig_cfg is not None:
            if trig_cfg.push_status == "DISABLED":
                return GovernanceCheckResult("BLOCKED", f"Trigger '{trigger_code}' disabled.", trigger_config=trig_cfg)
            if trig_cfg.push_status == "PAUSED":
                return GovernanceCheckResult("PAUSED", f"Trigger '{trigger_code}' paused.", trigger_config=trig_cfg)
            if trig_cfg.requires_approval:
                return GovernanceCheckResult("PENDING_APPROVAL", f"Trigger '{trigger_code}' requires Admin approval.", trigger_config=trig_cfg)

        return GovernanceCheckResult("SEND_IMMEDIATELY", trigger_config=trig_cfg)

    async def process_event(
        self,
        *,
        trigger_code: str,
        module_name: str,
        title: str,
        body: str,
        target_user_ids: list[uuid.UUID] | None = None,
        action_url: str | None = None,
        image_url: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        requested_by: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> tuple[str, NotificationApprovalQueue | None]:
        """Central entry point for all modules sending push notifications.

        Evaluates governance rules and either dispatches immediately via FCM,
        places in approval queue, or marks as paused/blocked.
        """
        gov = await self.evaluate_governance(trigger_code, module_name)
        recip_count = len(target_user_ids) if target_user_ids else 1
        prio = gov.trigger_config.default_priority if gov.trigger_config else "HIGH"

        item = NotificationApprovalQueue(
            trigger_code=trigger_code,
            module_name=module_name,
            title=title,
            body=body,
            action_url=action_url,
            image_url=image_url,
            metadata_json=metadata_json or {},
            recipient_count=recip_count,
            target_user_ids=[str(uid) for uid in target_user_ids] if target_user_ids else None,
            priority=prio,
            status="PENDING_APPROVAL" if gov.action == "PENDING_APPROVAL" else gov.action,
            pause_reason=gov.reason if gov.action == "PAUSED" else None,
            requested_by=requested_by,
        )

        if gov.action == "SEND_IMMEDIATELY":
            item.status = "SENT"
            item.approved_at = datetime.now(UTC)
            self._session.add(item)
            await self._session.flush()

            # Execute FCM Push Dispatch
            await self._dispatch_fcm(target_user_ids, title, body, action_url)
            await self.record_audit(
                notification_id=item.id,
                trigger_code=trigger_code,
                module_name=module_name,
                actor_user_id=requested_by,
                action="SENT",
                new_status="SENT",
                reason="Auto-approved governance dispatch.",
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return "SENT", item

        elif gov.action == "PENDING_APPROVAL":
            item.status = "PENDING_APPROVAL"
            self._session.add(item)
            await self._session.flush()
            await self.record_audit(
                notification_id=item.id,
                trigger_code=trigger_code,
                module_name=module_name,
                actor_user_id=requested_by,
                action="CREATED",
                new_status="PENDING_APPROVAL",
                reason=gov.reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return "PENDING_APPROVAL", item

        elif gov.action == "PAUSED":
            item.status = "PAUSED"
            item.paused_at = datetime.now(UTC)
            self._session.add(item)
            await self._session.flush()
            await self.record_audit(
                notification_id=item.id,
                trigger_code=trigger_code,
                module_name=module_name,
                actor_user_id=requested_by,
                action="PAUSED",
                new_status="PAUSED",
                reason=gov.reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return "PAUSED", item

        else:  # BLOCKED
            item.status = "BLOCKED"
            self._session.add(item)
            await self._session.flush()
            await self.record_audit(
                notification_id=item.id,
                trigger_code=trigger_code,
                module_name=module_name,
                actor_user_id=requested_by,
                action="BLOCKED",
                new_status="BLOCKED",
                reason=gov.reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return "BLOCKED", item

    async def approve_notification(
        self,
        queue_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_role: str = "admin",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationApprovalQueue:
        """Atomic approval of a pending notification item with FOR UPDATE locking."""
        stmt = (
            select(NotificationApprovalQueue)
            .where(NotificationApprovalQueue.id == queue_id)
            .with_for_update()
        )
        item = (await self._session.execute(stmt)).scalars().first()
        if item is None:
            raise NotFoundError("Queued notification not found.")

        if item.status != "PENDING_APPROVAL":
            raise ValidationFailedError(f"Cannot approve notification in status '{item.status}'. Please resume the notification first.")

        if item.expires_at and item.expires_at < datetime.now(UTC):
            item.status = "EXPIRED"
            await self.record_audit(
                notification_id=item.id,
                trigger_code=item.trigger_code,
                module_name=item.module_name,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="EXPIRED",
                previous_status="PENDING_APPROVAL",
                new_status="EXPIRED",
                reason="Item expired before approval.",
            )
            raise ValidationFailedError("Notification has expired and cannot be approved.")

        # Re-evaluate 3-tier governance rules at approval time
        gov = await self.evaluate_governance(item.trigger_code, item.module_name)
        if gov.action == "BLOCKED":
            raise ForbiddenError(f"Cannot approve: {gov.reason}")
        if gov.action == "PAUSED":
            item.status = "PAUSED"
            item.pause_reason = gov.reason
            item.paused_at = datetime.now(UTC)
            await self.record_audit(
                notification_id=item.id,
                trigger_code=item.trigger_code,
                module_name=item.module_name,
                actor_user_id=actor_user_id,
                actor_role=actor_role,
                action="PAUSED",
                previous_status="PENDING_APPROVAL",
                new_status="PAUSED",
                reason=gov.reason,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            return item

        # Approve and dispatch
        old_status = item.status
        item.status = "SENT"
        item.reviewed_by = actor_user_id
        item.reviewed_at = datetime.now(UTC)
        item.approved_at = datetime.now(UTC)

        target_uids = [uuid.UUID(uid) for uid in item.target_user_ids] if item.target_user_ids else None
        await self._dispatch_fcm(target_uids, item.title, item.body, item.action_url)

        await self.record_audit(
            notification_id=item.id,
            trigger_code=item.trigger_code,
            module_name=item.module_name,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="APPROVED",
            previous_status=old_status,
            new_status="SENT",
            reason="Approved by Admin.",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return item

    async def reject_notification(
        self,
        queue_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str | None = None,
        actor_role: str = "admin",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationApprovalQueue:
        stmt = (
            select(NotificationApprovalQueue)
            .where(NotificationApprovalQueue.id == queue_id)
            .with_for_update()
        )
        item = (await self._session.execute(stmt)).scalars().first()
        if item is None:
            raise NotFoundError("Queued notification not found.")

        if item.status not in ("PENDING_APPROVAL", "PAUSED"):
            raise ValidationFailedError(f"Cannot reject notification in status '{item.status}'.")

        old_status = item.status
        item.status = "REJECTED"
        item.reviewed_by = actor_user_id
        item.reviewed_at = datetime.now(UTC)
        item.rejected_at = datetime.now(UTC)
        item.rejection_reason = reason or "Rejected by Admin."

        await self.record_audit(
            notification_id=item.id,
            trigger_code=item.trigger_code,
            module_name=item.module_name,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="REJECTED",
            previous_status=old_status,
            new_status="REJECTED",
            reason=reason or "Rejected by Admin.",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return item

    async def pause_notification(
        self,
        queue_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str | None = None,
        actor_role: str = "admin",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationApprovalQueue:
        stmt = (
            select(NotificationApprovalQueue)
            .where(NotificationApprovalQueue.id == queue_id)
            .with_for_update()
        )
        item = (await self._session.execute(stmt)).scalars().first()
        if item is None:
            raise NotFoundError("Queued notification not found.")

        old_status = item.status
        item.status = "PAUSED"
        item.paused_at = datetime.now(UTC)
        item.pause_reason = reason or "Paused by Admin."

        await self.record_audit(
            notification_id=item.id,
            trigger_code=item.trigger_code,
            module_name=item.module_name,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="PAUSED",
            previous_status=old_status,
            new_status="PAUSED",
            reason=reason or "Paused by Admin.",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return item

    async def resume_notification(
        self,
        queue_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        actor_role: str = "admin",
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationApprovalQueue:
        stmt = (
            select(NotificationApprovalQueue)
            .where(NotificationApprovalQueue.id == queue_id)
            .with_for_update()
        )
        item = (await self._session.execute(stmt)).scalars().first()
        if item is None:
            raise NotFoundError("Queued notification not found.")

        if item.status != "PAUSED":
            raise ValidationFailedError(f"Cannot resume notification in status '{item.status}'.")

        gov = await self.evaluate_governance(item.trigger_code, item.module_name)
        if gov.action == "PAUSED":
            raise ValidationFailedError(f"Cannot resume: {gov.reason}")
        if gov.action == "BLOCKED":
            item.status = "BLOCKED"
            return item

        old_status = item.status
        item.status = "PENDING_APPROVAL" if gov.action == "PENDING_APPROVAL" else "QUEUED"
        item.paused_at = None
        item.pause_reason = None

        await self.record_audit(
            notification_id=item.id,
            trigger_code=item.trigger_code,
            module_name=item.module_name,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action="RESUMED",
            previous_status=old_status,
            new_status=item.status,
            reason="Resumed by Admin.",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return item

    async def _dispatch_fcm(
        self,
        target_user_ids: list[uuid.UUID] | None,
        title: str,
        body: str,
        action_url: str | None,
    ) -> None:
        """Internal helper to dispatch push via FCM."""
        from pawguard.modules.auth.models import User
        if target_user_ids:
            uids = target_user_ids
        else:
            # Broadcast to all active users with fcm_token
            stmt = select(User.id).where(
                User.is_active.is_(True),
                User.deleted_at.is_(None),
                User.fcm_token.isnot(None),
                User.fcm_token != "",
            )
            uids = list((await self._session.execute(stmt)).scalars().all())

        if not uids:
            return

        from pawguard.modules.notifications.repository import NotificationRepository
        from pawguard.modules.notifications.service import NotificationService
        notif_svc = NotificationService(NotificationRepository(self._session))
        await notif_svc._send_push_to_users(uids, title, body, action_url)

    async def record_audit(
        self,
        *,
        trigger_code: str,
        module_name: str,
        action: str,
        notification_id: uuid.UUID | None = None,
        actor_user_id: uuid.UUID | None = None,
        actor_role: str | None = None,
        previous_status: str | None = None,
        new_status: str | None = None,
        reason: str | None = None,
        metadata_json: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> NotificationGovernanceAuditLog:
        """Create an immutable governance audit record."""
        log = NotificationGovernanceAuditLog(
            notification_id=notification_id,
            trigger_code=trigger_code,
            module_name=module_name,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            action=action,
            previous_status=previous_status,
            new_status=new_status,
            reason=reason,
            metadata_json=metadata_json,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self._session.add(log)
        await self._session.flush()
        return log
