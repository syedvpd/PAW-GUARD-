# PawGuard — Complete API Specification
**REST API Reference for the Entire Backend — All Modules, All Endpoints**  
*PawGuard Rescue & Adoption Operations* | *PAWGUARD-APISPEC-01* | *August 2026*

---

## 1. Overview
This document catalogs every REST API endpoint exposed by the PawGuard backend: 23 modules, 448 endpoints in total. It is generated directly from the production source code, so it reflects exactly what is deployed — not a design intention that may have drifted from the build.

---

## 2. Base URL & Versioning

| Environment | Base URL |
| :--- | :--- |
| **Production (live)** | `https://pawguard-backend-mqri.onrender.com/api/v1` |
| **Interactive docs (Swagger UI)** | `https://pawguard-backend-mqri.onrender.com/docs` |
| **OpenAPI schema (machine-readable)** | `https://pawguard-backend-mqri.onrender.com/openapi.json` |

*Every endpoint in this document is relative to the `/api/v1` base — for example, the Auth module's `/auth/login` is reachable at `https://pawguard-backend-mqri.onrender.com/api/v1/auth/login`.*

---

## 3. Authentication
- **Bearer-token authentication**: `Authorization: Bearer <access_token>` on every protected request.
- **Access tokens** are short-lived JWTs (RS256, 15 minutes); obtained via `POST /auth/login` and renewed via `POST /auth/refresh`.
- Endpoints marked **"Public"** in this document require no token (e.g. browsing the adoption directory, submitting a public rescue report).
- All other endpoints require both a valid token and the specific permission code shown in the "Permission" column — a valid login alone is not enough if the account's role lacks that permission.

---

## 4. Standard Response Envelope
Every endpoint returns one of two consistent JSON shapes, so client apps can parse responses uniformly:

- **Single-item response**:
  ```json
  { "success": true, "data": { ... }, "message": "..." }
  ```
- **List / paginated response**:
  ```json
  { "success": true, "data": [ ... ], "meta": { "total": 0, "page": 1, "page_size": 20, "total_pages": 1 } }
  ```
- **Error response**:
  ```json
  { "success": false, "error": { "code": "VALIDATION_FAILED", "message": "...", "details": {} } }
  ```

---

## 5. Rate Limiting
Sensitive endpoints (login, QR-tag scanning, lost-pet broadcast, public submissions) are rate-limited per user/IP via Redis. Where a limit applies, it is shown in the "Rate Limit" column of that endpoint's table.

---

## 6. Module Index

| Module | Base Path | Endpoints | Purpose |
| :--- | :--- | :--- | :--- |
| **Auth** | `/admin`, `/auth` | 34 | Identity: registration, login, sessions, RBAC/PBAC, MFA, OAuth, audit trail. |
| **Admin** | `/admin/audit-logs`, `/admin/dashboard` | 19 | Cross-module administration: audit-log viewing and admin analytics dashboard. |
| **Dashboards** | `/dashboards` | 14 | Aggregated, role-specific operational dashboards. |
| **Rescue** | `/rescue`, `/public/rescue` | 24 | Rescue intake, field triage, dispatch tracking (includes a public reporting endpoint). |
| **Rescue Centre** | `/rescue-centres` | 8 | Rescue-centre / shelter facility directory and capacity management. |
| **Dog** | `/dogs` | 16 | Shelter-admitted dog master profiles, medical/behavior history, media. |
| **Companion Pet** | `/companion-pets` | 36 | Owner-managed pets, vet clinics, appointments, QR safety tags, medical uploads, reminders. |
| **Adoption** | `/adoptions` | 17 | Adoption applications, six-phase vetting pipeline, approvals, and post-adoption follow-ups. |
| **Volunteer** | `/volunteers` | 15 | Volunteer registration, shift scheduling, hours, training records. |
| **Foster** | `/fosters` | 12 | Foster applications, active placements, returns, foster-to-adopt. |
| **Donation** | `/donations` | 30 | Donor management, one-time/recurring donations, sponsorships, receipts. |
| **Lost Found** | `/lost-found` | 18 | Lost/found pet reporting, automated matching, broadcast alerts, ownership claims. |
| **Inventory** | `/inventory` | 11 | Stock levels, movement tracking, reorder triggers. |
| **Shelter** | `/shelter` | 23 | Facility capacity, room/kennel assignment, inter-facility transfers. |
| **Medical** | `/medical` | 21 | Shelter-side medical records: treatments, vaccinations, surgery, clearances. |
| **Portal** | `/portal` | 53 | Public website content and public submission endpoints (largest module). |
| **Fleet** | `/fleet` | 17 | Rescue-transport vehicles, maintenance, trips, fuel. |
| **Grievance** | `/grievance` | 16 | Complaint/grievance intake and resolution tracking. |
| **Notifications** | `/notifications` | 10 | Shared in-app/email/push delivery layer used by nearly every module. |
| **Settings** | `/settings` | 17 | Global settings and feature flags. |
| **Storage** | `/storage` | 8 | Presigned S3 upload issuance and confirmation for every module that accepts files. |
| **Finance** | `/finance` | 25 | Financial ledger reconciling donations and expenses. |
| **Reports** | `/reports` | 4 | On-demand CSV/XLSX/PDF report generation. |

---

## 7. Module Details & Endpoints

