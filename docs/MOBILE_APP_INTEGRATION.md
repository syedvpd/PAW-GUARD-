# Mobile App Shell Integration Guide (Flutter / React Native)

This document maps the backend APIs the PRR mobile app shell must consume to
deliver: Auth, Profile Management, Medical History Uploads, and Fixes/26. It is
backend-side guidance for the mobile team.

## Base URL & conventions

- Base: `https://pawguard-backend-mqri.onrender.com/api/v1` (live) or
  `http://localhost:8000/api/v1` (dev).
- Auth: `Authorization: Bearer <access_token>` on every authenticated request.
- Envelope: `{ success, data, message, meta? }` (errors use
  `{ success:false, error }`).
- Dates: ISO-8601 UTC (e.g. `2026-09-01T09:00:00Z`).
- IDs: UUID v4 (strings in JSON).
- Pagination: `?page=1&page_size=20` → `meta.{page,page_size,total,total_pages}`.

## Recommended architecture on the client

- A single `ApiClient` (dio in Flutter / axios in RN) injecting the bearer token,
  retrying on 401 via the refresh-token flow (`POST /auth/refresh`).
- A `feature/companion_pet` layer (profiles + medical + reminders).
- A `feature/lost_found` layer (alert broadcast + found reporting + matches).
- A `feature/safety_tag` layer (QR provisioning + scan screen).
- Offline/cache for the limited PII-free scan payload and the vet directory list.

## 1. Auth (owned by `auth` module)

| Feature | Endpoint | Notes |
|---------|----------|-------|
| Register | `POST /auth/register` | `{email,password,full_name,phone}` |
| Login | `POST /auth/login` | returns `access_token` / `refresh_token` |
| MFA flow | `/auth/mfa/enroll`, `/auth/mfa/enroll/confirm`, `/auth/mfa/verify` | if enabled |
| Refresh | `POST /auth/refresh` | swap refresh token for new access token |
| Me | `GET /auth/me` | load profile screen |
| Logout | `POST /auth/logout`, `POST /auth/logout-all` | |

Store the access token in secure storage (flutter_secure_storage /
expo-secure-store); never in AsyncStorage/plaintext.

## 2. Profile management (companion pet)

Pet profile = the owner's "pet profile". Use:

- `POST /companion-pets` — create the owner's pet (onboarding).
- `GET /companion-pets` — show the owner's pet list.
- `GET /companion-pets/{pet_id}` — pet detail screen.
- `PATCH /companion-pets/{pet_id}` — edit screen (color, emergency_notes,
  microchip_id, is_scan_enabled).
- `DELETE /companion-pets/{pet_id}` — remove a pet (soft delete).

## 3. Medical history uploads

Two-step upload (do not upload files through the API server):

1. `POST /companion-pets/{pet_id}/medical-files/upload-url`
   `{original_filename, mime_type, file_size}` → `{upload_url, object_key, file_id}`.
2. PUT the file bytes **directly to the `upload_url`** (S3 presigned).
3. `PUT /companion-pets/{pet_id}/medical-files/{file_id}/confirm` → records the
   stored file.
4. Optionally `POST /companion-pets/{pet_id}/medical-records`
   `{record_type, title, notes, occurred_at, stored_file_id, clinic_id}` to
   attach a typed record. `GET /companion-pets/{pet_id}/medical-files` and
   `/medical-records` to render the history screen.

## 4. QR safety tag

- `POST /companion-pets/{pet_id}/safety-tag` → returns `raw_token` **once**. The
  mobile app must immediately render the QR (`https://pawguard.app/qr/<token>`)
  and persist it securely; the backend cannot recover it.
- `GET /companion-pets/{pet_id}/safety-tag` to show `token_prefix` / `scan_count`
  / `last_scanned_at` metadata on the tag screen.
- The *finder-side* scan screen POSTs the scanned token to the public
  `POST /companion-pets/safety-tag/scan` (no auth) and displays the safe
  `SafetyTagScanResponse`.

## 5. Vet directory & appointments

- Directory: `GET /companion-pets/clinics` (public). Render with map pins
  (`latitude`/`longitude`), emergency badge (`is_emergency`).
- Booking: `POST /companion-pets/appointments`
  `{pet_id, clinic_id, vet_id?, starts_at, ends_at, reason}`.
- Status: `GET /companion-pets/appointments` (list), `/{id}` (detail),
  `/confirm` (clinic staff), `/cancel`.

## 6. Reminders

- `POST /companion-pets/{pet_id}/reminders` `{kind, title, details, due_at, source_key}`
  to schedule a vaccination/medication reminder. `kind` ∈ `vaccination|medication`.
- `GET /companion-pets/{pet_id}/reminders` for the reminders list screen.
- Delivery is push-in-app via `GET /notifications`; poll or socket as needed.
  `source_key` makes duplicates safe.

## 7. Lost-pet alerts

- On a lost pet: `POST /lost-found/lost` with GPS + details.
- One-tap broadcast: `POST /lost-found/lost/{report_id}/broadcast` →
  `{queued:true}`. Fans out to the community in the background.
- Found a pet: `POST /lost-found/found` with GPS; `GET /lost-found/lost/{id}/matches`
  to see auto-matches.
- Owner proof: `POST /lost-found/matches/{match_id}/claim`; admin reviews via
  `POST /lost-found/matches/{match_id}/claim/review`.

## 8. Public emergency rescue (PRR)

- Anonymous: `POST /public/rescue/report` (no auth) for community emergencies;
  rate limited 5/min.
- Status lookup: `GET /rescue/status?ticket_number=&phone=` (public, no PII).

## Implementation checklist (mobile)

- [ ] Auth + token refresh interceptor
- [ ] Companion pet CRUD screens
- [ ] Medical upload (presigned two-step) with progress UI
- [ ] QR generate screen + secure token persistence + display tag
- [ ] Public scan screen (no-auth) showing safe payload
- [ ] Vet directory list + map + booking flow + cancel
- [ ] Reminders CRUD + notifications inbox
- [ ] Lost-pet report + broadcast button + matches list + found report
- [ ] Anonymous rescue report flow + status lookup
- [ ] Push notification handling wired to `/notifications` payloads

## Postman

Import `PawGuard.postman_collection.json` to drive every flow above before
writing a line of mobile code; see `POSTMAN_API_TESTING_GUIDE.md`.