# Audit Logging System

## Overview

PawGuard maintains a comprehensive audit trail of all security-relevant and business-critical events. The audit system is implemented in `src/pawguard/services/audit_service.py` and uses the `auth_audit_logs` database table.

## Architecture

### AuditService
- Generic audit trail writer reused across all modules
- Writes to `auth_audit_logs` table
- Supports structured metadata, before/after state snapshots

### Storage
- PostgreSQL JSONB columns for metadata and state snapshots
- Indexed on `user_id`, `event_type`, and `created_at`

## Audit Event Types

### Authentication Events
- `login_success` - Successful login
- `login_failed` - Failed login attempt
- `logout` - User logout
- `logout_all` - Global logout
- `refresh` - Token refresh
- `refresh_reuse_detected` - Refresh token reuse (security breach)
- `password_change` - Password changed
- `password_reset_requested` - Password reset requested
- `password_reset_completed` - Password reset confirmed
- `email_verification_requested` - Email verification requested
- `email_verified` - Email verified
- `mfa_enrolled` - MFA enabled
- `mfa_verified` - MFA code verified
- `mfa_failed` - MFA verification failed
- `mfa_disabled` - MFA disabled
- `session_revoked` - Session revoked
- `account_locked` - Account locked (too many failed attempts)
- `registered` - New user registered
- `profile_updated` - Profile updated
- `oauth_login` - OAuth social login
- `oauth_linked` - OAuth account linked
- `oauth_unlinked` - OAuth account unlinked

### Admin Events
- `admin_user_created` - Admin created user
- `admin_user_updated` - Admin updated user
- `admin_user_deleted` - Admin deleted user
- `admin_role_created` - Admin created role
- `admin_role_updated` - Admin updated role
- `admin_role_deleted` - Admin deleted role

### Rescue Events
- `rescue_reported` - New rescue incident reported
- `rescue_verified` - Rescue request verified
- `rescue_rejected` - Rescue request rejected
- `rescue_dispatched` - Rescue team dispatched
- `rescue_status_updated` - Rescue status changed
- `rescue_deleted` - Rescue request deleted
- `rescue_coordinator_assigned` - Coordinator assigned
- `bulk_rescue_status_updated` - Bulk status update
- `bulk_rescue_deleted` - Bulk delete

### Dog Events
- `dog_registered` - New dog profile created
- `dog_updated` - Dog profile updated
- `dog_status_changed` - Dog status changed
- `dog_weight_recorded` - Weight measurement recorded
- `dog_deleted` - Dog profile deleted
- `bulk_dog_status_updated` - Bulk status update
- `bulk_dog_deleted` - Bulk delete

### Adoption Events
- `adoption_submitted` - Application submitted
- `adoption_updated` - Application updated
- `adoption_status_changed` - Application status changed
- `adoption_agreement_generated` - Agreement generated
- `adoption_deleted` - Application deleted
- `bulk_adoption_status_updated` - Bulk status update
- `bulk_adoption_deleted` - Bulk delete

### Foster Events
- `foster_application_submitted` - Application submitted
- `foster_application_updated` - Application updated
- `foster_placement_created` - Dog placed in foster
- `foster_placement_ended` - Foster placement ended
- `foster_supply_dispatched` - Supplies dispatched
- `foster_deleted` - Application deleted

### Medical Events
- `medical_record_created` - Medical record created
- `medical_record_updated` - Medical record updated
- `medical_record_deleted` - Medical record deleted
- `vaccination_recorded` - Vaccination recorded

### Financial Events
- `finance_account_created` - Account created
- `finance_account_updated` - Account updated
- `finance_account_deleted` - Account deleted
- `finance_transaction_created` - Transaction created
- `finance_transaction_status_updated` - Transaction status changed
- `finance_transaction_deleted` - Transaction deleted
- `finance_donations_reconciled` - Donations reconciled
- `finance_budget_created` - Budget created
- `finance_budget_item_added` - Budget item added
- `finance_recurring_created` - Recurring transaction created

