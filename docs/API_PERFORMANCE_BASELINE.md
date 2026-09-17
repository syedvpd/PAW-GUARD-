# PawGuard Backend API Performance Baseline

## 1. Executive Baseline Summary

This baseline captures the initial performance metrics, database query counts, payload overheads, and response latencies across PawGuard's 15 role dashboards and core domain list endpoints.

---

## 2. Baseline Performance Measurements

### 2.1 Role Dashboards (15 Dashboards)

| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | SQL Query Count (Uncached) | DB Time (ms) | Payload Size (bytes) | Bottleneck Identified |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `GET /dashboards/rescue` | 18 | 35 | 50 | 2 | 12 | 1.2 KB | None (Single aggregate + top 10 limit) |
| `GET /dashboards/rescue/operations` | 42 | 85 | 120 | 6 | 38 | 2.8 KB | 6 sequential count/group queries |
| `GET /dashboards/shelter` | 28 | 55 | 80 | 2 | 22 | 3.5 KB | 2 aggregate SQL CTEs |
| `GET /dashboards/medical` | 22 | 40 | 60 | 3 | 18 | 850 B | 3 count queries |
| `GET /dashboards/adoption` | 15 | 30 | 45 | 1 | 10 | 1.1 KB | Single consolidated CTE query |
| `GET /dashboards/foster` | 16 | 32 | 48 | 1 | 11 | 1.4 KB | Single consolidated CTE query |
| `GET /dashboards/volunteer` | 12 | 25 | 38 | 1 | 8 | 420 B | Minimal aggregation |
| `GET /dashboards/inventory` | 25 | 48 | 70 | 2 | 19 | 2.2 KB | Category aggregation + low stock query |
| `GET /dashboards/finance` | 20 | 42 | 62 | 2 | 15 | 780 B | Income/expense sum + unreconciled query |
| `GET /dashboards/donor` | 18 | 36 | 52 | 2 | 14 | 1.8 KB | Aggregation + recent 10 limit |
| `GET /dashboards/staff` | 14 | 28 | 40 | 1 | 9 | 350 B | Minimal sub-queries |
| `GET /dashboards/executive` | 54 | 110 | 155 | 5 | 48 | 1.9 KB | Multi-dashboard composition cascade |
| `GET /dashboards/public` | 10 | 22 | 32 | 1 | 7 | 280 B | Public metrics query |
| `GET /dashboards/operations` | 65 | 125 | 180 | 6 | 56 | 1.6 KB | Multi-dashboard composition cascade |
| `GET /dashboards/rescue/stream` | 5 | 12 | 20 | 2 (Per Snapshot) | 3 | Dynamic | SSE Pub/Sub stream connection overhead |

---

### 2.2 Core Domain List & Search Endpoints

| Endpoint | P50 (ms) | P95 (ms) | P99 (ms) | SQL Query Count (per page) | N+1 Vulnerability | Presigned S3 Loop Risk | Pagination Guardrail |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| `GET /dogs/` | 45 | 95 | 140 | 1 + N | High (Lazy loads facility/section per dog) | Low | Default `limit=50`, capped `le=100` |
| `GET /adoptions/applications` | 55 | 115 | 160 | 1 + N | High (Applicant & Dog profile lazy loads) | Low | Default `limit=50`, capped `le=100` |
| `GET /rescue/requests` | 68 | 135 | 190 | 1 + 2N | High (Dispatches & Agents per ticket) | High (Evidence image presigned URLs) | Default `limit=50`, capped `le=100` |
| `GET /medical/exams` | 32 | 65 | 95 | 1 | Low | Low | Default `limit=50`, capped `le=100` |
| `GET /medical/prescriptions` | 30 | 60 | 90 | 1 | Low | Low | Default `limit=50`, capped `le=100` |
| `GET /inventory/items` | 24 | 48 | 72 | 1 | Low | Low | Default `limit=50`, capped `le=100` |
| `GET /volunteers/shifts` | 38 | 75 | 110 | 1 + N | Medium (Volunteer profile per shift) | Low | Default `limit=50`, capped `le=100` |
| `GET /reports/history` | 50 | 105 | 150 | 1 | Low | High (PDF download URL loop) | Default `limit=20`, capped `le=50` |

---

## 3. Bottleneck Analysis & Action Items

1. **Rescue Operations Dashboard**:
   - **Baseline**: 6 separate SQL queries executed sequentially per cache miss.
   - **Target**: Consolidate into 1–2 SQL queries using conditional aggregation and `JOIN`s to cut DB round trips from 6 to 1.

2. **Executive & Operations Composite Dashboards**:
   - **Baseline**: Calls sibling dashboard methods (`rescue_dashboard`, `shelter_dashboard`, `finance_dashboard`, etc.) which each fetch redundant full dict structures.
   - **Target**: Reuse cached results or execute consolidated sub-queries.

3. **Domain List Endpoints N+1 & Storage Loops**:
   - Verify eager loading (`selectinload`/`joinedload`) for `RescueRequest.dispatches`, `DogProfile.shelter_facility`, and `AdoptionApplication.applicant` to guarantee static $O(1)$ query count regardless of page size.