### 7.1 Module: Auth (34 endpoints)
Identity: registration, login, sessions, RBAC/PBAC, MFA, OAuth, audit trail.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/admin/roles` | List Roles | `system:admin` | — |
| **POST** | `/admin/roles` | Create Role | `system:admin` | — |
| **GET** | `/admin/roles/{role_id}` | Get Role | `system:admin` | — |
| **PUT** | `/admin/roles/{role_id}` | Update Role | `system:admin` | — |
| **DELETE** | `/admin/roles/{role_id}` | Delete Role | `system:admin` | — |
| **GET** | `/admin/permissions` | List Permissions | `system:admin` | — |
| **GET** | `/admin/users` | List Users | `system:admin` | — |
| **POST** | `/admin/users` | Create User | `system:admin` | — |
| **GET** | `/admin/users/{user_id}` | Get User | `system:admin` | — |
| **PUT** | `/admin/users/{user_id}` | Update User | `system:admin` | — |
| **DELETE** | `/admin/users/{user_id}` | Delete User | `system:admin` | — |
| **POST** | `/admin/users/restore-and-reset` | Restore And Reset Password | `system:admin` | — |
| **POST** | `/auth/register` | Register | `Public` | — |
| **POST** | `/auth/login` | Login | `Public` | — |
| **POST** | `/auth/mfa/verify` | Verify Mfa Login | `Public` | — |
| **POST** | `/auth/refresh` | Refresh | `Public` | — |
| **POST** | `/auth/logout` | Logout | `Public` | — |
| **POST** | `/auth/logout-all` | Logout All | `Public` | — |
| **GET** | `/auth/me` | Get Me | `Public` | — |
| **PUT** | `/auth/me` | Update Profile | `Public` | — |
| **GET** | `/auth/sessions` | List Sessions | `Public` | — |
| **DELETE** | `/auth/sessions/{session_id}` | Revoke Session | `Public` | — |
| **POST** | `/auth/password/change` | Change Password | `Public` | — |
| **POST** | `/auth/password/reset/request` | Request Password Reset | `Public` | — |
| **POST** | `/auth/password/reset/confirm` | Confirm Password Reset | `Public` | — |
| **POST** | `/auth/email/verify/confirm` | Confirm Email Verification | `Public` | — |
| **POST** | `/auth/email/verify/request` | Request Email Verification | `Public` | — |
| **POST** | `/auth/mfa/enroll` | Enroll Mfa | `Public` | — |
| **POST** | `/auth/mfa/enroll/confirm` | Confirm Mfa Enrollment | `Public` | — |
| **POST** | `/auth/mfa/disable` | Disable Mfa | `Public` | — |
| **POST** | `/auth/oauth/login` | Oauth Login | `Public` | — |
| **GET** | `/auth/oauth/accounts` | List Oauth Accounts | `Public` | — |
| **POST** | `/auth/oauth/link` | Link Oauth Account | `Public` | — |
| **DELETE** | `/auth/oauth/accounts/{account_id}` | Unlink Oauth Account | `Public` | — |

---

### 7.2 Module: Admin (19 endpoints)
Cross-module administration: audit-log viewing and admin analytics dashboard.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/admin/audit-logs` | List Audit Logs | `system:admin` | — |
| **GET** | `/admin/audit-logs/export` | Export Audit Logs | `system:admin` | — |
| **GET** | `/admin/audit-logs/{entry_id}` | Get Audit Log | `system:admin` | — |
| **GET** | `/admin/dashboard/metrics` | Get System Metrics | `system:admin` | — |
| **GET** | `/admin/dashboard/summary` | Get Summary | `system:admin` | — |
| **GET** | `/admin/dashboard/kpis` | Get Kpis | `system:admin` | — |
| **GET** | `/admin/dashboard/charts` | Get Charts | `system:admin` | — |
| **GET** | `/admin/dashboard/recent-activity` | Get Recent Activity | `system:admin` | — |
| **GET** | `/admin/dashboard/inventory-alerts` | Get Inventory Alerts | `system:admin` | — |
| **GET** | `/admin/dashboard/donation-summary` | Get Donation Summary | `system:admin` | — |
| **GET** | `/admin/dashboard/rescue-stats` | Get Rescue Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/medical-stats` | Get Medical Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/adoption-stats` | Get Adoption Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/volunteer-stats` | Get Volunteer Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/notification-summary` | Get Notification Summary | `system:admin` | — |
| **GET** | `/admin/dashboard/shelter-stats` | Get Shelter Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/foster-stats` | Get Foster Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/lost-found-stats` | Get Lost Found Stats | `system:admin` | — |
| **GET** | `/admin/dashboard/grievance-stats` | Get Grievance Stats | `system:admin` | — |

---

### 7.3 Module: Dashboards (14 endpoints)
Aggregated, role-specific operational dashboards.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/dashboards/rescue` | Get Rescue Dashboard | `dashboard:rescue` | — |
| **GET** | `/dashboards/rescue/stream` | Stream Rescue Dashboard | `dashboard:rescue` | — |
| **GET** | `/dashboards/shelter` | Get Shelter Dashboard | `dashboard:shelter` | — |
| **GET** | `/dashboards/medical` | Get Medical Dashboard | `dashboard:medical` | — |
| **GET** | `/dashboards/adoption` | Get Adoption Dashboard | `dashboard:adoption` | — |
| **GET** | `/dashboards/foster` | Get Foster Dashboard | `dashboard:foster` | — |
| **GET** | `/dashboards/volunteer` | Get Volunteer Dashboard | `dashboard:volunteer` | — |
| **GET** | `/dashboards/inventory` | Get Inventory Dashboard | `dashboard:inventory` | — |
| **GET** | `/dashboards/finance` | Get Finance Dashboard | `dashboard:finance` | — |
| **GET** | `/dashboards/donor` | Get Donor Dashboard | `dashboard:donor` | — |
| **GET** | `/dashboards/staff` | Get Staff Dashboard | `system:admin` | — |
| **GET** | `/dashboards/executive` | Get Executive Dashboard | `system:admin` | — |
| **GET** | `/dashboards/public` | Get Public Dashboard | `Public` | — |
| **GET** | `/dashboards/operations` | Get Operations Dashboard | `system:admin` | — |

---

### 7.4 Module: Rescue (24 endpoints)
Rescue intake, field triage, dispatch tracking (includes a public reporting endpoint).

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/rescue/report` | Report Incident | `rescue:create` | 5/60s |
| **POST** | `/public/rescue/report` | Public Report Incident | `Public` | 5/60s |
| **POST** | `/rescue/media-upload-url` | Request Rescue Media Upload Url | `Public` | 10/60s |
| **POST** | `/rescue/{request_id}/verify` | Verify Request | `rescue:verify` | — |
| **POST** | `/rescue/{request_id}/assign-coordinator` | Assign Coordinator | `rescue:dispatch` | — |
| **POST** | `/rescue/{request_id}/dispatch` | Dispatch Team | `rescue:dispatch` | — |
| **PATCH** | `/rescue/dispatches/{dispatch_id}` | Update Dispatch | `rescue:dispatch` | — |
| **DELETE** | `/rescue/dispatches/{dispatch_id}` | Delete Dispatch | `rescue:delete` | — |
| **POST** | `/rescue/{request_id}/escalate` | Escalate Rescue | `rescue:update` | — |
| **POST** | `/rescue/{request_id}/located` | Mark Located | `rescue:execute` | — |
| **POST** | `/rescue/{request_id}/secured` | Mark Rescued | `rescue:execute` | — |
| **POST** | `/rescue/{request_id}/admitted` | Mark Admitted | `rescue:dispatch` | — |
| **POST** | `/rescue/{request_id}/fail` | Fail Rescue | `rescue:execute` | — |
| **POST** | `/rescue/{request_id}/accept` | Accept Dispatch | `rescue:execute` | — |
| **POST** | `/rescue/{request_id}/reports` | Add Observation Report | `rescue:execute` | — |
| **GET** | `/rescue/status` | Get Public Status | `Public` | 10/60s |
| **GET** | `/rescue/dispatches` | List Dispatches | `rescue:read` | — |
| **GET** | `/rescue/{request_id}` | Get Request | `Public` | — |
| **GET** | `/rescue` | List Requests | `Public` | — |
| **DELETE** | `/rescue/{request_id}` | Soft Delete Request | `rescue:execute` | — |
| **POST** | `/rescue/bulk/status-update` | Bulk Update Rescue Status | `rescue:execute` | — |
| **POST** | `/rescue/bulk/delete` | Bulk Delete Rescue Requests | `rescue:execute` | — |
| **POST** | `/rescue/agents/location` | Update Agent Location | `rescue:execute` | — |
| **GET** | `/rescue/{request_id}/suggest-agents` | Suggest Nearest Agents | `rescue:dispatch` | — |

