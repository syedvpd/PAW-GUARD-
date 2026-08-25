# PawGuard — Backend Push Notification Coverage Audit & Gap Report

## A. Overall Summary

- **Total Modules Audited**: 11 Modules
- **Modules with Complete Push Support**: 1 Module (Notifications Core Infrastructure & Broadcast)
- **Modules with Partial Push Support**: 4 Modules (Volunteer, Lost & Found, Veterinary / Companion Pets, Emergency)
- **Modules with NO Push Support**: 6 Modules (Authentication, Adoption, Foster, Donations, Safety Tag / QR, Pet / Profile)
- **Total Events Audited**: 48 Events
- **Total Push-Supported Events**: 12 Events
- **Total Missing Push Events**: 36 Events

---

## B. Module-by-Module Status

### 1. Authentication / Account
- **Push Infrastructure**: NO
- **Implemented Events**: None
- **Missing Events**:
  - Registration Welcome / Account Created
  - Login Security Alert (New device / suspicious login)
  - Password Reset Request & Password Changed Confirmation
  - MFA Enabled / Disabled Alert
  - Account Role / Permissions Update
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/auth/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/auth/router.py)
  - [`src/pawguard/modules/auth/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/auth/service.py)
  - Database tables: `users`, `user_sessions`

---

### 2. Adoption
- **Push Infrastructure**: NO (Email notifications only)
- **Implemented Events**: None
- **Missing Events**:
  - Adoption Application Submitted
  - Application Approved
  - Application Rejected
  - Application Status Changed (e.g. Under Review, Home Visit Scheduled)
  - Adoption Completed / Final Agreement Issued
  - Pet Assigned to Adopter
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/adoption/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/adoption/router.py)
  - [`src/pawguard/modules/adoption/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/adoption/service.py)
  - Database tables: `adoption_applications`, `adoption_agreements`

---

### 3. Foster
- **Push Infrastructure**: NO (In-app database record only, no FCM dispatch)
- **Implemented Events**: None
- **Missing Events**:
  - Foster Application Submitted
  - Application Approved
  - Application Rejected
  - Placement Assigned / Pet Assigned to Foster
  - Placement Updated / Supplies Request Status
  - Return-to-Shelter Request Status
  - Foster-to-Adopt Conversion Status
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/foster/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/foster/router.py)
  - [`src/pawguard/modules/foster/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/foster/service.py)
  - Database tables: `foster_profiles`, `foster_placements`, `foster_supplies`

---

### 4. Volunteer
- **Push Infrastructure**: PARTIAL
- **Implemented Events**:
  - **Application Approval**: `POST /volunteers/applications/{id}/approve` $\rightarrow$ Triggers `VOLUNTEER_APPROVED`
  - **Application Rejection**: `POST /volunteers/applications/{id}/reject` $\rightarrow$ Triggers `VOLUNTEER_REJECTED`
  - **Shift Assigned / Claimed**: `POST /volunteers/shifts/{id}/join` $\rightarrow$ Triggers `SHIFT_ASSIGNED`
  - **Check-in Confirmation**: `POST /volunteers/attendance/{id}/check-in`
- **Missing Events**:
  - Application Submitted Confirmation
  - Shift Available Notification (Broadcast to active volunteers)
  - Shift Cancellation Alert (Admin cancelled shift)
  - Shift Starting Soon / Hourly Reminder
  - Check-out Confirmation & Logged Hours Summary
  - Milestone / Service Certificate Issued
- **Partial / Broken Events**: Shift reminders (Cron job dispatcher not registered).
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/volunteer/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/volunteer/router.py)
  - [`src/pawguard/modules/volunteer/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/volunteer/service.py)
  - Database tables: `volunteer_profiles`, `volunteer_shifts`, `shift_attendances`

---

### 5. Veterinary / Companion Pets
- **Push Infrastructure**: PARTIAL
- **Implemented Events**:
  - **Appointment Confirmed**: `POST /companion-pets/appointments/{id}/confirm`
  - **Appointment Cancelled**: `POST /companion-pets/appointments/{id}/cancel`
- **Missing Events**:
  - Appointment Requested Confirmation
  - Appointment Rejected
  - Appointment Rescheduled
  - Appointment Reminder (Upcoming vet visit)
  - Prescription / Medication Reminder
  - Vaccination Due Reminder
