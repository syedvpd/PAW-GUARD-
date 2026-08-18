# Lost & Found Module

Lost/found pet reporting, algorithmic matching, reunification, broadcast alerts, and ownership claims.

---

## Architecture

```
lost_found/
  router.py          # 18 endpoints
  service.py         # LostFoundService (matching, broadcast, claims)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `LostReport` | `lost_reports` | Lost pet: name, breed, color, location, photo |
| `FoundReport` | `found_reports` | Found pet: breed, color, collar, location |
| `ReportMatch` | `report_matches` | Match between lost+found with confidence score |
| `PetSighting` | `pet_sightings` | Public sighting reports |

## State Machines

```
LostReport:  ACTIVE ──resolve──> RESOLVED | EXPIRED
FoundReport: ACTIVE ──resolve──> RESOLVED | EXPIRED
Match:       PENDING ──confirm──> CONFIRMED | REJECTED
```

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/lost-found/lost` | Auth (rate-limited) | Report lost pet |
| POST | `/lost-found/found` | Auth (rate-limited) | Report found pet |
| POST | `/lost-found/sighting` | Public (rate-limited) | Report sighting |
| POST | `/lost-found/lost/{id}/broadcast` | `lost_found:broadcast` | Broadcast alert |
| GET | `/lost-found/lost` | Public | List lost reports |
| GET | `/lost-found/found` | Public | List found reports |
| GET | `/lost-found/lost/{id}` | Public | Get lost report |
| GET | `/lost-found/found/{id}` | Public | Get found report |
| GET | `/lost-found/lost/{id}/matches` | Owner or `public:read` | View matches |
| GET | `/lost-found/found/{id}/matches` | Owner or `public:read` | View matches |
| POST | `/lost-found/matches/{id}/claim` | Auth (rate-limited) | Submit ownership claim |
| POST | `/lost-found/matches/{id}/claim/review` | `system:admin` | Review claim |
| POST | `/lost-found/matches/{id}/resolve` | `system:admin` | Resolve match |
| GET | `/lost-found/reunion-stories` | Public | Success stories |
| DELETE | `/lost-found/lost/{id}` | `system:admin` | Soft delete |
| DELETE | `/lost-found/found/{id}` | `system:admin` | Soft delete |

## Algorithmic Matching

When a lost or found report is created, `_run_matching_for_lost/found()` executes:

**Scoring factors:**
| Factor | Weight |
|--------|--------|
| Haversine distance | Closer = higher score |
| Breed exact match | +points |
| Breed partial match | +points |
| Color exact match | +points |
| Color partial match | +points |
| Temporal alignment | Recent = higher |
| Collar/markers match | +points |

**Threshold:** Score >= 50 creates a `ReportMatch` record.

**Notifications:** Both parties notified via email + push on match creation.

## Broadcast Alert

```
POST /lost-found/lost/{id}/broadcast
  -> Queue ARQ job: broadcast_lost_pet_alert
  -> Background job:
     -> Find all active users (excluding reporter)
     -> Create in-app notifications in batches of 500
     -> Send push notifications to all recipients
     -> Mark report.broadcasted_at = now
```

## Contact Release (Reunification)

When a match is CONFIRMED:
```
-> Notify lost owner: finder's contact info (name, email, phone)
-> Notify found reporter: owner's contact info (name, email, phone)
-> Push notification to both parties
```

## Ownership Claim Flow

```
POST /lost-found/matches/{id}/claim {claimant_notes}
  -> Create claim record

POST /lost-found/matches/{id}/claim/review {approve, notes}
  -> If approved: resolve both reports, release contacts
  -> If rejected: notify claimant
```

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Sighting reported | Notifications | Push + email to pet owner |
| Match found | Notifications | Push + email to both parties |
| Match confirmed | Notifications | Push to both (contact release) |
| Broadcast queued | ARQ Worker | Background fan-out to all users |