---

### 7.5 Module: Rescue Centre (8 endpoints)
Rescue-centre / shelter facility directory and capacity management.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/rescue-centres` | List Rescue Centres | `Public` | — |
| **POST** | `/rescue-centres` | Create Rescue Centre | `shelter:update` | — |
| **GET** | `/rescue-centres/{facility_id}` | Get Rescue Centre | `Public` | — |
| **PUT** | `/rescue-centres/{facility_id}` | Update Rescue Centre | `shelter:update` | — |
| **DELETE** | `/rescue-centres/{facility_id}` | Delete Rescue Centre | `shelter:update` | — |
| **PUT** | `/rescue-centres/{facility_id}/status` | Update Rescue Centre Status | `shelter:update` | — |
| **POST** | `/rescue-centres/bulk/delete` | Bulk Delete Rescue Centres | `shelter:update` | — |
| **POST** | `/rescue-centres/bulk/status` | Bulk Update Rescue Centre Status | `shelter:update` | — |

---

### 7.6 Module: Dog (16 endpoints)
Shelter-admitted dog master profiles, medical/behavior history, media.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/dogs` | Register Dog | `shelter:update` | — |
| **GET** | `/dogs` | List Dogs | `Public` | — |
| **GET** | `/dogs/admin/dogs/{dog_id}` | Get Dog | `Public` | — |
| **GET** | `/dogs/{dog_id}/timeline` | Get Dog Timeline | `shelter:read` | — |
| **GET** | `/dogs/{dog_id}/public-scan` | Privacy-safe public dog QR scan | `Public` | — |
| **GET** | `/dogs/{dog_id}/qr-image` | Generate a staff-only dog profile QR image | `shelter:update` | — |
| **POST** | `/dogs/{dog_id}/weight` | Record Dog Weight | `shelter:update` | — |
| **GET** | `/dogs/{dog_id}/weights` | Get Dog Weight History | `shelter:read` | — |
| **PUT** | `/dogs/{dog_id}` | Update Dog | `shelter:update` | — |
| **PATCH** | `/dogs/{dog_id}/status` | Update Dog Status | `shelter:update` | — |
| **DELETE** | `/dogs/{dog_id}` | Soft Delete Dog | `shelter:update` | — |
| **POST** | `/dogs/bulk/status-update` | Bulk Update Dog Status | `shelter:update` | — |
| **POST** | `/dogs/bulk/delete` | Bulk Delete Dogs | `shelter:update` | — |
| **POST** | `/dogs/{dog_id}/safety-tag` | Provision a permanent Safety Tag for a Dog | `safety_tag:manage` | — |
| **GET** | `/dogs/{dog_id}/safety-tag` | Get active Safety Tag metadata for a Dog | `safety_tag:manage` | — |
| **DELETE** | `/dogs/{dog_id}/safety-tag` | Deactivate/revoke active Safety Tag for tag replacement | `safety_tag:manage` | — |

---

