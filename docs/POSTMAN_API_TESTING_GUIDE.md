# Postman API Testing Guide — PRR Pet Vertical 

This guide covers manual testing in Postman for every task completed today:
companion pets, medical uploads, QR safety tags, vet directory & appointments,
smart reminders, lost-pet alerts, public rescue reporting, and the dog public
directory fix.

## 0. Setup

1. **Import the collection.** In Postman → Import → choose
   `PawGuard.postman_collection.json` from the repo root. It is grouped by tag
   and already wired with `baseUrl` and `accessToken` variables.
2. **Set the environment variables:**
   - `baseUrl` → `https://pawguard-backend-mqri.onrender.com/api/v1` (live) or
     `http://localhost:8000/api/v1` (local).
   - `accessToken` → paste the `access_token` returned by the Login request
     (step 1 below). All requests send `Authorization: Bearer {{accessToken}}`.
3. **Auth note.** Register a user, promote to `super_admin` in the DB to bypass
   MFA, or use the test helper. For role-scoped tests, register users and grant
   the relevant role (donor / general_public / rescue_agent / vet staff) via the
   seed script. Admin roles (`super_admin`, `rescue_centre_admin`, `shelter_admin`)
   bypass permission checks, so use them only for setup, then switch to the
   target role to test real authorization.
4. **Rate limits.** Several endpoints are throttled (rescue report, safety-tag
   scan, broadcast). If a request suddenly returns `429`, wait 60s.

> The live Render deploy rebuilds after each `main` push (≈2–5 min). If
> `/docs` does not yet show `companion-pets/*`, the deploy is still running.

---

## 1. Auth — get a token

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 1 | POST | `/auth/register` | `{email,password,full_name,phone}` | 201 |
| 2 | POST | `/auth/login` | `{email,password}` | 200 → copy `data.access_token` into `accessToken` |
| 3 | GET | `/auth/me` | — | 200 (verify token works) |

If MFA is enforced, complete `/auth/mfa/enroll` → `/auth/mfa/enroll/confirm`
→ re-login → `/auth/mfa/verify`, then refresh.

---

## 2. Companion Pet Profiles (Owner)

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 4 | POST | `/companion-pets` | `{name,species,breed,color,microchip_id,emergency_notes,is_scan_enabled}` | 201 → save `data.id` as `petId` |
| 5 | GET | `/companion-pets` | — | 200 paginated, only caller's pets |
| 6 | GET | `/companion-pets/{{petId}}` | — | 200 |
| 7 | PATCH | `/companion-pets/{{petId}}` | `{color:"tan"}` | 200 |
| 8 | DELETE | `/companion-pets/{{petId}}` | — | 200 (soft delete) |

**Authz test:** log in as a *different* owner and `GET /companion-pets/{{petId}}`
→ expect **403**. Admins get 200.

---

## 3. Medical History Uploads

Two-step presigned upload flow (same pattern as rescue/storage modules).

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 9 | POST | `/companion-pets/{{petId}}/medical-files/upload-url` | `{original_filename,mime_type,file_size}` | 201 → `data.upload_url` + `object_key` |
| 10 | PUT | (the `upload_url` directly to S3) | raw file bytes | 200 from S3 |
| 11 | PUT | `/companion-pets/{{petId}}/medical-files/{{fileId}}/confirm` | — | 200 |
| 12 | GET | `/companion-pets/{{petId}}/medical-files` | — | 200 paginated |
| 13 | POST | `/companion-pets/{{petId}}/medical-records` | `{record_type,title,notes,occurred_at,stored_file_id}` | 201 |
| 14 | GET | `/companion-pets/{{petId}}/medical-records` | — | 200 list |
| 15 | DELETE | `/companion-pets/medical-records/{{recordId}}` | — | 200 |

> In step 9, `file_id` returned in the response is the `fileId` for step 11.

---

