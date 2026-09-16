# PawGuard Platform — Administrative Governance Manual

**Document ID:** PG-MAN-GOV-2026-v1.0  
**Target Roles:** Super Administrators, Rescue Centre Administrators, Compliance Officers, and IT Security Auditors  
**Backend Target API:** `https://pawguard-backend-mqri.onrender.com/api/v1`  
**Classification:** OFFICIAL CONTRACTUAL ADMINISTRATIVE GOVERNANCE MANUAL  

---

## 1. Governance Architecture & Scope

This manual outlines administrative protocols for the PawGuard platform, covering:
1. System Initial Setup & Tenant Scoping
2. User Provisioning & Identity Lifecycle
3. Multi-Role RBAC Configuration & Granular Permission Codes
4. Immutable Audit Trail Inspection & Compliance Logging
5. Security Throttling, Rate Limits & MFA Enforcement

---

## 2. System Initial Setup & Centre Provisioning

PawGuard enforces multi-centre tenancy where operational data is scoped by Rescue Centre (`rescue_centres`) and Shelter Facility (`shelter_facilities`).

### 2.1 Provisioning a Rescue Centre
- **Endpoint:** `POST /api/v1/rescue-centres`
- **Authorized Role:** `super_admin` (`Depends(require_permission("system:manage"))`)
- **Payload:**
  ```json
  {
    "name": "City Central Animal Welfare Centre",
    "code": "CC-AWC-01",
    "address_line": "100 Rescue Way",
    "city": "Bengaluru",
    "state": "Karnataka",
    "country": "India",
    "postal_code": "560001",
    "contact_email": "ops@citycentralrescue.org",
    "contact_phone": "+919876543210",
    "latitude": 12.971598,
    "longitude": 77.594566,
    "is_active": true
  }
  ```

### 2.2 Provisioning a Shelter Facility & Sections
- **Endpoint:** `POST /api/v1/shelter/facilities`
- **Authorized Role:** `super_admin`, `rescue_centre_admin`
- **Payload:**
  ```json
  {
    "name": "Main Quarantine & Recovery Facility",
    "rescue_centre_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "total_capacity": 150,
    "quarantine_capacity": 30,
    "isolation_capacity": 20
  }
  ```

---

## 3. User Provisioning & Role Configuration

The system implements 15 standard seeded roles, mapped across operational domains.

### 3.1 15-Role RBAC Matrix

| Role ID | Role Name | System Scope | Core Granular Permissions |
| :---: | :--- | :--- | :--- |
| **1** | `super_admin` | Global System-wide | `system:manage`, `audit:read`, `users:manage`, `finance:override`, `shelter:admin` |
| **2** | `rescue_centre_admin` | Centre-scoped | `centre:manage`, `staff:manage`, `fleet:manage`, `shelter:admin` |
| **3** | `rescue_coordinator` | Operational Dispatch | `rescue:dispatch`, `rescue:update`, `rescue:read`, `fleet:assign` |
| **4** | `rescue_agent` | Mobile Field Response | `rescue:respond`, `rescue:update`, `media:upload` |
| **5** | `veterinarian` | Medical Bay / Clinic | `medical:diagnose`, `medical:prescribe`, `medical:clearance`, `tag:provision` |
| **6** | `shelter_manager` | Shelter & Kennel Ops | `shelter:manage`, `kennel:allocate`, `inventory:manage`, `dog:register` |
| **7** | `adoption_coordinator` | Adoption Lifecycle | `adoption:vetting`, `adoption:exclusivity_lock`, `adoption:contract` |
| **8** | `foster_coordinator` | Foster Lifecycle | `foster:vetting`, `foster:placement`, `foster:checkin` |
| **9** | `volunteer_coordinator` | Volunteer Roster | `volunteer:schedule`, `volunteer:verify_hours`, `volunteer:assign` |
| **10** | `inventory_manager` | Stock & Supply Chain | `inventory:purchase_order`, `inventory:stock_adjust`, `inventory:audit` |
| **11** | `finance_user` | Financial Ledger | `finance:read`, `finance:invoice`, `donation:receipt_80g`, `expense:log` |
| **12** | `volunteer` | Self Service | `volunteer:self_shifts`, `volunteer:check_in`, `volunteer:log_hours` |
| **13** | `foster_family` | Self / Assigned Dog | `foster:my_dogs`, `foster:daily_log`, `foster:vet_request` |
| **14** | `donor` | Self Service | `donation:my_donations`, `donation:download_receipt` |
| **15** | `general_public` | Public Catalog | `rescue:report`, `adoption:apply`, `tag:scan_public`, `lost_found:report` |

### 3.2 Staff User Provisioning
- **Endpoint:** `POST /api/v1/users`
- **Authorized Role:** `super_admin`, `rescue_centre_admin`
- **Payload:**
  ```json
  {
    "email": "dr.smith@pawguard.com",
    "full_name": "Dr. Sarah Smith",
    "password": "InitialSecureP@ssw0rd!2026",
    "phone": "+919876543211",
    "roles": ["veterinarian"],
    "rescue_centre_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6"
  }
  ```

---

## 4. Audit Log Inspection & Compliance Procedures

Every state mutation, login, permission check failure, or role change is recorded to the immutable `auth_audit_logs` table.

### 4.1 Querying Audit Logs
- **Endpoint:** `GET /api/v1/audit` (or alias `GET /api/v1/admin/audit-logs`)
- **Authorized Role:** `super_admin` (`require_permission("audit:read")`)
- **Query Parameters:**
  - `actor_id`: Filter by initiating user UUID
  - `event_type`: Filter by event (`login_success`, `login_failed`, `role_assigned`, `adoption_locked`, etc.)
  - `from_date` / `to_date`: ISO 8601 timestamps
  - `page` & `page_size`: Pagination parameters
- **Audit Row Structure:**
  ```json
  {
    "id": "1fa85f64-5717-4562-b3fc-2c963f66afa0",
    "actor_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "event_type": "ADOPTION_APPLICATION_STATUS_CHANGED",
    "ip_address": "203.0.113.195",
    "user_agent": "PawGuard-AdminPortal/2.0 (Windows NT 10.0; Win64; x64)",
    "timestamp": "2026-09-16T08:30:00Z",
    "metadata": {
      "application_id": "7ca85f64-5717-4562-b3fc-2c963f66afa7",
      "dog_id": "8da85f64-5717-4562-b3fc-2c963f66afa8",
      "old_status": "submitted",
      "new_status": "home_check",
      "exclusivity_lock": "ACQUIRED"
    }
  }
  ```

---

## 5. Security Policies & Administrative Controls

1. **Mandatory MFA for Administrators:**
   - Enforced by `mfa_mandatory_for_admins = True` setting. All admin accounts must enroll in TOTP/authenticator before full portal access is granted.
2. **Brute Force Protection & Rate Limiting:**
   - Login rate limit: 10 requests per minute per IP.
   - Account lockout: 5 consecutive failed login attempts locks the account for 15 minutes (`locked_until`).
3. **Password Complexity:**
   - Minimum 8 characters, requiring uppercase, lowercase, numeric digit, and special character.

---
*End of Administrative Governance Manual.*