### 7.7 Module: Companion Pet (36 endpoints)
Owner-managed pets, vet clinics, appointments, QR safety tags, medical uploads, reminders.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/companion-pets` | Create an owner companion pet | `companion_pet:create` | — |
| **GET** | `/companion-pets` | List companion pets visible to the caller | `companion_pet:read` | — |
| **GET** | `/companion-pets/clinics` | List active veterinary clinics | `Public` | — |
| **GET** | `/companion-pets/clinics/{clinic_id}` | Get single veterinary clinic details | `Public` | — |
| **GET** | `/companion-pets/clinics/{clinic_id}/veterinarians` | List veterinarians available for booking | `Public` | — |
| **GET** | `/companion-pets/appointments` | List authorized veterinary appointments | `appointment:read` | — |
| **GET** | `/companion-pets/{pet_id}` | Get companion pet profile | `companion_pet:read` | — |
| **PATCH** | `/companion-pets/{pet_id}` | Update companion pet profile | `companion_pet:update` | — |
| **DELETE** | `/companion-pets/{pet_id}` | Soft-delete companion pet | `companion_pet:delete` | — |
| **POST** | `/companion-pets/{pet_id}/medical-files/upload-url` | Request presigned upload URL | `companion_pet:medical_upload` | — |
| **PUT** | `/companion-pets/{pet_id}/medical-files/{file_id}/confirm` | Confirm medical-history upload | `companion_pet:medical_upload` | — |
| **GET** | `/companion-pets/{pet_id}/medical-files` | List medical-history files | `companion_pet:read` | — |
| **GET** | `/companion-pets/medical-files/{file_id}/download-url` | Get download URL | `companion_pet:read` | — |
| **POST** | `/companion-pets/{pet_id}/medical-records` | Create medical-history record | `companion_pet:medical_upload` | — |
| **GET** | `/companion-pets/{pet_id}/medical-records` | List medical history | `companion_pet:read` | — |
| **GET** | `/companion-pets/medical-records/{record_id}` | Get medical-history record by ID | `companion_pet:read` | — |
| **PUT** | `/companion-pets/medical-records/{record_id}` | Update medical-history record | `companion_pet:medical_upload` | — |
| **DELETE** | `/companion-pets/medical-records/{record_id}` | Soft-delete medical-history record | `companion_pet:medical_upload` | — |
| **POST** | `/companion-pets/{pet_id}/safety-tag` | Provision or rotate a QR safety tag | `safety_tag:manage` | — |
| **GET** | `/companion-pets/{pet_id}/safety-tag` | Read safety-tag metadata | `companion_pet:read` | — |
| **DELETE** | `/companion-pets/{pet_id}/safety-tag` | Deactivate or revoke a QR safety tag | `safety_tag:manage` | — |
| **POST** | `/companion-pets/from-adoption/{application_id}` | Create companion pet from approved adoption | `companion_pet:create` | — |
| **POST** | `/companion-pets/safety-tag/scan` | Privacy-safe public QR safety-tag scan | `Public` | — |
| **POST** | `/companion-pets/clinics` | Create veterinary clinic directory entry | `vet_clinic:manage` | — |
| **PATCH** | `/companion-pets/clinics/{clinic_id}` | Update veterinary clinic | `vet_clinic:manage` | — |
| **DELETE** | `/companion-pets/clinics/{clinic_id}` | Soft-delete veterinary clinic | `vet_clinic:manage` | — |
| **POST** | `/companion-pets/clinics/{clinic_id}/memberships` | Authorize user for clinic | `vet_clinic:manage` | — |
| **POST** | `/companion-pets/appointments` | Book veterinary appointment | `appointment:create` | — |
| **GET** | `/companion-pets/appointments/{appointment_id}` | Get authorized appointment | `appointment:read` | — |
| **POST** | `/companion-pets/appointments/{appointment_id}/cancel` | Cancel appointment | `appointment:cancel` | — |
| **DELETE** | `/companion-pets/appointments/{appointment_id}` | Cancel appointment via DELETE | `appointment:cancel` | — |
| **POST** | `/companion-pets/appointments/{appointment_id}/confirm` | Confirm appointment as clinic staff | `appointment:manage` | — |
| **POST** | `/companion-pets/{pet_id}/reminders` | Create vaccination or medication reminder | `companion_pet:update` | — |
| **GET** | `/companion-pets/{pet_id}/reminders` | List vaccination and medication reminders | `companion_pet:read` | — |
| **DELETE** | `/companion-pets/{pet_id}/reminders/{reminder_id}` | Soft-delete reminder | `companion_pet:update` | — |

---

### 7.8 Module: Adoption (17 endpoints)
Adoption applications, six-phase vetting pipeline, approvals, and post-adoption follow-ups.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/adoptions/nearby-shelters` | Find Nearby Shelters | `Public` | — |
| **POST** | `/adoptions` | Apply For Adoption | `Public` | — |
| **GET** | `/adoptions/my` | List My Applications | `Public` | — |
| **GET** | `/adoptions` | List Applications | `Public` | — |
| **GET** | `/adoptions/{app_id}` | Get Application | `Public` | — |
| **GET** | `/adoptions/{app_id}/agreement` | Get Adoption Agreement | `Public` | — |
| **PUT** | `/adoptions/{app_id}` | Update Application | `adoption:process` | — |
| **PATCH** | `/adoptions/{app_id}/status` | Update Application Status | `adoption:process` | — |
| **POST** | `/adoptions/{app_id}/scores` | Add Score | `adoption:process` | — |
| **GET** | `/adoptions/{app_id}/scores` | Get Scores | `Public` | — |
| **DELETE** | `/adoptions/{app_id}` | Soft Delete Application | `adoption:process` | — |
| **POST** | `/adoptions/{app_id}/follow-ups` | Create Follow Up | `adoption:process` | — |
| **GET** | `/adoptions/{app_id}/follow-ups` | Get Follow Ups | `Public` | — |
| **POST** | `/adoptions/{app_id}/follow-ups/{follow_up_id}/proof` | Submit Follow Up Proof | `Public` | — |
| **PUT** | `/adoptions/{app_id}/fee` | Update Adoption Fee | `adoption:process` | — |
| **POST** | `/adoptions/bulk/status-update` | Bulk Update Application Status | `adoption:process` | — |
| **POST** | `/adoptions/bulk/delete` | Bulk Delete Applications | `adoption:process` | — |

---

### 7.9 Module: Volunteer (15 endpoints)
Volunteer registration, shift scheduling, hours, training records.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/volunteers/apply` | Apply to Volunteer | `Public` | — |
| **PUT** | `/volunteers/{profile_id}` | Update Profile | `volunteer:update` | — |
| **DELETE** | `/volunteers/{profile_id}` | Soft Delete Profile | `volunteer:update` | — |
| **GET** | `/volunteers/shifts` | List Shifts | `public:read` | — |
| **GET** | `/volunteers/{profile_id}` | Get Profile | `Public` | — |
| **POST** | `/volunteers/shifts` | Create Shift | `volunteer:schedule` | — |
| **POST** | `/volunteers/shifts/{shift_id}/join` | Join Shift | `Public` | — |
| **POST** | `/volunteers/attendance/{attendance_id}/check-in` | Check In | `Public` | — |
| **POST** | `/volunteers/attendance/{attendance_id}/check-out` | Check Out | `Public` | — |
| **GET** | `/volunteers/shifts/{shift_id}/attendance` | List Shift Attendance | `volunteer:read` | — |
| **GET** | `/volunteers` | List Profiles | `volunteer:update` | — |
| **POST** | `/volunteers/bulk/delete` | Bulk Delete Profiles | `volunteer:update` | — |
| **GET** | `/volunteers/{profile_id}/certificate` | Issue Service Certificate | `Public` | — |
| **GET** | `/volunteers/{profile_id}/service-summary` | Get Service Summary | `Public` | — |
| **POST** | `/volunteers/bulk/status` | Bulk Update Profile Status | `volunteer:update` | — |

---

### 7.10 Module: Foster (12 endpoints)
Foster applications, active placements, returns, foster-to-adopt.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/fosters/apply` | Apply to Foster | `Public` | — |
| **PUT** | `/fosters/{profile_id}` | Update Profile | `foster:update` | — |
| **DELETE** | `/fosters/{profile_id}` | Soft Delete Profile | `foster:update` | — |
| **POST** | `/fosters/{profile_id}/placements` | Place Dog | `foster:approve` | — |
| **POST** | `/fosters/placements/{placement_id}/return` | Return Dog | `foster:approve` | — |
| **GET** | `/fosters` | List Profiles | `foster:read` | — |
| **POST** | `/fosters/bulk/delete` | Bulk Delete Profiles | `foster:update` | — |
| **POST** | `/fosters/placements/{placement_id}/progress` | Log Progress | `Public` | — |
| **GET** | `/fosters/placements/{placement_id}/progress` | Get Progress Logs | `Public` | — |
| **POST** | `/fosters/placements/{placement_id}/supplies` | Log Supply Dispatch | `foster:approve` | — |
| **GET** | `/fosters/placements/{placement_id}/supplies` | List Supply Dispatches | `Public` | — |
| **POST** | `/fosters/placements/{placement_id}/convert-to-adopt` | Convert to Adopt | `foster:approve` | — |

---

