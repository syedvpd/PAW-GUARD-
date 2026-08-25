# PawGuard — Volunteer Dashboard Attendance & Certification API Contract

This document outlines the complete API contract for the volunteer dashboard attendance, hours logging, and service certificate workflows.

---

## 🗺️ 1. API Route Registry

### 🚫 Non-Existent Routes (To Be Implemented)
- **`GET /api/v1/volunteers/me/attendance`** (Does not exist)
  - *Purpose*: Retrieve active shift registrations for the logged-in volunteer.
- **`GET /api/v1/volunteers/me/hours`** (Does not exist)
  - *Alternative*: Use `GET /api/v1/volunteers/{profile_id}/service-summary`
- **`GET /api/v1/volunteers/me/certificates`** (Does not exist)
  - *Alternative*: Use `GET /api/v1/volunteers/{profile_id}/certificate`

### 🟢 Existing Routes

#### 1. Join Shift
- **Endpoint**: `POST /api/v1/volunteers/shifts/{shift_id}/join`
- **Path Params**: `shift_id: UUID`
- **Response**: `ApiResponse[ShiftAttendanceResponse]`
  - *Note*: Returns the newly created `attendance_id` in the `id` field of the response body.

#### 2. TAP IN / Check-In
- **Endpoint**: `POST /api/v1/volunteers/attendance/{attendance_id}/check-in`
- **Path Params**: `attendance_id: UUID`
- **Response**: `ApiResponse[ShiftAttendanceResponse]`

#### 3. TAP OUT / Check-Out
- **Endpoint**: `POST /api/v1/volunteers/attendance/{attendance_id}/check-out`
- **Path Params**: `attendance_id: UUID`
- **Response**: `ApiResponse[ShiftAttendanceResponse]`

#### 4. Service Summary (Hours)
- **Endpoint**: `GET /api/v1/volunteers/{profile_id}/service-summary`
- **Path Params**: `profile_id: UUID`
- **Response**: `ApiResponse[VolunteerServiceSummary]`

#### 5. Generate / Issue Service Certificate
- **Endpoint**: `GET /api/v1/volunteers/{profile_id}/certificate`
- **Path Params**: `profile_id: UUID`
- **Response**: `ApiResponse[DownloadUrlResponse]`

---

## 📄 2. Schema Details

### ShiftAttendanceResponse
```json
{
  "id": "UUID (attendance_id)",
  "shift_id": "UUID",
  "volunteer_id": "UUID",
  "check_in_at": "datetime or null",
  "check_out_at": "datetime or null",
  "hours_logged": "float or null"
}
```

### VolunteerServiceSummary
```json
{
  "volunteer_id": "UUID",
  "total_hours": 12.5,
  "shifts_count": 3,
  "period_start": "datetime or null",
  "period_end": "datetime or null",
  "role_summary": "Transport, Dog Walking"
}
```

### DownloadUrlResponse
```json
{
  "download_url": "S3_PRESIGNED_DOWNLOAD_URL",
  "object_key": "certificates/service_certificate_profile_uuid.pdf",
  "file_id": "UUID"
}
```

---

## 🔄 3. Workflow & Eligibility

### Attendance Status Lifecycle
Status values defined by the `AttendanceStatus` enum:
- `claimed`: Joined the shift, waiting for check-in.
- `checked_in`: Active on the shift.
- `checked_out`: Completed the shift.
- `no_show`: Marked as absent by coordinator.
- `cancelled`: Cancelled by volunteer before shift.

### Certificate Eligibility
- **Condition**: The volunteer must have completed at least one shift (`shifts_count > 0`).
- **Error**: If 0 shifts are completed, `400 Bad Request` (`ValidationFailedError`) is returned: `"No verified shifts to certify; the volunteer must complete at least one attended shift first."`

### Self-Service Authorization
- **Yes**. The profile owner (`profile.user_id == current_user.user.id`) can request their own service summary, check in/out, and generate certificates without requiring elevated administrative permissions.
