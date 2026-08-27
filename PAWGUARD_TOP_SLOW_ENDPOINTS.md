# PawGuard — Top Slow Endpoints (Performance Backlog)

> Source: outbound-bandwidth / request-latency forensic pass (Render period
> 2026-08-22 → 2026-08-27). Latency figures are the observed warm/cold request
> times reported for that period and **must be re-measured against a live backend**
> (no DB/Redis available in the analysis environment).

Priority order follows the execution mandate: **P0 → P1 → P2 → P3**.

---

## P0 — Critical (correctness + latency)

| Endpoint | Issue | Status |
| --- | --- | --- |
| `GET /api/v1/portal/urgent-alerts` | HTTP **500** (missing `count_active_alerts`, wrong `list_active_alerts` signature) | **FIXED** (portal/repository.py) |

---

## P1 — Companion Pets

| Endpoint | Observed | Root cause (hypothesis) | Action |
| --- | --- | --- | --- |
| `POST /api/v1/companion-pets/safety-tag/scan` | ~4.8s | Synchronous FCM push inside request path | **FIXED** — offloaded to ARQ job `notify_safety_tag_scan` |
| `POST /api/v1/companion-pets/{pet_id}/reminders` | ~7.3s | Shared auth chain (2 DB + 1 Redis per request); no inline external call in code — likely DB/pool latency | Measure `get_db` acquire + `require_permission` cache hit; run `get_current_user` queries concurrently |
| `POST /api/v1/companion-pets/appointments/{id}/cancel` | ~3.4s | `get_appointment` + `flush` + `refresh` + audit; no inline external call | Drop unnecessary `_session.refresh` if safe (needs DB) |
| `POST /api/v1/companion-pets/appointments/{id}/confirm` | ~1.9s | Same as cancel | Same as cancel |

---

## P2 — Adoption

| Endpoint | Observed | Likely cause | Action |
| --- | --- | --- | --- |
| `GET /api/v1/adoption/applications` | ~1.2s | N+1 eager loads (adopter/shelter), missing index on sort/filter | `EXPLAIN ANALYZE`; add covering index; keyset pagination |
| `GET /api/v1/adoption/pets` | ~600ms–900ms | List scan + relation lazy loads | `selectinload` + index review |
| `POST /api/v1/adoption/applications` | ~800ms | Write + multiple dependent inserts + audit | Batch dependent inserts |

---

## P3 — Dogs

| Endpoint | Observed | Likely cause | Action |
| --- | --- | --- | --- |
| `GET /api/v1/dogs` | ~561ms cold / ~593ms warm | List query missing index coverage on default sort + shelter filter; per-row relation lazy loads | Add index; `selectinload` |
| `POST /api/v1/dogs/bulk/delete` | ~86ms cold / **~1.1s warm** | Warm-slower-than-cold regression: per-dog activity inserts in a loop + 6 Redis `DELETE`s every call | Batch activity inserts; make cache invalidation conditional |

---

## Cross-cutting (applies to P1/P2/P3)

1. **Auth dependency cost** — every authed request runs `get_current_user`
   (2 sequential DB queries) then `require_permission` (1 Redis GET + optional 1
   DB query). Run the two `get_current_user` queries concurrently; verify RBAC
   cache hit-rate in production before tuning.
2. **Pagination** — confirm all list endpoints use keyset pagination on large
   tables; offset pagination degrades as `offset` grows.
3. **Eager loading** — replace per-row relationship lazy loads with
   `selectinload`/`joinedload` to kill N+1 patterns in list endpoints.

---

## Out of scope (do not change this pass)

SSE, Brevo email, presigned-S3 thumbnails, FCM/Razorpay/OAuth transport, and all
healthy modules (Rescue, Shelter, Medical, Finance, Volunteer, Foster, Admin).