### 7.11 Module: Donation (30 endpoints)
Donor management, one-time/recurring donations, sponsorships, receipts.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/donations/register` | Register Donor | `Public` | — |
| **PUT** | `/donations/donors/{donor_id}` | Update Donor | `donation:update` | — |
| **DELETE** | `/donations/donors/{donor_id}` | Soft Delete Donor | `donation:update` | — |
| **POST** | `/donations` | Record Manual Donation | `donation:manage` | — |
| **POST** | `/donations/checkout` | Initiate Donation Checkout | `Public` | — |
| **POST** | `/donations/verify` | Verify Donation Checkout | `Public` | — |
| **POST** | `/donations/webhook/razorpay` | Razorpay Webhook | `Public` | — |
| **GET** | `/donations/history` | Get Donation History | `Public` | — |
| **GET** | `/donations` | List All Donations | `donation:read` | — |
| **GET** | `/donations/donors` | List Donors | `donation:read` | — |
| **GET** | `/donations/{donation_id}/receipt` | Get Donation Receipt | `Public` | — |
| **PATCH** | `/donations/{donation_id}/status` | Update Donation Status | `donation:update` | — |
| **POST** | `/donations/{donation_id}/reconcile` | Reconcile Donation | `finance:create` | — |
| **POST** | `/donations/bulk/status-update` | Bulk Update Donation Status | `donation:update` | — |
| **POST** | `/donations/donors/bulk/delete` | Bulk Delete Donors | `donation:update` | — |
| **POST** | `/donations/sponsorships` | Create Sponsorship | `Public` | — |
| **PATCH** | `/donations/sponsorships/{sponsorship_id}/status` | Update Sponsorship Status | `Public` | — |
| **GET** | `/donations/sponsorships/my` | List My Sponsorships | `Public` | — |
| **GET** | `/donations/sponsorships` | List All Sponsorships | `donation:read` | — |
| **GET** | `/donations/sponsorships/{sponsorship_id}` | Get Sponsorship | `Public` | — |
| **GET** | `/donations/campaigns` | List Public Campaigns | `Public` | — |
| **GET** | `/donations/campaigns/manage` | List All Campaigns | `donation:read` | — |
| **POST** | `/donations/campaigns` | Create Campaign | `donation:manage` | — |
| **GET** | `/donations/campaigns/{campaign_id}` | Get Campaign | `Public` | — |
| **PATCH** | `/donations/campaigns/{campaign_id}` | Update Campaign | `donation:update` | — |
| **DELETE** | `/donations/campaigns/{campaign_id}` | Delete Campaign | `donation:update` | — |
| **GET** | `/donations/donors/me` | Get My Donor Profile | `Public` | — |
| **POST** | `/donations/recurring` | Create Recurring Subscription | `Public` | — |
| **GET** | `/donations/recurring` | List My Recurring Subscriptions | `Public` | — |
| **DELETE** | `/donations/recurring/{subscription_id}` | Cancel Recurring Subscription | `Public` | — |

---

### 7.12 Module: Lost Found (18 endpoints)
Lost/found pet reporting, automated matching, broadcast alerts, ownership claims.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/lost-found/sighting` | Sighting Submission | `Public` | — |
| **POST** | `/lost-found/lost` | Report Lost Pet | `Public` | — |
| **POST** | `/lost-found/lost/{report_id}/broadcast` | Broadcast Lost Pet Alert | `lost_found:broadcast` | 3/3600s |
| **POST** | `/lost-found/found` | Report Found Pet | `Public` | — |
| **GET** | `/lost-found/lost` | List Lost Reports | `Public` | — |
| **GET** | `/lost-found/found` | List Found Reports | `Public` | — |
| **GET** | `/lost-found/reunion-stories` | Get Reunion Stories | `Public` | — |
| **GET** | `/lost-found/lost/{report_id}` | Get Lost Report | `Public` | — |
| **GET** | `/lost-found/found/{report_id}` | Get Found Report | `Public` | — |
| **GET** | `/lost-found/lost/{report_id}/matches` | Get Matches For Lost | `Public` | — |
| **GET** | `/lost-found/found/{report_id}/matches` | Get Matches For Found | `Public` | — |
| **POST** | `/lost-found/matches/{match_id}/claim` | Submit Ownership Claim | `Public` | — |
| **POST** | `/lost-found/matches/{match_id}/claim/review` | Review Ownership Claim | `system:admin` | — |
| **POST** | `/lost-found/matches/{match_id}/resolve` | Resolve Match | `system:admin` | — |
| **DELETE** | `/lost-found/lost/{report_id}` | Delete Lost Report | `system:admin` | — |
| **DELETE** | `/lost-found/found/{report_id}` | Delete Found Report | `system:admin` | — |
| **POST** | `/lost-found/lost/bulk/delete` | Bulk Delete Lost Reports | `system:admin` | — |
| **POST** | `/lost-found/found/bulk/delete` | Bulk Delete Found Reports | `system:admin` | — |

---