### Donation Events
- `donation_received` - Donation received
- `donation_order_created` - Order created
- `donor_registered` - Donor registered
- `donation_refunded` - Donation refunded
- `donation_receipt_issued` - Receipt issued
- `donation_status_changed` - Status changed
- `donor_profile_updated` - Donor profile updated
- `donor_profile_deleted` - Donor profile deleted
- `sponsorship_created` - Sponsorship created
- `sponsorship_cancelled` - Sponsorship cancelled
- `sponsorship_paused` - Sponsorship paused
- `sponsorship_charged` - Sponsorship charged
- `donation_campaign_created` - Campaign created
- `donation_campaign_updated` - Campaign updated
- `donation_campaign_completed` - Campaign completed
- `donation_campaign_deleted` - Campaign deleted

### Other Module Events
- `shelter_created`, `shelter_updated`, `kennel_assigned`, `kennel_sanitation_updated`
- `transfer_requested`, `transfer_confirmed`, `care_log_submitted`
- `fleet_vehicle_created`, `fleet_vehicle_updated`, `fleet_vehicle_deleted`
- `fleet_equipment_checked_out`, `fleet_equipment_returned`
- `inventory_item_created`, `inventory_item_updated`, `inventory_item_deleted`, `inventory_stock_adjusted`
- `lost_found_reported`, `lost_found_updated`, `lost_found_resolved`, `lost_found_deleted`
- `lost_found_claim_submitted`, `lost_found_claim_reviewed`
- `volunteer_application_submitted`, `volunteer_application_updated`
- `volunteer_shift_created`, `volunteer_shift_updated`, `volunteer_deleted`
- `volunteer_certificate_issued`
- `notification_sent`, `portal_post_created`, `portal_post_updated`, `portal_post_deleted`
- `settings_updated`
- `grievance_updated`, `grievance_assigned`
- `companion_pet_created`, `companion_pet_updated`, `companion_pet_deleted`
- `companion_medical_record_created`, `companion_medical_record_updated`, `companion_medical_record_deleted`
- `safety_tag_provisioned`, `safety_tag_scanned`
- `vet_clinic_created`, `vet_clinic_updated`, `vet_clinic_deleted`
- `pet_appointment_created`, `pet_appointment_cancelled`, `pet_appointment_status_changed`
- `lost_found_broadcast_queued`
- `cms_page_draft_saved`, `cms_page_published`, `cms_page_draft_discarded`

## Audit Log Schema

```python
class AuthAuditLog:
    id: UUID                    # Primary key
    user_id: UUID | None        # Actor (nullable for anonymous actions)
    event_type: str             # Event type from AuthAuditEventType
    ip_address: str | None      # Client IP address
    user_agent: str | None      # Client user agent
    event_metadata: dict | None # Additional event-specific data
    before_state: dict | None   # State before change (for transitions)
    after_state: dict | None    # State after change (for transitions)
    created_at: datetime        # Event timestamp
```

## Usage Example

```python
await self._audit.record(
    event_type=AuthAuditEventType.RESCUE_STATUS_UPDATED,
    actor_id=agent_id,
    ip_address=ip_address,
    user_agent="",
    metadata={
        "rescue_id": str(request_id),
        "old_status": str(old_status),
        "new_status": str(request.status),
    },
    before_state={"status": str(old_status)},
    after_state={"status": str(request.status)},
)
```

## State Snapshot Pattern

For state-transition events (status changes, workflow transitions):
- `before_state`: Queryable state before the change
- `after_state`: Queryable state after the change
- Provides structured before/after picture without digging through free-form JSONB

## Anonymous Actions

Anonymous actions (e.g., public rescue reports) are audited with:
- `user_id=None`
- IP address recorded from request
- Metadata includes action-specific context

## Database Indexes

```sql
CREATE INDEX ix_auth_audit_logs_user_id_created_at ON auth_audit_logs (user_id, created_at);
CREATE INDEX ix_auth_audit_logs_event_type ON auth_audit_logs (event_type);
CREATE INDEX ix_auth_audit_logs_created_at ON auth_audit_logs (created_at);
```
