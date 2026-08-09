# Lost Pet Alert System — Broadcast Alerts, GPS Pinning, QR Scan Flow

A functional, end-to-end lost-pet pipeline: a lost report with GPS coordinates,
auto-matching against found reports, a one-click **community broadcast** to every
active user, and integration with the **QR safety-tag scan** so finders can act
fast without exposing owner PII.

## Components

1. **Lost report** (`POST /lost-found/lost`) — pet details + `latitude`/`longitude`
   + `location_address` + `lost_at`.
2. **GPS-based matching engine** — ranks found reports by breed/color proximity,
   geographic distance, temporal gap, collar colour, and distinctive markers.
3. **Community broadcast** (`POST /lost-found/lost/{report_id}/broadcast`) —
   asynchronous fan-out via ARQ.
4. **QR scan bridge** (`POST /companion-pets/safety-tag/scan`) — finder scans the
   pet's QR and gets `emergency_notes` to act, with no PII leak.
5. **Reunion workflow** — ownership-claim submission + admin review → resolves and
   closes both reports.

## 1. GPS location pinning

On lost/found report creation the client sends `latitude` + `longitude` (and a
human `location_address`). The match-score engine (`LostFoundService._evaluate_match_score`)
uses the haversine distance between the lost and found coordinates:

- **distance ≤ ~1 km** → strong geographic boost
- distance up to ~25 km → partial boost
- distance > 25 km → capped/partial
- combined with breed/color match → `confidence_score` 0–100
- temporal gap (days between lost_at and found_at) penalises long gaps
- matching collar colour and distinctive marker text add boosts

Output is a ranked list of `ReportMatch` rows with `confidence_score`, `gap_days`,
`dist_km`, and human-readable `reasons`.

## 2. Community broadcast (exactly-once fan-out)

### Endpoint
`POST /lost-found/lost/{report_id}/broadcast`
- Permission: `lost_found:broadcast` (granted to `general_public`, `donor`).
- The reporter (or an admin) may broadcast; other users get `403`.
- Only **active** reports can be broadcast (resolved → `422`).
- Rate limited: **3 broadcasts per hour** per caller.
- Returns immediately: `{ "report_id": "...", "queued": true }` — HTTP stays fast.

### Worker (`broadcast_lost_pet_alert`, ARQ)
1. Acquires a **row lock** (`SELECT ... FOR UPDATE`) on the lost report.
2. If the report is missing, not active, or already has `broadcasted_at` set →
   return early (idempotent — safe under ARQ retries and concurrent runs).
3. Selects all active, non-deleted users except the reporter.
4. Sends `NotificationService.broadcast` in **500-user batches** so memory stays
   bounded even at millions of users.
5. Sets `lost_reports.broadcasted_at = now()` and commits.
6. Each recipient gets a `lost_pet_alert` notification with a deep link to the
   report.

### Exactly-once guarantee
The combination of the row lock and the `broadcasted_at` marker means a second
enqueue (manual retry, ARQ retry, or a duplicate request) does **not** produce a
second alert wave. Migration `4f3c25a44f2e` adds the `broadcasted_at` column +
index.

## 3. QR safety-tag scan flow

For full QR engine details see `QR_SAFETY_TAGS.md`. In the lost-pet context:

- A finder scans the pet's QR → `POST /companion-pets/safety-tag/scan`.
- The response carries `emergency_notes` (e.g. "Diabetic, needs insulin, call
  any 24h vet") but **no owner contact info or microchip**.
- The finder files a `POST /lost-found/found` report with the GPS location of the
  sighting.
- The match engine links the found report to the active lost report
  (`confidence_score` reflects proximity + breed/color match).
- The owner is notified of the match and can submit an ownership claim; an admin
  reviews and resolves both reports.

## 4. Reunion closure

| Step | Endpoint | By |
|------|----------|----|
| Owner submits claim with proof | `POST /lost-found/matches/{match_id}/claim` | owner |
| Admin reviews claim | `POST /lost-found/matches/{match_id}/claim/review` | admin |
| Approve → confirms match + resolves both reports | (same) | admin |
| Reject → status `rejected` | (same) | admin |

## 5. Test plan (manual)

See `POSTMAN_API_TESTING_GUIDE.md` §7:

1. Create a lost report with GPS (201).
2. Broadcast (200, `queued:true`); repeat to hit 429 (3/h).
3. As a second user, confirm a `lost_pet_alert` notification arrived.
4. Create a found report with nearby GPS + matching breed/color.
5. List lost matches → ensure high `confidence_score`.
6. Verify re-running the broadcast worker is a no-op (`broadcasted_at` set).
7. Scan the pet's QR and confirm no PII leaks.