### 7.13 Module: Inventory (11 endpoints)
Stock levels, movement tracking, reorder triggers.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/inventory/items` | Create Item | `inventory:create` | — |
| **GET** | `/inventory/items` | List Items | `inventory:read` | — |
| **GET** | `/inventory/items/{item_id}` | Get Item | `inventory:read` | — |
| **POST** | `/inventory/movements` | Record Movement | `inventory:update` | — |
| **GET** | `/inventory/items/{item_id}/movements` | List Movements | `inventory:read` | — |
| **POST** | `/inventory/requisitions` | Create Requisition | `inventory:create` | — |
| **GET** | `/inventory/requisitions` | List Requisitions | `inventory:read` | — |
| **PUT** | `/inventory/requisitions/{req_id}/status` | Update Requisition Status | `inventory:update` | — |
| **DELETE** | `/inventory/items/{item_id}` | Delete Item | `inventory:update` | — |
| **POST** | `/inventory/items/bulk/delete` | Bulk Delete Items | `inventory:update` | — |
| **POST** | `/inventory/requisitions/bulk/status` | Bulk Update Requisition Status | `inventory:update` | — |

---

### 7.14 Module: Shelter (23 endpoints)
Facility capacity, room/kennel assignment, inter-facility transfers.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/shelter/facilities` | Create Facility | `shelter:update` | — |
| **GET** | `/shelter/facilities` | List Facilities | `shelter:read` | — |
| **GET** | `/shelter/facilities/{facility_id}` | Get Facility | `shelter:read` | — |
| **PUT** | `/shelter/facilities/{facility_id}` | Update Facility | `shelter:update` | — |
| **POST** | `/shelter/facilities/{facility_id}/sections` | Create Section | `shelter:update` | — |
| **GET** | `/shelter/facilities/{facility_id}/sections` | List Sections | `shelter:read` | — |
| **POST** | `/shelter/sections/{section_id}/kennels` | Create Kennel | `shelter:update` | — |
| **GET** | `/shelter/sections/{section_id}/kennels` | List Kennels | `shelter:read` | — |
| **POST** | `/shelter/kennels/{kennel_id}/assign/{dog_id}` | Assign Dog to Kennel | `shelter:update` | — |
| **PUT** | `/shelter/kennels/{kennel_id}/sanitation` | Update Kennel Sanitation | `shelter:update` | — |
| **POST** | `/shelter/kennels/{kennel_id}/cleaning-logs` | Log Kennel Cleaning | `shelter:update` | — |
| **GET** | `/shelter/kennels/{kennel_id}/cleaning-logs` | List Kennel Cleaning Logs | `shelter:read` | — |
| **POST** | `/shelter/transfers` | Request Transfer | `shelter:update` | — |
| **GET** | `/shelter/transfers` | List Transfers | `shelter:read` | — |
| **GET** | `/shelter/transfers/{transfer_id}` | Get Transfer | `shelter:read` | — |
| **POST** | `/shelter/transfers/{transfer_id}/confirm-sender` | Confirm Transfer Sender | `shelter:update` | — |
| **POST** | `/shelter/transfers/{transfer_id}/confirm-receiver` | Confirm Transfer Receiver | `shelter:update` | — |
| **POST** | `/shelter/care-logs` | Submit Daily Care Log | `shelter:update` | — |
| **GET** | `/shelter/dogs/{dog_id}/care-logs` | List Care Logs | `shelter:read` | — |
| **DELETE** | `/shelter/facilities/{facility_id}` | Delete Facility | `shelter:update` | — |
| **PUT** | `/shelter/facilities/{facility_id}/status` | Update Facility Status | `shelter:update` | — |
| **POST** | `/shelter/facilities/bulk/delete` | Bulk Delete Facilities | `shelter:update` | — |
| **POST** | `/shelter/facilities/bulk/status` | Bulk Update Facility Status | `shelter:update` | — |

---

### 7.15 Module: Medical (21 endpoints)
Shelter-side medical records: treatments, vaccinations, surgery, clearances.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/medical/exams` | Perform Clinical Exam | `medical:create` | — |
| **POST** | `/medical/treatments` | Record Treatment | `medical:create` | — |
| **POST** | `/medical/vaccinations` | Administer Vaccine | `medical:create` | — |
| **POST** | `/medical/prescriptions` | Prescribe Medication | `medical:create` | — |
| **POST** | `/medical/clearance/{dog_id}` | Authorize Adoption Clearance | `medical:clearance` | — |
| **GET** | `/medical/clearances/dogs/{dog_id}` | Get Dog Clearances | `medical:read` | — |
| **POST** | `/medical/administrations` | Log Medication Administration | `medical:update` | — |
| **GET** | `/medical/prescriptions/{prescription_id}/administrations` | Get Prescription Administrations | `medical:read` | — |
| **GET** | `/medical/dogs/{dog_id}/administrations` | Get Dog Administrations | `medical:read` | — |
| **POST** | `/medical/vaccine-protocols` | Create Vaccine Protocol | `medical:update` | — |
| **GET** | `/medical/vaccine-protocols` | List Vaccine Protocols | `medical:read` | — |
| **GET** | `/medical/dogs/{dog_id}/history` | Get Medical History | `medical:read` | — |
| **GET** | `/medical/exams` | List Exams | `medical:read` | — |
| **GET** | `/medical/treatments` | List Treatments | `medical:read` | — |
| **GET** | `/medical/vaccinations` | List Vaccinations | `medical:read` | — |
| **GET** | `/medical/prescriptions` | List Prescriptions | `medical:read` | — |
| **PUT** | `/medical/prescriptions/{prescription_id}` | Update Prescription | `medical:update` | — |
| **PATCH** | `/medical/prescriptions/{prescription_id}/status` | Update Prescription Status | `medical:update` | — |
| **DELETE** | `/medical/{entity_type}/{entity_id}` | Soft Delete Entity | `medical:delete` | — |
| **POST** | `/medical/bulk/prescriptions/status` | Bulk Update Prescription Status | `medical:update` | — |
| **POST** | `/medical/bulk/delete` | Bulk Delete Entities | `medical:delete` | — |

---

### 7.16 Module: Portal (53 endpoints)
Public website content and public submission endpoints (largest module).

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/portal/stats` | Get Hero Stats | `Public` | — |
| **GET** | `/portal/success-stories` | List Published Stories | `Public` | — |
| **GET** | `/portal/success-stories/{story_id}` | Get Published Story | `Public` | — |
| **GET** | `/portal/blog` | List Published Blog | `Public` | — |
| **GET** | `/portal/blog/slug/{slug}` | Get Blog By Slug | `Public` | — |
| **GET** | `/portal/veterinary-network` | List Veterinary Partners | `Public` | — |
| **GET** | `/portal/contact` | List Contact Locations | `Public` | — |
| **POST** | `/portal/contact` | Submit Contact Message | `Public` | — |
| **POST** | `/portal/newsletter/subscribe` | Subscribe Newsletter | `Public` | — |
| **GET** | `/portal/faq` | List Faq | `Public` | — |
| **GET** | `/portal/legal` | List Published Legal Docs | `Public` | — |
| **GET** | `/portal/legal/{slug}` | Get Published Legal Doc | `Public` | — |
| **GET** | `/portal/urgent-alerts` | List Active Urgent Alerts | `Public` | — |
| **GET** | `/portal/transparency` | Get Transparency Stats | `Public` | — |
| **GET** | `/portal/me/dashboard` | Get User Dashboard | `Public` | — |
| **POST** | `/portal/admin/success-stories` | Create Story | `system:admin` | — |
| **PUT** | `/portal/admin/success-stories/{story_id}` | Update Story | `system:admin` | — |
| **POST** | `/portal/admin/blog` | Create Blog | `system:admin` | — |
| **PUT** | `/portal/admin/blog/{post_id}` | Update Blog | `system:admin` | — |
| **POST** | `/portal/admin/veterinary-network` | Create Vet | `system:admin` | — |
| **PUT** | `/portal/admin/veterinary-network/{partner_id}` | Update Vet | `system:admin` | — |
| **POST** | `/portal/admin/contact` | Create Contact | `system:admin` | — |
| **PUT** | `/portal/admin/contact/{location_id}` | Update Contact | `system:admin` | — |
| **POST** | `/portal/admin/faq` | Create Faq | `system:admin` | — |
| **PUT** | `/portal/admin/faq/{entry_id}` | Update Faq | `system:admin` | — |
| **GET** | `/portal/admin/success-stories` | Admin List Stories | `system:admin` | — |
| **GET** | `/portal/admin/blog` | Admin List Blogs | `system:admin` | — |
| **GET** | `/portal/admin/faq` | Admin List Faqs | `system:admin` | — |
| **PUT** | `/portal/admin/settings/{key}` | Upsert Setting | `system:admin` | — |
| **GET** | `/portal/admin/settings` | List Settings | `system:admin` | — |
| **DELETE** | `/portal/admin/success-stories/{story_id}` | Soft Delete Story | `system:admin` | — |
| **DELETE** | `/portal/admin/blog/{post_id}` | Soft Delete Blog | `system:admin` | — |
| **DELETE** | `/portal/admin/faq/{entry_id}` | Soft Delete Faq | `system:admin` | — |
| **POST** | `/portal/admin/success-stories/bulk/delete` | Bulk Delete Stories | `system:admin` | — |
| **POST** | `/portal/admin/success-stories/bulk/status` | Bulk Update Story Status | `system:admin` | — |
| **POST** | `/portal/admin/blog/bulk/delete` | Bulk Delete Blogs | `system:admin` | — |
| **POST** | `/portal/admin/blog/bulk/status` | Bulk Update Blog Status | `system:admin` | — |
| **POST** | `/portal/admin/faq/bulk/delete` | Bulk Delete Faqs | `system:admin` | — |
| **POST** | `/portal/admin/faq/bulk/status` | Bulk Update Faq Status | `system:admin` | — |
| **POST** | `/portal/admin/legal` | Create Legal Doc | `system:admin` | — |
| **PUT** | `/portal/admin/legal/{doc_id}` | Update Legal Doc | `system:admin` | — |
| **DELETE** | `/portal/admin/legal/{doc_id}` | Soft Delete Legal Doc | `system:admin` | — |
| **GET** | `/portal/admin/legal` | Admin List Legal Docs | `system:admin` | — |
| **POST** | `/portal/admin/urgent-alerts` | Create Urgent Alert | `system:admin` | — |
| **PUT** | `/portal/admin/urgent-alerts/{alert_id}` | Update Urgent Alert | `system:admin` | — |
| **DELETE** | `/portal/admin/urgent-alerts/{alert_id}` | Soft Delete Urgent Alert | `system:admin` | — |
| **GET** | `/portal/admin/urgent-alerts` | Admin List Urgent Alerts | `system:admin` | — |
| **GET** | `/portal/cms/pages/{slug}` | Get Public Cms Page | `Public` | — |
| **GET** | `/portal/admin/cms/pages` | List Admin Cms Pages | `system:admin` | — |
| **GET** | `/portal/admin/cms/pages/{slug}` | Get Admin Cms Page | `system:admin` | — |
| **PUT** | `/portal/admin/cms/pages/{slug}` | Update Admin Cms Page | `system:admin` | — |
| **POST** | `/portal/admin/cms/pages/{slug}/publish` | Publish Admin Cms Page | `system:admin` | — |
| **POST** | `/portal/admin/cms/pages/{slug}/discard` | Discard Admin Cms Page | `system:admin` | — |

