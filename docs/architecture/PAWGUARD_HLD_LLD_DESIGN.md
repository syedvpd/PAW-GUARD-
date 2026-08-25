# PawGuard System Architecture: High-Level Design (HLD) & Low-Level Design (LLD)

**Document Reference**: HLD-LLD-PAWGUARD-2026-V1  
**Target Platform**: PawGuard Central Operations Network & Public Portal  
**Compliance**: PRR-PAWGUARD-2026-V1 & AGENTS.md Backend Constitution  

---

## 1. High-Level Design (HLD) - System Architecture

```
                  ┌─────────────────────────────────────────────────────────────┐
                  │                 CLIENT APPLICATION TIER                     │
                  │  (Public Web, Rescue Staff App, Executive App, Admin Portal)│
                  └──────────────────────────────┬──────────────────────────────┘
                                                 │ HTTPS / WSS
                                                 ▼
                  ┌─────────────────────────────────────────────────────────────┐
                  │             EDGE GATEWAY & SECURITY LAYER                   │
                  │  • Upstash Redis Sliding Window Rate Limiter (Token Bucket) │
                  │  • JWT Authentication & Revocation Guard                    │
                  │  • ETag Conditional Response Evaluator (HTTP 304)           │
                  └──────────────────────────────┬──────────────────────────────┘
                                                 │
                                                 ▼
                  ┌─────────────────────────────────────────────────────────────┐
                  │           FASTAPI DOMAIN APPLICATION SERVICES               │
                  │                                                             │
                  │  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐ │
                  │  │ Rescue Module│   │Adoption Mod  │   │ Volunteer Mod   │ │
                  │  └──────────────┘   └──────────────┘   └─────────────────┘ │
                  │  ┌──────────────┐   ┌──────────────┐   ┌─────────────────┐ │
                  │  │Medical Suite │   │Shelter Module│   │  Finance Module │ │
                  │  └──────────────┘   └──────────────┘   └─────────────────┘ │
                  └──────────────────────┬───────────────┬──────────────────────┘
                                         │               │
                    ACID Outbox Enqueue  │               │ Redis Pub/Sub & GEO
                                         ▼               ▼
                  ┌──────────────────────────────┐   ┌──────────────────────────┐
                  │  PostgreSQL Database (ACID)  │   │ Upstash Serverless Redis │
                  │  • Dog Profiles & History    │   │  • Geosearch Index       │
                  │  • Transactional Outbox      │   │  • Rate Limits & TTL     │
                  │  • Audit Snapshots (Diff)    │   │  • Active Officer Locks  │
                  └──────────────┬───────────────┘   └──────────────────────────┘
                                 │
                                 ▼
                  ┌──────────────────────────────┐
                  │   Async Outbox Worker Pool   │ ──► FCM Push / SendGrid Email
                  │       (arq_worker.py)        │
                  └──────────────────────────────┘
```

---

## 2. Low-Level Design (LLD) - Key Production Design Patterns

### Pattern 1: Optimistic Concurrency Control (OCC) - `version_id`
- **Class**: `AdoptionService` & `DogProfile`
- **Mechanism**:
  ```python
  if payload.version_id is not None and payload.version_id != app.version_id:
      raise ConflictError("Record modified concurrently by another user.")
  app.version_id += 1
  ```
- **SQL Execution**:
  ```sql
  UPDATE adoption_applications 
  SET status = 'home_inspection_approved', version_id = version_id + 1
  WHERE id = :id AND version_id = :expected_version;
  ```

### Pattern 2: GeoSpatial Nearest-Neighbor Rescue Officer Dispatch
- **Class**: `RescueService.get_nearest_agents`
- **Mechanism**:
  - Redis `GEOSEARCH` finds rescue agents within radius $R$ (in kilometers) sorted by ascending distance.
  - Verifies officer liveness heartbeat key `rescue:agent_active:{agent_id}`.
  - Merges real-time GPS coordinates with PostgreSQL user records.

### Pattern 3: Transactional Outbox Pattern
- **Class**: `OutboxService` & `arq_worker`
- **Mechanism**:
  - Business updates and `OutboxEvent` insertions commit in the **same atomic SQL transaction**.
  - `arq_worker` polls pending events every 2 seconds, executing external push notifications with exponential backoff retries.

### Pattern 4: ETag HTTP Conditional Evaluation
- **Utility**: `etag_cache_response` (`cache_utils.py`)
- **Mechanism**:
  - Computes SHA-256 signature $E = \text{SHA256}(JSON)$.
  - If `If-None-Match == E`, returns `HTTP 304 Not Modified` with 0-byte payload.
