# PawGuard Backend API Surface & Performance Inventory

## 1. Executive Summary

This inventory maps out the complete API surface of the PawGuard backend system across all 27 domain modules and 15 role-based dashboards. It acts as the structural foundation for performance benchmarking, query-count auditing, payload size profiling, and concurrency analysis.

---

## 2. Dashboard Endpoints Inventory (15 Role-Based Dashboards)

| Endpoint | Method | Path | Required Permission / Auth | Service Method | Cache TTL | Query Complexity / Sub-queries | Bottleneck Potential |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- | :--- |
| **Rescue Dashboard** | `GET` | `/dashboards/rescue` | `dashboard:rescue` | `dasvc.rescue_dashboard` | 300s | 2 queries: aggregate counts + top 10 recent calls | Low |
| **Rescue Operations Dashboard** | `GET` | `/dashboards/rescue/operations` | `dashboard:rescue` | `dasvc.rescue_operations_dashboard` | 300s | 6 sequential count/group queries (status, severity, active dispatches, busy agents, total agents, total vehicles) | Medium (Sequential DB queries) |
| **Rescue Real-Time SSE Feed** | `GET` | `/dashboards/rescue/stream` | `dashboard:rescue` | `stream_rescue_dashboard` | Streaming | Redis Pub/Sub `dispatch:events` + fallback snapshot polling | Medium (Connection pool & long-polling) |
| **Shelter Capacity Dashboard** | `GET` | `/dashboards/shelter` | `dashboard:shelter` | `dasvc.shelter_dashboard` | 10s | 2 complex SQL CTE/aggregation queries (capacity breakdown, kennels, isolation, quarantine) | Medium |
| **Shelter Real-Time SSE Feed** | `GET` | `/dashboards/shelter/stream` | `dashboard:shelter` | `stream_shelter_dashboard` | Streaming | Redis Pub/Sub `shelter:events` + fallback snapshot polling | Medium (Connection pool) |
| **Medical Dashboard** | `GET` | `/dashboards/medical` | `dashboard:medical` | `dasvc.medical_dashboard` | 30s | 3 count queries (exams_last_30d, treatments_last_30d, pending_vaccinations) | Low |
| **Adoption Dashboard** | `GET` | `/dashboards/adoption` | `dashboard:adoption` | `dasvc.adoption_dashboard` | 300s | 1 consolidated SQL query aggregating 12 status sub-selects | Low |
| **Foster Dashboard** | `GET` | `/dashboards/foster` | `dashboard:foster` | `dasvc.foster_dashboard` | 300s | 1 consolidated SQL query aggregating 12 status sub-selects | Low |
| **Volunteer Dashboard** | `GET` | `/dashboards/volunteer` | `dashboard:volunteer` | `dasvc.volunteer_dashboard` | 300s | 1 SQL query with 2 sub-counts | Low |
| **Inventory Dashboard** | `GET` | `/dashboards/inventory` | `dashboard:inventory` | `dasvc.inventory_dashboard` | 300s | 2 queries (category aggregation + low stock query) | Low |
| **Finance Dashboard** | `GET` | `/dashboards/finance` | `dashboard:finance` | `dasvc.finance_dashboard` | 300s | 2 queries (income/expense aggregation + unreconciled donations count) | Low |
| **Donor Dashboard** | `GET` | `/dashboards/donor` | `dashboard:donor` | `dasvc.donor_dashboard` | 300s | 2 queries (total donations count/sum + top 10 recent donations) | Low |
| **Staff Dashboard** | `GET` | `/dashboards/staff` | `system:admin` | `dasvc.staff_dashboard` | 300s | 1 SQL query with 2 sub-counts | Low |
| **Executive Dashboard** | `GET` | `/dashboards/executive` | `system:admin` | `dasvc.executive_dashboard` | 300s | Multi-dashboard composition: calls `rescue_dashboard`, `finance_dashboard`, `adoption_dashboard` | Medium (Cascade aggregation) |
| **Public Dashboard** | `GET` | `/dashboards/public` | Unauthenticated | `dasvc.public_dashboard` | 300s | 1 SQL query with 2 sub-counts | Low |
| **Operations Dashboard** | `GET` | `/dashboards/operations` | `system:admin` | `dasvc.operations_dashboard` | 60s | Multi-dashboard composition: calls `rescue_dashboard`, `shelter_dashboard`, `inventory_dashboard` | Medium (Cascade aggregation) |

---

## 3. Domain API Routers & Major Endpoints

### 3.1 Dog Management (`/dogs`)
- **Prefix**: `/dogs`
- **Endpoints**:
  - `POST /dogs/` (`dog:create`)
  - `GET /dogs/` (`dog:read`) — **List Endpoint**: Supports pagination (`skip`, `limit`), filtering by status, gender, shelter_facility_id, breed.
  - `GET /dogs/search` (`dog:read`) — **Search Endpoint**: Name & microchip query.
  - `GET /dogs/summary` (`dog:read`) — Aggregate status counters.
  - `GET /dogs/{dog_id}` (`dog:read`) — Single dog detail.
  - `PUT /dogs/{dog_id}` (`dog:update`) — Update profile.
  - `DELETE /dogs/{dog_id}` (`dog:delete`) — Soft delete.
  - `POST /dogs/{dog_id}/quarantine-pass` (`dog:quarantine:override`)
  - `POST /dogs/{dog_id}/sanitation-log` (`shelter:update`)