## 4. QR Safety Tag Generation Engine

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 16 | POST | `/companion-pets/{{petId}}/safety-tag` | — | 201 → **copy `data.raw_token`** (returned once; never shown again) |
| 17 | GET | `/companion-pets/{{petId}}/safety-tag` | — | 200 metadata only (no token; note `token_prefix`) |
| 18 | POST | `/companion-pets/safety-tag/scan` | `{token:"{{raw_token}}"}` | 200 → pet's public safe fields, no PII |
| 19 | POST | `/companion-pets/safety-tag/scan` | `{token:"WRONG"}` | 404 |
| 20 | POST | `/companion-pets/safety-tag/scan` | repeat 21× | 21st → **429** (rate limited 20/min) |

**QR engine rules (verification):**
- Provisioning again **rotates** the token and invalidates the old raw token
  (scanning the old token → 404).
- The scan response exposes only `name, species, breed, color, emergency_notes`
  — never owner contact info or microchip.
- `disable is_scan_enabled` on the pet → scan returns 404.

> Build the QR code: encode the `raw_token` (or a URL like
> `https://pawguard.app/qr/<raw_token>`) into a QR image client-side. The
> scanner app POSTs the token to `/safety-tag/scan`.

---

## 5. Vet Directory & Appointment Booking

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 21 | GET | `/companion-pets/clinics` | `?search=vet` | 200 paginated, anonymous-safe |
| 22 | POST | `/companion-pets/clinics` | `{name,address,phone,email,services,latitude,longitude,is_emergency}` | 201 → save `clinicId` |
| 23 | PATCH | `/companion-pets/clinics/{{clinicId}}` | `{is_emergency:true}` | 200 |
| 24 | DELETE | `/companion-pets/clinics/{{clinicId}}` | — | 200 |
| 25 | POST | `/companion-pets/clinics/{{clinicId}}/memberships` | `{user_id,membership_role:"staff"}` | 201 |
| 26 | POST | `/companion-pets/appointments` | `{pet_id,clinic_id,vet_id,starts_at,ends_at,reason}` | 201 → save `appointmentId` |
| 27 | GET | `/companion-pets/appointments` | `?pet_id=&clinic_id=` | 200 paginated |
| 28 | GET | `/companion-pets/appointments/{{appointmentId}}` | — | 200 |
| 29 | POST | `/companion-pets/appointments/{{appointmentId}}/confirm` | — | 200 (clinic staff only) |
| 30 | POST | `/companion-pets/appointments/{{appointmentId}}/cancel` | `{reason}` | 200 |

**Authz tests:**
- `confirm` requires `appointment:manage` (clinic staff) → owner gets **403**.
- `cancel` requires `appointment:cancel`.
- Double-booking the same pet + overlapping time → **409** (exclusion constraint).

---

## 6. Smart Reminders Engine (Vaccination & Medication)

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 31 | POST | `/companion-pets/{{petId}}/reminders` | `{kind:"vaccination",title,details,due_at,source_key}` | 201 |
| 32 | POST | `/companion-pets/{{petId}}/reminders` | `{kind:"medication",...}` | 201 |
| 33 | GET | `/companion-pets/{{petId}}/reminders` | — | 200 list |
| 34 | DELETE | `/companion-pets/{{petId}}/reminders/{{reminderId}}` | — | 200 |

`kind` ∈ `vaccination` | `medication`. `source_key` is the idempotency key —
duplicate `source_key` for the same pet is rejected to prevent double reminders.

**Delivery:** the ARQ cron `send_companion_pet_reminders` runs daily at **09:45**,
finds active reminders due within the next 48h, and pushes an in-app notification
via `NotificationService`. To verify delivery manually, set `due_at` to ~now+1h
and run the job: `python -c "import asyncio; from pawguard.workers.jobs.companion_pet_jobs import send_companion_pet_reminders; asyncio.run(send_companion_pet_reminders({}))"`.

---

## 7. Lost Pet Alert System (Broadcast + GPS + QR scan)

