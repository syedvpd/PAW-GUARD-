# Adoption Module

Adoption application lifecycle with exclusivity locks, agreement PDF generation, scoring, and post-adoption follow-ups.

---

## Architecture

```
adoption/
  router.py          # 18 endpoints
  service.py         # AdoptionService (lifecycle, locking, agreements)
  repository.py      # Data access
  models.py          # ORM models + enums
  schemas.py         # Pydantic DTOs
```

## State Machine

```
SUBMITTED ──> SCREENING ──> INTERVIEW ──> HOME_CHECK ──> APPROVED ──> COMPLETED
    │             │             │              │              │
    └──reject──> REJECTED <──reject── REJECTED <──reject── REJECTED <──reject── REJECTED
```

| From | To | Notes |
|------|----|-------|
| SUBMITTED | SCREENING | Initial review |
| SCREENING | INTERVIEW | Background check |
| INTERVIEW | HOME_CHECK | **Exclusivity lock activated** |
| HOME_CHECK | APPROVED | **Agreement PDF generated** |
| APPROVED | COMPLETED | **Dog status -> ADOPTED** |
| Any pre-completion | REJECTED | No locking needed |

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `AdoptionApplication` | `adoption_applications` | Core application with status, vetting notes, fee |
| `AdoptionScore` | `adoption_scores` | 4-dimension evaluation (home, pet_care, financial, lifestyle) |
| `AdoptionFollowUp` | `adoption_follow_ups` | 30/90/180-day post-adoption milestones |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/adoptions` | Authenticated | Submit application |
| GET | `/adoptions/my` | Authenticated | My applications |
| GET | `/adoptions` | `adoption:read` | All applications |
| GET | `/adoptions/{id}` | Owner or `adoption:read` | Single application |
| GET | `/adoptions/{id}/agreement` | Authenticated | Download agreement PDF |
| PUT | `/adoptions/{id}` | `adoption:process` | Update application |
| PATCH | `/adoptions/{id}/status` | `adoption:process` | Update status |
| POST | `/adoptions/{id}/scores` | `adoption:process` | Add evaluation score |
| GET | `/adoptions/{id}/scores` | Authenticated | View scores |
| PUT | `/adoptions/{id}/fee` | `adoption:process` | Set adoption fee |
| POST | `/adoptions/{id}/follow-ups` | `adoption:process` | Create follow-up |
| GET | `/adoptions/{id}/follow-ups` | Authenticated | View follow-ups |
| POST | `/adoptions/{id}/follow-ups/{fid}/proof` | Owner or `adoption:process` | Submit proof |
| DELETE | `/adoptions/{id}` | `adoption:process` | Soft delete |
| GET | `/adoptions/nearby-shelters` | Authenticated | Find nearby shelters |
| POST | `/adoptions/bulk/status-update` | `adoption:process` | Bulk status |
| POST | `/adoptions/bulk/delete` | `adoption:process` | Bulk soft delete |

## Exclusivity Lock Mechanism

Two-tier distributed lock preventing concurrent approvals for the same dog:

**Tier 1 — Database Row Lock (Authoritative):**
```
SELECT ... FOR UPDATE on dog_profiles
-> Serializes concurrent transactions
-> Used at: submission, HOME_CHECK, APPROVED, COMPLETED
```

**Tier 2 — Redis Lock (Best-Effort, Reduces Contention):**
```
CacheService.acquire_lock("lock:dog:{dog_id}", token, expire_ms=10000)
-> SET key value NX PX 10000
-> Lua script for atomic release
-> Fail-closed if Redis unavailable
```

**Locking statuses:** HOME_CHECK, APPROVED, COMPLETED — once any application reaches HOME_CHECK, no other application for the same dog can proceed past SCREENING.

## Agreement PDF

Auto-generated on APPROVED status:
- Content: org header, adopter name, dog details, fee, liability waiver, signature line
- Generated via `reportlab` in a thread (CPU-bound)
- Uploaded to S3: `documents/agreement_{application_id}.pdf`
- Download via presigned URL

## Follow-Up System

**Milestones:** 30, 90, 180 days after `completed_at`

**Status flow:**
```
PENDING ──submit proof──> SUBMITTED
PENDING ──due_at passes──> OVERDUE (via background job)
OVERDUE ──late submit──> SUBMITTED
```

**Proof submission:** `media_keys` (photos/videos) + notes. Owner or staff.

## Scoring

4 dimensions (each 1-10):
- `home_environment_score`
- `pet_care_knowledge_score`
- `financial_readiness_score`
- `lifestyle_compatibility_score`

**Overall** = average of all four. Multiple scores can be recorded per application.

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Application submitted | Notifications | In-app + email + push to adopter |
| Status change | Notifications | In-app + email + push on approved/rejected/completed |
| APPROVED | Storage | Agreement PDF uploaded to S3 |
| COMPLETED | Dog | `dog.status = ADOPTED`, `dog.is_adoptable = False` |
| Follow-up due | Notifications | Push to adopter (30/90/180 day) |
