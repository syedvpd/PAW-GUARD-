# Dashboards Module

Aggregated analytics dashboards for all operational roles — rescue, shelter, medical, adoption, foster, volunteer, inventory, finance, donor, staff, and executive.

---

## Architecture

```
dashboards/
  router.py          # 14 endpoints
  service.py         # Dashboard aggregation functions (dasvc)
  dashboard_repository.py  # Cross-module queries
```

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| GET | `/dashboards/rescue` | `dashboard:rescue` | Rescue operations dashboard |
| GET | `/dashboards/rescue/stream` | `dashboard:rescue` | **SSE live stream** (Redis Pub/Sub) |
| GET | `/dashboards/shelter` | `dashboard:shelter` | Shelter occupancy |
| GET | `/dashboards/medical` | `dashboard:medical` | Medical operations |
| GET | `/dashboards/adoption` | `dashboard:adoption` | Adoption pipeline |
| GET | `/dashboards/foster` | `dashboard:foster` | Foster operations |
| GET | `/dashboards/volunteer` | `dashboard:volunteer` | Volunteer hours |
| GET | `/dashboards/inventory` | `dashboard:inventory` | Stock levels |
| GET | `/dashboards/finance` | `dashboard:finance` | Financial overview |
| GET | `/dashboards/donor` | `dashboard:donor` | Donor dashboard |
| GET | `/dashboards/staff` | `system:admin` | Staff management |
| GET | `/dashboards/executive` | `system:admin` | Executive summary |
| GET | `/dashboards/public` | Public | Public statistics |
| GET | `/dashboards/operations` | `system:admin` | Operations overview |

## SSE Live Rescue Dashboard

```
GET /dashboards/rescue/stream
  -> SSE connection established
  -> Subscribes to Redis channel "dispatch:events"
  -> Rescue module publishes "updated" on every status change
  -> Client receives real-time snapshot updates
```

## Dashboard Data Sources

| Dashboard | Modules Queried |
|-----------|----------------|
| Rescue | RescueRequest, RescueDispatch (status counts, SLA) |
| Shelter | ShelterFacility, Kennel, DogProfile (occupancy) |
| Medical | ClinicalExam, MedicalTreatment, VaccinationRecord |
| Adoption | AdoptionApplication (pipeline counts, approval rate) |
| Foster | FosterProfile, FosterPlacement (active placements, capacity) |
| Volunteer | VolunteerProfile, ShiftAttendance (hours, attendance) |
| Inventory | InventoryItem (stock levels, low stock, expiring) |
| Finance | FinancialTransaction, ChartOfAccounts (income, expenses) |
| Donor | Donation, DonorProfile (total raised, donor count) |
| Executive | All modules (high-level KPIs) |

## Caching

All dashboards use Redis caching via `CacheService`:
- Keys: `cache:dashboard:{type}`
- TTL: configurable
- Invalidated on relevant mutations in each module