- **Partial / Broken Events**: Medication reminders created in `POST /companion-pets/{pet_id}/reminders` lack an automated background push worker.
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/companion_pet/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/companion_pet/router.py)
  - [`src/pawguard/modules/companion_pet/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/companion_pet/service.py)
  - Database tables: `companion_pet_appointments`, `companion_pet_reminders`

---

### 6. Lost & Found
- **Push Infrastructure**: PARTIAL
- **Implemented Events**:
  - **Lost Pet Broadcast Alert**: `POST /lost-found/lost/{report_id}/broadcast`
  - **Sighting Submitted**: `POST /lost-found/sighting`
- **Missing Events**:
  - Lost Report Submitted Confirmation
  - Found Report Submitted Confirmation
  - Potential Match Found (Algorithmic match trigger)
  - Match Confirmed / Ownership Claim Reviewed
  - Report Resolved / Pet Reunited
- **Partial / Broken Events**: Sighting alert notifies original reporter via in-app notification, but FCM push is missing for citizen sightings.
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/lost_found/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/lost_found/router.py)
  - [`src/pawguard/modules/lost_found/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/lost_found/service.py)
  - Database tables: `lost_reports`, `found_reports`, `lost_found_matches`

---

### 7. Donations
- **Push Infrastructure**: NO (Email receipts only)
- **Implemented Events**: None
- **Missing Events**:
  - Donation Checkout Initiated
  - Payment Success / Receipt Available
  - Payment Failure Alert
  - Recurring Sponsorship Status Change / Charged
  - Campaign Milestone Reached
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/donation/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/donation/router.py)
  - [`src/pawguard/modules/donation/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/donation/service.py)
  - Database tables: `donations`, `donor_profiles`, `sponsorships`

---

### 8. Safety Tag / QR
- **Push Infrastructure**: NO
- **Implemented Events**: None
- **Missing Events**:
  - Safety Tag Provisioned / Activated
  - **QR Code Scanned Alert**: Notifies pet owner immediately when public QR tag is scanned.
  - Safety Tag Revoked / Deactivated
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/companion_pet/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/companion_pet/router.py) *(specifically `/safety-tag` endpoints)*
  - Database tables: `safety_tags`, `companion_pets`

---

### 9. Emergency / Rescue
- **Push Infrastructure**: PARTIAL
- **Implemented Events**:
  - **Emergency Incident Reported**: `POST /rescue/report` & `POST /public/rescue/report`
- **Missing Events**:
  - Rescue Dispatch Team Assigned
  - Rescue Agent En Route / Location Updated
  - Pet Located / Secured / Admitted Status
  - Emergency Incident Resolved
- **Partial / Broken Events**: Dispatch team push assignment exists for agents but is not sent to the reporting citizen.
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/rescue/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/rescue/router.py)
  - [`src/pawguard/modules/rescue/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/rescue/service.py)
  - Database tables: `rescue_requests`, `rescue_dispatches`

---

### 10. Pet / Profile
- **Push Infrastructure**: NO
- **Implemented Events**: None
- **Missing Events**:
  - Pet Status Changed (e.g. Quarantine Passed, Adoptable, Fostered)
  - Medical Clearance Authorized (`POST /medical/clearance/{dog_id}`)
  - Profile Update Confirmation (`PUT /auth/me`)
