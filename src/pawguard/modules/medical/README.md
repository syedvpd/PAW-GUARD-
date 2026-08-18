# Medical Module

Clinical examinations, treatments, vaccinations, prescriptions, medication administration, and adoption medical clearance.

---

## Architecture

```
medical/
  router.py          # 21 endpoints
  service.py         # MedicalService (exams, treatments, clearances)
  repository.py      # Data access
  models.py          # ORM models
  schemas.py         # Pydantic DTOs
```

## Models

| Model | Table | Purpose |
|-------|-------|---------|
| `ClinicalExam` | `clinical_exams` | Intake/periodic exam: body condition (1-9), dental, ocular, coat, injuries |
| `MedicalTreatment` | `medical_treatments` | Treatment/surgery record. **Auto-sets dog.status=CLINIC** |
| `VaccinationRecord` | `vaccination_records` | Vaccination with auto-scheduled next dose |
| `Prescription` | `prescriptions` | Medication prescription. Consumes inventory |
| `MedicationAdministrationLog` | `medication_administration_logs` | Nurse sign-off per dose |
| `VaccineProtocol` | `vaccine_protocols` | Drives auto-scheduling (name, interval_days, is_required) |
| `MedicalClearance` | `medical_clearances` | **Vet-only** adoption clearance. Sets is_adoptable |

## Endpoints

| Method | Path | Permission | Description |
|--------|------|------------|-------------|
| POST | `/medical/exams` | `medical:create` | Log clinical exam |
| POST | `/medical/treatments` | `medical:create` | Log treatment (sets dog=CLINIC, consumes inventory) |
| POST | `/medical/vaccinations` | `medical:create` | Administer vaccine (auto-schedules next dose) |
| POST | `/medical/prescriptions` | `medical:create` | Create prescription (consumes inventory) |
| POST | `/medical/clearance/{dog_id}` | `medical:clearance` | **Vet-only** adoption clearance |
| GET | `/medical/clearances/dogs/{dog_id}` | `medical:read` | List clearance records |
| POST | `/medical/administrations` | `medical:update` | Nurse sign-off on medication |
| GET | `/medical/prescriptions/{id}/administrations` | `medical:read` | Administrations for prescription |
| GET | `/medical/dogs/{id}/administrations` | `medical:read` | Administrations for dog |
| POST | `/medical/vaccine-protocols` | `medical:update` | Create protocol (unique name) |
| GET | `/medical/vaccine-protocols` | `medical:read` | List protocols |
| GET | `/medical/dogs/{id}/history` | `medical:read` | Full medical history |
| GET | `/medical/exams` | `medical:read` | Paginated exam list |
| GET | `/medical/treatments` | `medical:read` | Paginated treatment list |
| GET | `/medical/vaccinations` | `medical:read` | Paginated vaccination list |
| GET | `/medical/prescriptions` | `medical:read` | Paginated prescription list |
| PUT | `/medical/prescriptions/{id}` | `medical:update` | Update prescription |
| PATCH | `/medical/prescriptions/{id}/status` | `medical:update` | Toggle active/inactive |
| DELETE | `/medical/{type}/{id}` | `medical:delete` | Soft delete any entity |
| POST | `/medical/bulk/prescriptions/status` | `medical:update` | Bulk toggle status |
| POST | `/medical/bulk/delete` | `medical:delete` | Bulk soft delete |

## Key Flows

### Treatment (with Dog Status Side-Effect)
```
POST /medical/treatments {dog_id, treatment_type, description, inventory_consumptions?}
  -> Validate dog exists
  -> Create MedicalTreatment
  -> SET dog.status = CLINIC (auto)
  -> For each inventory_consumption:
     -> InventoryService.record_movement(CHECK_OUT, reference_type="medical_treatment")
  -> Audit: MEDICAL_RECORD_CREATED
```

### Vaccination (with Auto-Scheduling)
```
POST /medical/vaccinations {dog_id, vaccine_name, ...}
  -> Create VaccinationRecord (administered_at = now)
  -> Lookup VaccineProtocol by normalised name
  -> If protocol exists:
     -> next_due = administered_at + protocol.interval_days
     -> Create placeholder VaccinationRecord for next dose
  -> Audit: VACCINATION_RECORDED
```

### Medical Clearance (Vet-Only)
```
POST /medical/clearance/{dog_id} {status: "approved", ...}
  -> Validate caller has "veterinarian" role (raises FORBIDDEN if not)
  -> Create MedicalClearance record
  -> If approved:
     -> dog.is_adoptable = True
     -> dog.is_quarantine_passed = True
     -> dog.status = SHELTER
  -> Audit: MEDICAL_RECORD_UPDATED
```

### Inventory Consumption
Both treatments and prescriptions can consume inventory:
- Each item: `{item_id, quantity}`
- Creates `CHECK_OUT` movement with `reference_type` + `reference_id`
- Triggers expiry enforcement, stock validation, low-stock alerts

## Cross-Module Interactions

| Trigger | Target | Effect |
|---------|--------|--------|
| `record_treatment()` | Dog | Sets `dog.status = CLINIC` |
| `authorize_adoption_clearance()` (approved) | Dog | Sets `is_adoptable=True`, `status=SHELTER` |
| Treatment/Prescription creation | Inventory | `CHECK_OUT` movements for consumed items |
| `administer_vaccine()` | VaccinationRecord | Auto-creates next dose placeholder |
