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
| SCREENING | INTERVIEW | **Requires verified applicant documents** (`documents_verified_at`) |
| INTERVIEW | HOME_CHECK | **Exclusivity lock activated** |
| HOME_CHECK | APPROVED | **Agreement PDF generated** |
| APPROVED | COMPLETED | **Dog status -> ADOPTED** |
| Any pre-completion | REJECTED | No locking needed |

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `AdoptionApplication` | `adoption_applications` | Core application with status, vetting notes, applicant documents |
| `AdoptionScore` | `adoption_scores` | 4-dimension evaluation, typed `interview` or `home_inspection` |
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
| PUT | `/adoptions/{id}/fee` | `adoption:process` | Set adoption fee (not printed on the agreement) |
| POST | `/adoptions/{id}/documents/upload-url` | Owner or `adoption:process` | Presigned upload URL (PDF/JPEG/PNG, 10MB) |
| POST | `/adoptions/{id}/documents` | Owner or `adoption:process` | Attach an uploaded applicant document |
| POST | `/adoptions/{id}/documents/verify` | `adoption:process` | Mark Phase 1 documents verified |
| DELETE | `/adoptions/{id}/documents/{doc_id}` | Owner or `adoption:process` | Remove a wrongly uploaded document |
| GET | `/adoptions/{id}/documents/{doc_id}/download` | Owner or `adoption:read` | Presigned download URL |
| POST | `/adoptions/{id}/follow-ups` | `adoption:process` | Create follow-up |
| GET | `/adoptions/{id}/follow-ups` | Authenticated | View follow-ups |
| POST | `/adoptions/{id}/follow-ups/{fid}/proof` | Owner or `adoption:process` | Submit proof |
| DELETE | `/adoptions/{id}` | `adoption:delete` | Soft delete |
| GET | `/adoptions/nearby-shelters` | Authenticated | Find nearby shelters |
| POST | `/adoptions/bulk/status-update` | `adoption:process` | Bulk status |
| POST | `/adoptions/bulk/delete` | `adoption:delete` | Bulk soft delete |

`adoption:delete` is seeded only for `rescue_centre_admin` (`super_admin` bypasses all permission checks) —
Adoption Coordinator's `adoption:process` covers routine pipeline work but not deletion, matching the
workflow doc's RBAC matrix (`docs/workflow/08-adoption.md` §16). Previously both delete endpoints
incorrectly accepted `adoption:process` too, so a Coordinator could delete applications; fixed to use
the already-seeded-but-previously-unenforced `adoption:delete` permission.

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
- Content: org header, adopter name, dog details, liability waiver, signature line (no fee: adoption is free)
- Generated via `reportlab` in a thread (CPU-bound)
- Uploaded to S3: `documents/agreement_{application_id}.pdf`
- Download via presigned URL

## Applicant Documents (Phase 1)

Document types: `identity_proof`, `address_proof`, `landlord_approval`, `pet_medical_record`, `other`.

- Verification requires an `identity_proof`, plus a `landlord_approval` when `residential_status` is rented.
- Verification is only possible while SUBMITTED or SCREENING, and SCREENING -> INTERVIEW is refused until it is done
  (also enforced on bulk status updates). Foster-to-Adopt applications skip straight to HOME_CHECK (PRR 3.8).
- Adding or removing a document while SUBMITTED/SCREENING clears an earlier verification so the change is reviewed.

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

**Overall** = average of all four. Multiple scores can be recorded per application; `score_type` separates the
phone-interview score sheet from the home-inspection one (defaults to `interview` for older clients).

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| Application submitted | Notifications | In-app + email + push to adopter |
| Status change | Notifications | In-app + email + push on approved/rejected/completed |
| APPROVED | Storage | Agreement PDF uploaded to S3 |
| COMPLETED | Dog | `dog.status = ADOPTED`, `dog.is_adoptable = False` |
| Follow-up due | Notifications | Push to adopter (30/90/180 day) |