---

### 7.17 Module: Fleet (17 endpoints)
Rescue-transport vehicles, maintenance, trips, fuel.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/fleet/vehicles` | Create Vehicle | `vehicle:update` | — |
| **GET** | `/fleet/vehicles` | List Vehicles | `vehicle:read` | — |
| **GET** | `/fleet/vehicles/{vehicle_id}` | Get Vehicle | `vehicle:read` | — |
| **PUT** | `/fleet/vehicles/{vehicle_id}` | Update Vehicle | `vehicle:update` | — |
| **PATCH** | `/fleet/vehicles/{vehicle_id}/status` | Update Vehicle Status | `vehicle:update` | — |
| **DELETE** | `/fleet/vehicles/{vehicle_id}` | Soft Delete Vehicle | `vehicle:update` | — |
| **POST** | `/fleet/maintenance` | Log Maintenance | `vehicle:update` | — |
| **GET** | `/fleet/vehicles/{vehicle_id}/maintenance` | List Maintenance | `vehicle:read` | — |
| **POST** | `/fleet/bulk/status-update` | Bulk Update Vehicle Status | `vehicle:update` | — |
| **POST** | `/fleet/bulk/delete` | Bulk Delete Vehicles | `vehicle:update` | — |
| **POST** | `/fleet/equipment` | Checkout Equipment | `vehicle:update` | — |
| **GET** | `/fleet/equipment` | List Equipment Checkouts | `vehicle:read` | — |
| **GET** | `/fleet/equipment/{checkout_id}` | Get Equipment Checkout | `vehicle:read` | — |
| **POST** | `/fleet/equipment/{checkout_id}/return` | Return Equipment | `vehicle:update` | — |
| **POST** | `/fleet/vehicles/{vehicle_id}/fuel` | Log Fuel | `vehicle:update` | — |
| **GET** | `/fleet/vehicles/{vehicle_id}/fuel` | List Fuel Logs | `vehicle:read` | — |
| **GET** | `/fleet/fuel/{log_id}` | Get Fuel Log | `vehicle:read` | — |

---

### 7.18 Module: Grievance (16 endpoints)
Complaint/grievance intake and resolution tracking.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/grievance` | Submit Complaint | `Public` | — |
| **GET** | `/grievance` | List Tickets | `grievance:read` | — |
| **GET** | `/grievance/feedback` | List Feedback | `grievance:read` | — |
| **GET** | `/grievance/{ticket_id}` | Get Ticket | `grievance:read` | — |
| **PUT** | `/grievance/{ticket_id}` | Update Ticket | `grievance:update` | — |
| **PATCH** | `/grievance/{ticket_id}/status` | Update Ticket Status | `grievance:update` | — |
| **POST** | `/grievance/{ticket_id}/assign` | Assign Ticket | `grievance:assign` | — |
| **POST** | `/grievance/{ticket_id}/escalate` | Escalate Ticket | `grievance:assign` | — |
| **POST** | `/grievance/{ticket_id}/comments` | Add Comment | `grievance:comment` | — |
| **GET** | `/grievance/{ticket_id}/comments` | List Comments | `grievance:read` | — |
| **POST** | `/grievance/feedback` | Submit Feedback | `Public` | — |
| **DELETE** | `/grievance/{ticket_id}` | Soft Delete Ticket | `grievance:update` | — |
| **DELETE** | `/grievance/feedback/{feedback_id}` | Soft Delete Feedback | `grievance:update` | — |
| **POST** | `/grievance/bulk/delete` | Bulk Delete Tickets | `grievance:update` | — |
| **POST** | `/grievance/bulk/status` | Bulk Update Ticket Status | `grievance:update` | — |
| **POST** | `/grievance/feedback/bulk/delete` | Bulk Delete Feedback | `grievance:update` | — |