| # | Method | URL | Body | Expected |
|---|--------|-----|------|----------|
| 35 | POST | `/lost-found/lost` | `{pet_name,breed,color,location_address,latitude,longitude,lost_at}` | 201 → save `reportId` |
| 36 | GET | `/lost-found/lost` | — | 200, reporter PII masked for anonymous |
| 37 | POST | `/lost-found/lost/{{reportId}}/broadcast` | — | 200 `{queued:true}` |
| 38 | POST | `/lost-found/lost/{{reportId}}/broadcast` | repeat 4× | 4th → **429** (3/hour rate limit) |
| 39 | POST | `/lost-found/found` | `{breed_observed,color_observed,location_address,latitude,longitude,found_at}` | 201 |
| 40 | GET | `/lost-found/lost/{{reportId}}/matches` | — | 200 list |

**Broadcast flow:** the endpoint enqueues an ARQ job (`broadcast_lost_pet_alert`)
and returns immediately (HTTP stays fast). The worker fans out notifications to
**all active users** (excluding the reporter) in **500-user batches**, then stamps
`broadcasted_at` so retries/waves are **exactly-once**. Verify: as a second user,
check `GET /notifications` for the `lost_pet_alert` notification.

**GPS pinning:** `latitude`/`longitude` on the lost/found report power the
match-score geographic distance; the match engine boosts nearby, temporally close
reports (see `_evaluate_match_score`). Postman can't pin a GPS map, but you
can validate that close coords + same breed/color yield `confidence_score >= 80`.

**QR scan → lost alert link:** a tag scanned via `/companion-pets/safety-tag/scan`
returns the pet's `emergency_notes`; pair that with the active lost report to
reunite. (The scan response itself intentionally carries no owner PII.)

---

## 8. Public Rescue Reporting (PRR split)

| # | Method | URL | Body | Auth | Expected |
|---|--------|-----|------|------|----------|
| 41 | POST | `/public/rescue/report` | `{reporter_name,reporter_phone,location_address,physical_condition}` | none | 201 |
| 42 | POST | `/public/rescue/report` | repeat 6× | none | 6th → **429** (5/min) |
| 43 | POST | `/rescue/report` | same body | `rescue:create` | 201 (staff) or **403** (no permission) |
| 44 | GET | `/rescue/status?ticket_number=&phone=` | — | none | 200 public status, no PII |

The split keeps `POST /rescue/report` gated (staff workflow) while
`POST /public/rescue/report` allows anonymous community emergency reporting.

---

## 9. Dog Public Directory Regression Fix

| # | Method | URL | Auth | Expected |
|---|--------|-----|------|----------|
| 45 | POST | `/dogs` | admin | 201 (create a non-adoptable dog) |
| 46 | GET | `/dogs` | none | 200 — list contains **only** adoptable dogs |
| 47 | GET | `/dogs/{{nonAdoptableId}}` | none | **404** (must not leak) |
| 48 | GET | `/dogs/{{nonAdoptableId}}` | admin token | 200 (staff sees all) |

Verify that anonymous `/dogs` no longer returns internal UUIDs
(`microchip_id`, `rescue_case_id`, `shelter_facility_id`, `kennel_id` are `null`).

---

## 10. Swagger UI verification

- Local: http://localhost:8000/docs
- Live: https://pawguard-backend-mqri.onrender.com/docs

Search the Swagger page for `companion-pets`, `lost-found/lost/{report_id}/broadcast`,
and `public/rescue/report`. All three must be present after the deploy completes.

The committed `openapi.json` snapshot (336 paths) is the source of truth; you can
also import it directly into Postman via *Import → File*.

---

## Troubleshooting

| Symptom | Cause / Fix |
|---------|------------|
| 401 on every call | `accessToken` variable empty/expired → re-login |
| 403 | role lacks the required permission — check `seed_roles_and_permissions.py` grants |
| 429 | rate limit hit — wait 60s / 1h depending on endpoint |
| 422 on appointment | `ends_at` not after `starts_at`, or missing required fields |
| 409 on appointment | double-booking (exclusion constraint) — choose a non-overlapping slot |
| 404 on safety-tag scan | wrong token, tag rotated, or `is_scan_enabled=false` |
| `/docs` missing new routes | Render deploy still running — wait 2–5 min after push |