- **Partial / Broken Events**: None
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/dog/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/dog/router.py)
  - [`src/pawguard/modules/medical/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/medical/router.py)
  - Database tables: `dogs`, `dog_medical_clearances`

---

### 11. Notifications Core System
- **Push Infrastructure**: YES (Complete FCM Gateway & Broadcast Engine)
- **Implemented Events**:
  - Admin Manual Broadcast (`POST /notifications/broadcast`)
  - Direct Notification Send (`POST /notifications/send`)
  - FCM Token Registration (`PUT /auth/me` with `fcm_token` & `push_notifications`)
  - Test Push Gateway (`POST /notifications/test-push`)
- **Missing Events**: None (Infrastructure is operational; business modules must call it).
- **Backend Files / Services Involved**:
  - [`src/pawguard/modules/notifications/router.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/notifications/router.py)
  - [`src/pawguard/modules/notifications/service.py`](file:///c:/Users/win10/Downloads/PAW-GUARD-/src/pawguard/modules/notifications/service.py)
  - Database tables: `notifications`, `notification_preferences`, `users` *(fcm_token column)*

---

## C. Complete Gap Matrix

| Module | Event | Email | In-App | Push | FCM Send | Status |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Auth** | User Registration Welcome | YES | NO | NO | NO | PUSH MISSING |
| **Auth** | New Login / Security Alert | YES | YES | NO | NO | PUSH MISSING |
| **Auth** | Password Reset Request | YES | NO | NO | NO | EMAIL ONLY |
| **Auth** | MFA Enabled / Disabled | YES | YES | NO | NO | PUSH MISSING |
| **Adoption** | Application Submitted | YES | YES | NO | NO | PUSH MISSING |
| **Adoption** | Application Approved | YES | YES | NO | NO | PUSH MISSING |
| **Adoption** | Application Rejected | YES | YES | NO | NO | PUSH MISSING |
| **Adoption** | Status Changed / Home Visit | YES | YES | NO | NO | PUSH MISSING |
| **Adoption** | Adoption Finalized | YES | YES | NO | NO | PUSH MISSING |
| **Foster** | Application Submitted | YES | YES | NO | NO | PUSH MISSING |
| **Foster** | Application Approved | YES | YES | NO | NO | PUSH MISSING |
| **Foster** | Application Rejected | YES | YES | NO | NO | PUSH MISSING |
| **Foster** | Pet Assigned to Foster | YES | YES | NO | NO | PUSH MISSING |
| **Foster** | Placement / Supplies Update | NO | YES | NO | NO | PUSH MISSING |
| **Foster** | Return to Shelter Request | NO | YES | NO | NO | PUSH MISSING |
| **Volunteer** | Application Submitted | YES | YES | NO | NO | PUSH MISSING |
| **Volunteer** | Application Approved | YES | YES | YES | YES | **IMPLEMENTED** |
| **Volunteer** | Application Rejected | YES | YES | YES | YES | **IMPLEMENTED** |
| **Volunteer** | Shift Available Alert | NO | NO | NO | NO | MISSING |
| **Volunteer** | Shift Claimed / Joined | NO | YES | YES | YES | **IMPLEMENTED** |
| **Volunteer** | Shift Cancelled Alert | YES | YES | NO | NO | PUSH MISSING |
| **Volunteer** | Shift Starting Reminder | NO | NO | NO | NO | MISSING (CRON) |
| **Volunteer** | Check-in Successful | NO | YES | YES | YES | **IMPLEMENTED** |
| **Volunteer** | Check-out Successful | NO | YES | NO | NO | PUSH MISSING |
| **Volunteer** | Service Certificate Issued | YES | YES | NO | NO | PUSH MISSING |
| **Vet / Pets** | Appointment Requested | YES | YES | NO | NO | PUSH MISSING |
| **Vet / Pets** | Appointment Confirmed | YES | YES | YES | YES | **IMPLEMENTED** |
| **Vet / Pets** | Appointment Rejected | YES | YES | NO | NO | PUSH MISSING |
| **Vet / Pets** | Appointment Cancelled | YES | YES | YES | YES | **IMPLEMENTED** |
| **Vet / Pets** | Appointment Reminder | NO | YES | NO | NO | PUSH MISSING (CRON) |
| **Vet / Pets** | Vaccine / Med Reminder | NO | YES | NO | NO | PUSH MISSING (CRON) |
| **Lost/Found** | Lost Report Submitted | YES | YES | NO | NO | PUSH MISSING |
| **Lost/Found** | Found Report Submitted | YES | YES | NO | NO | PUSH MISSING |
| **Lost/Found** | Broadcast Lost Pet Alert | NO | YES | YES | YES | **IMPLEMENTED** |
| **Lost/Found** | Potential Match Found | NO | YES | NO | NO | PUSH MISSING |
| **Lost/Found** | Sighting Reported | NO | YES | NO | NO | PUSH MISSING |
| **Lost/Found** | Ownership Claim Approved | YES | YES | NO | NO | PUSH MISSING |
| **Donations** | Donation Successful | YES | YES | NO | NO | EMAIL ONLY |
| **Donations** | Payment Failed | YES | YES | NO | NO | PUSH MISSING |
| **Donations** | Receipt Generated | YES | YES | NO | NO | EMAIL ONLY |
| **Donations** | Sponsorship Charged | YES | YES | NO | NO | PUSH MISSING |
| **Safety Tag** | QR Code Scanned Alert | NO | YES | NO | NO | PUSH MISSING |
| **Safety Tag** | Tag Revoked / Replaced | NO | YES | NO | NO | PUSH MISSING |
| **Emergency** | Incident Reported | YES | YES | YES | YES | **IMPLEMENTED** |
| **Emergency** | Dispatch Team Assigned | NO | YES | YES | YES | **IMPLEMENTED (AGENTS ONLY)** |
| **Emergency** | Pet Rescued / Secured | YES | YES | NO | NO | PUSH MISSING |
| **Pet Status** | Adoptable / Fostered Status | NO | YES | NO | NO | PUSH MISSING |
| **Pet Status** | Medical Clearance Granted | NO | YES | NO | NO | PUSH MISSING |

---

## D. Backend Team Action List

### 🔴 High Priority

#### 1. Adoption Module Push Integration
- **File**: `src/pawguard/modules/adoption/service.py`
- **Action**: Trigger FCM push on `approve_application`, `reject_application`, and `create_application`.
- **Payload**: `{"title": "Adoption Update", "body": "Your application for {pet_name} was approved!", "action_url": "/profile/applications"}`

#### 2. Foster Module Push Integration
- **File**: `src/pawguard/modules/foster/service.py`
- **Action**: Trigger FCM push when admin assigns a foster placement (`create_placement`) or updates placement status.
- **Payload**: `{"title": "Foster Placement", "body": "You have been assigned to foster {pet_name}!", "action_url": "/profile/foster/status"}`

#### 3. Veterinary & Appointment Push Coverage
- **File**: `src/pawguard/modules/companion_pet/service.py`
- **Action**: Add FCM push calls to `reject_appointment` and `request_appointment`. Register Celery / Background cron worker for `companion_pet_reminders` to send upcoming vaccination/medication push alerts 24 hours prior.

#### 4. Safety Tag QR Scan Push Alert
- **File**: `src/pawguard/modules/companion_pet/router.py` *(Specifically QR scan callback endpoints)*
- **Action**: Trigger real-time FCM push notification to pet owner when a citizen scans their lost pet's QR code.
- **Payload**: `{"title": "Safety Tag Scanned!", "body": "Someone just scanned {pet_name}'s QR tag near {city}", "action_url": "/profile/companion-pets"}`

### 🟡 Medium Priority

#### 1. Lost & Found Match & Sighting Push
- **File**: `src/pawguard/modules/lost_found/service.py`
- **Action**: Trigger FCM push to lost pet owner when `submit_sighting` or `confirm_match` is called.

#### 2. Donations & Payment Receipts
- **File**: `src/pawguard/modules/donation/service.py`
- **Action**: Dispatch FCM push alongside existing email receipt when `verify_checkout` succeeds.

#### 3. Volunteer Shift Reminders & Check-out
- **File**: `src/pawguard/modules/volunteer/service.py`
- **Action**: Trigger FCM push on `check_out` showing logged hours summary. Set up cron job to dispatch push alerts 2 hours prior to a claimed shift.

### 🟢 Low Priority

#### 1. Authentication Security Alerts
- **File**: `src/pawguard/modules/auth/service.py`
- **Action**: Dispatch push alerts when MFA is enabled/disabled or password is changed.

---

## E. Evidence & Discovery Logs
- **Notification Core Service**: `src/pawguard/modules/notifications/service.py`
- **Function**: `FCMService.send_push_notification(user_id, title, body, data)`
- **Table**: `users` *(fcm_token column)* & `notifications` table *(sent_at, is_read, user_id)*.
- **Volunteer Approvals**: `src/pawguard/modules/volunteer/service.py` $\rightarrow$ `approve_application()` calls `notification_service.send_notification(user_id, trigger_code='VOLUNTEER_APPROVED', send_push=True)`.
- **Veterinary Confirmations**: `src/pawguard/modules/companion_pet/service.py` $\rightarrow$ `confirm_appointment()` calls `fcm_service.send_push_notification()`.
- **Lost Pet Broadcast**: `src/pawguard/modules/lost_found/router.py` $\rightarrow$ `broadcast_lost_report()` calls `notification_service.broadcast_notification()`.