---

### 7.19 Module: Notifications (10 endpoints)
Shared in-app/email/push delivery layer used by nearly every module.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/notifications` | List Notifications | `Public` | — |
| **GET** | `/notifications/unread-count` | Unread Count | `Public` | — |
| **PUT** | `/notifications/{notification_id}/read` | Mark Read | `Public` | — |
| **PUT** | `/notifications/read-all` | Mark All Read | `Public` | — |
| **DELETE** | `/notifications/{notification_id}` | Delete Notification | `Public` | — |
| **POST** | `/notifications/bulk/delete` | Bulk Delete Notifications | `notification:manage` | — |
| **POST** | `/notifications/send` | Send Notification | `notification:manage` | — |
| **GET** | `/notifications/preferences` | Get Preferences | `Public` | — |
| **PUT** | `/notifications/preferences` | Update Preferences | `Public` | — |
| **POST** | `/notifications/broadcast` | Broadcast Notification | `system:admin` | — |

---

### 7.20 Module: Settings (17 endpoints)
Global settings and feature flags.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/settings/general` | Get General Settings | `system:admin` | — |
| **GET** | `/settings/email` | Get Email Settings | `system:admin` | — |
| **GET** | `/settings/storage` | Get Storage Settings | `system:admin` | — |
| **GET** | `/settings/public-content` | Get Public Content | `public:read` | — |
| **PUT** | `/settings/public-content` | Update Public Content | `system:admin` | — |
| **GET** | `/settings/system` | List Settings | `system:admin` | — |
| **GET** | `/settings/system/{key}` | Get Setting | `system:admin` | — |
| **POST** | `/settings/system` | Create Setting | `system:admin` | — |
| **PUT** | `/settings/system/{key}` | Update Setting | `system:admin` | — |
| **DELETE** | `/settings/system/{setting_id}` | Delete Setting | `system:admin` | — |
| **GET** | `/settings/password-policy` | Get Password Policy | `system:admin` | — |
| **PUT** | `/settings/password-policy` | Update Password Policy | `system:admin` | — |
| **GET** | `/settings/business-rules` | List Business Rules | `system:admin` | — |
| **GET** | `/settings/business-rules/{rule_key}` | Get Business Rule | `system:admin` | — |
| **POST** | `/settings/business-rules` | Create Business Rule | `system:admin` | — |
| **PUT** | `/settings/business-rules/{rule_key}` | Update Business Rule | `system:admin` | — |
| **DELETE** | `/settings/business-rules/{rule_id}` | Delete Business Rule | `system:admin` | — |

---

### 7.21 Module: Storage (8 endpoints)
Presigned S3 upload issuance and confirmation for every module that accepts files.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/storage/upload-url` | Request Upload Url | `Public` | — |
| **PUT** | `/storage/{file_id}/confirm` | Confirm Upload | `Public` | — |
| **GET** | `/storage/{file_id}/download-url` | Get Download Url | `Public` | — |
| **GET** | `/storage/{file_id}` | Get File | `Public` | — |
| **GET** | `/storage` | List Files | `Public` | — |
| **DELETE** | `/storage/{file_id}` | Delete File | `Public` | — |
| **POST** | `/storage/bulk/delete` | Bulk Delete Files | `Public` | — |
| **GET** | `/storage/entity/{entity_type}/{entity_id}` | List Files By Entity | `Public` | — |

---

### 7.22 Module: Finance (25 endpoints)
Financial ledger reconciling donations and expenses.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/finance/accounts` | Create Account | `finance:create` | — |
| **GET** | `/finance/accounts` | List Accounts | `finance:read` | — |
| **GET** | `/finance/accounts/{account_id}` | Get Account | `finance:read` | — |
| **PUT** | `/finance/accounts/{account_id}` | Update Account | `finance:update` | — |
| **DELETE** | `/finance/accounts/{account_id}` | Delete Account | `finance:update` | — |
| **POST** | `/finance/transactions` | Create Transaction | `finance:create` | — |
| **GET** | `/finance/transactions` | List Transactions | `finance:read` | — |
| **GET** | `/finance/transactions/{tx_id}` | Get Transaction | `finance:read` | — |
| **PATCH** | `/finance/transactions/{tx_id}/status` | Update Transaction Status | `finance:update` | — |
| **DELETE** | `/finance/transactions/{tx_id}` | Delete Transaction | `finance:update` | — |
| **GET** | `/finance/summary` | Get Finance Summary | `finance:read` | — |
| **GET** | `/finance/pnl` | Get Pnl | `finance:read` | — |
| **GET** | `/finance/account-balances` | Get Account Balances | `finance:read` | — |
| **POST** | `/finance/reconcile/donations` | Reconcile Donations | `finance:create` | — |
| **GET** | `/finance/reconcile/summary` | Get Reconciliation Summary | `finance:read` | — |
| **POST** | `/finance/budgets` | Create Budget | `finance:create` | — |
| **GET** | `/finance/budgets` | List Budgets | `finance:read` | — |
| **GET** | `/finance/budgets/{budget_id}` | Get Budget | `finance:read` | — |
| **POST** | `/finance/budgets/{budget_id}/items` | Add Budget Item | `finance:update` | — |
| **DELETE** | `/finance/budgets/{budget_id}` | Delete Budget | `finance:update` | — |
| **POST** | `/finance/recurring` | Create Recurring | `finance:create` | — |
| **GET** | `/finance/recurring` | List Recurring | `finance:read` | — |
| **DELETE** | `/finance/recurring/{rtx_id}` | Delete Recurring | `finance:update` | — |
| **POST** | `/finance/accounts/bulk/delete` | Bulk Delete Accounts | `finance:update` | — |
| **POST** | `/finance/transactions/bulk/delete` | Bulk Delete Transactions | `finance:update` | — |

---

### 7.23 Module: Reports (4 endpoints)
On-demand CSV/XLSX/PDF report generation.

| Method | Endpoint | Description | Permission | Rate Limit |
| :--- | :--- | :--- | :--- | :--- |
| **POST** | `/reports/generate` | Generate Report | `reports:create` | — |
| **GET** | `/reports/types` | List Report Types | `reports:read` | — |
| **GET** | `/reports/formats` | List Report Formats | `reports:read` | — |
| **GET** | `/reports/download/{filename}` | Download Report | `reports:read` | — |

---
*End of API specification. Generated from pawguard-backend source.*