### 3.2 Adoption Module (`/adoptions`, `/adoption-applications`)
- **Prefix**: `/adoptions`
- **Endpoints**:
  - `POST /adoptions/applications` (`adoption:create`) — Submit application.
  - `GET /adoptions/applications` (`adoption:read`) — List applications with filtering and pagination.
  - `GET /adoptions/applications/{id}` (`adoption:read`) — Single application view.
  - `PATCH /adoptions/applications/{id}/status` (`adoption:update`) — State transition.
  - `POST /adoptions/applications/{id}/home-inspection` (`adoption:update`)
  - `GET /adoptions/follow-ups` (`adoption:read`) — List follow-ups.

### 3.3 Medical Module (`/medical`)
- **Prefix**: `/medical`
- **Endpoints**:
  - `POST /medical/exams` (`medical:create`)
  - `GET /medical/exams` (`medical:read`) — List exams.
  - `POST /medical/treatments` (`medical:create`)
  - `GET /medical/treatments` (`medical:read`) — List treatments.
  - `POST /medical/vaccinations` (`medical:create`)
  - `GET /medical/vaccinations` (`medical:read`) — List vaccination records.
  - `POST /medical/prescriptions` (`medical:create`)
  - `GET /medical/prescriptions` (`medical:read`) — List prescriptions.
  - `POST /medical/prescriptions/bulk-status` (`medical:update`) — Bulk status update.
  - `GET /medical/clearances/{id}` (`medical:read`)
  - `PATCH /medical/clearances/{id}/status` (`medical:update`)

### 3.4 Rescue Operations (`/rescue`, `/public/rescue`)
- **Prefix**: `/rescue`, `/public/rescue`
- **Endpoints**:
  - `POST /public/rescue/requests` (Unauthenticated) — Emergency incident reporting.
  - `GET /public/rescue/requests/{ticket}/tracking` (Unauthenticated) — Dynamic tracking & ETA calculation.
  - `GET /rescue/requests` (`rescue:read`) — List rescue tickets.
  - `PATCH /rescue/requests/{id}/dispatch` (`rescue:dispatch`) — Assign team & vehicle.
  - `PATCH /rescue/requests/{id}/status` (`rescue:update`) — Lifecycle state update.
  - `POST /rescue/dispatches/bulk-status` (`rescue:update`) — Bulk dispatch state transition.

### 3.5 Shelter & Kennels (`/shelter`)
- **Prefix**: `/shelter`
- **Endpoints**:
  - `POST /shelter/facilities` (`shelter:create`)
  - `GET /shelter/facilities` (`shelter:read`)
  - `POST /shelter/sections` (`shelter:create`)
  - `POST /shelter/kennels` (`shelter:create`)
  - `POST /shelter/kennels/{id}/assign` (`shelter:update`)
  - `POST /shelter/transfers/request` (`shelter:update`)
  - `POST /shelter/transfers/{id}/confirm` (`shelter:update`)
  - `POST /shelter/care-logs` (`shelter:create`)
  - `POST /shelter/cleaning-logs` (`shelter:create`)
  - `POST /shelter/vet-requests` (`shelter:create`)

### 3.6 Storage & Media (`/storage`)
- **Prefix**: `/storage`
- **Endpoints**:
  - `POST /storage/upload-url` (Authenticated) — Presigned S3 upload URL.
  - `POST /storage/upload-direct` (Authenticated) — Direct file upload.
  - `GET /storage/download-url` (Authenticated) — Single presigned S3 download URL.
  - `POST /storage/bulk-download-urls` (Authenticated) — Batch presigned S3 download URLs.
  - `DELETE /storage/file` (Authenticated) — Storage file deletion.

### 3.7 Reports & Exports (`/reports`)
- **Prefix**: `/reports`
- **Endpoints**:
  - `POST /reports/export` (`reports:create`) — Trigger background ARQ/BackgroundTask report generation.
  - `GET /reports/history` (`reports:read`) — List user generated reports.
  - `GET /reports/{id}/download` (`reports:read`) — Presigned report file download.

---

## 4. Key Performance Risk Matrix

1. **N+1 Relationship Queries**:
   - `GET /dogs/`: Fetching associated shelter section/facility details without eager loading.
   - `GET /rescue/requests`: Fetching dispatches, assigned agents, and evidence media per ticket in a loop.
   - `GET /adoptions/applications`: Fetching applicant user, dog profile, and reviewer details per item.

2. **Loop-based Presigned S3 URL Generation**:
   - `GET /rescue/requests` or `GET /reports/history`: Generating presigned S3 URLs during list model serialization inside Python loops.

3. **Unbounded Pagination Limits**:
   - `GET /inventory/items`, `GET /volunteers/shifts`, `GET /donations/`: Query parameters missing hard max ceiling (e.g., `limit > 1000`).

4. **Multi-Dashboard Cascade Overhead**:
   - `GET /dashboards/operations` and `GET /dashboards/executive`: Calling sibling dashboard handlers that each execute multiple database statements.
