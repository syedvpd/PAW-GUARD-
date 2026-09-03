"""Central registry of every permission code used across the platform.

Naming convention: ``<module>:<action>``

- module:  the domain (rescue, medical, shelter, …)
- action:  create, read, update, delete, approve, dispatch, …

Add new codes here as modules are built.  The seed script reads this file
so the set of roles and their permissions stays in one place.
"""

# ── System ──────────────────────────────────────────────────────────────────
SYSTEM_READ = "system:read"
SYSTEM_WRITE = "system:write"
SYSTEM_ADMIN = "system:admin"

# ── User / Role management ───────────────────────────────────────────────────
USER_READ = "user:read"
USER_CREATE = "user:create"
USER_UPDATE = "user:update"
USER_DELETE = "user:delete"
USER_ASSIGN_ROLE = "user:assign_role"

# ── Rescue ───────────────────────────────────────────────────────────────────
RESCUE_CREATE = "rescue:create"
RESCUE_READ = "rescue:read"
RESCUE_UPDATE = "rescue:update"
RESCUE_DELETE = "rescue:delete"
RESCUE_VERIFY = "rescue:verify"
RESCUE_DISPATCH = "rescue:dispatch"
RESCUE_EXECUTE = "rescue:execute"

# ── Vehicle / Fleet ──────────────────────────────────────────────────────────
VEHICLE_READ = "vehicle:read"
VEHICLE_ASSIGN = "vehicle:assign"
VEHICLE_UPDATE = "vehicle:update"

# ── Shelter / Facility ───────────────────────────────────────────────────────
SHELTER_READ = "shelter:read"
SHELTER_UPDATE = "shelter:update"
SHELTER_MANAGE_KENNELS = "shelter:manage_kennels"
SHELTER_TRANSFER = "shelter:transfer"

# ── Medical / Veterinary ─────────────────────────────────────────────────────
MEDICAL_CREATE = "medical:create"
MEDICAL_READ = "medical:read"
MEDICAL_UPDATE = "medical:update"
MEDICAL_CLEARANCE = "medical:clearance"
MEDICAL_DELETE = "medical:delete"
DOG_MEDICAL_UPDATE = "dog:medical_update"

# ── Adoption ─────────────────────────────────────────────────────────────────
ADOPTION_READ = "adoption:read"
ADOPTION_PROCESS = "adoption:process"
ADOPTION_APPROVE = "adoption:approve"
ADOPTION_LOCK = "adoption:lock"
ADOPTION_DELETE = "adoption:delete"

# ── Foster ───────────────────────────────────────────────────────────────────
FOSTER_CREATE = "foster:create"
FOSTER_READ = "foster:read"
FOSTER_UPDATE = "foster:update"
FOSTER_APPROVE = "foster:approve"
FOSTER_DELETE = "foster:delete"

# ── Volunteer ────────────────────────────────────────────────────────────────
VOLUNTEER_CREATE = "volunteer:create"
VOLUNTEER_READ = "volunteer:read"
VOLUNTEER_UPDATE = "volunteer:update"
VOLUNTEER_SCHEDULE = "volunteer:schedule"
VOLUNTEER_DELETE = "volunteer:delete"

# ── Inventory ────────────────────────────────────────────────────────────────
INVENTORY_CREATE = "inventory:create"
INVENTORY_READ = "inventory:read"
INVENTORY_UPDATE = "inventory:update"
INVENTORY_DELETE = "inventory:delete"
REQUISITION_CREATE = "requisition:create"

# ── Finance ──────────────────────────────────────────────────────────────────
FINANCE_READ = "finance:read"
FINANCE_CREATE = "finance:create"
FINANCE_RECONCILE = "finance:reconcile"
FINANCE_UPDATE = "finance:update"
FINANCE_DELETE = "finance:delete"
FINANCE_EXPORT = "finance:export"

# ── Reports ──────────────────────────────────────────────────────────────────
REPORTS_READ = "reports:read"
REPORTS_CREATE = "reports:create"
REPORTS_EXPORT_PDF = "reports:export_pdf"
REPORTS_EXPORT_CSV = "reports:export_csv"
REPORTS_EXPORT_EXCEL = "reports:export_excel"

# ── Role Dashboards ──────────────────────────────────────────────────────────
DASHBOARD_RESCUE = "dashboard:rescue"
DASHBOARD_SHELTER = "dashboard:shelter"
DASHBOARD_MEDICAL = "dashboard:medical"
DASHBOARD_ADOPTION = "dashboard:adoption"
DASHBOARD_FOSTER = "dashboard:foster"
DASHBOARD_VOLUNTEER = "dashboard:volunteer"
DASHBOARD_INVENTORY = "dashboard:inventory"
DASHBOARD_FINANCE = "dashboard:finance"
DASHBOARD_DONOR = "dashboard:donor"

# ── Donation / Sponsorship ───────────────────────────────────────────────────
DONATION_READ = "donation:read"
DONATION_MANAGE = "donation:manage"
DONATION_UPDATE = "donation:update"

# ── Public portal ────────────────────────────────────────────────────────────
PUBLIC_READ = "public:read"
PUBLIC_CREATE = "public:create"

# ── Audit ────────────────────────────────────────────────────────────────────
AUDIT_READ = "audit:read"

# ── Grievance ─────────────────────────────────────────────────────────────────
GRIEVANCE_CREATE = "grievance:create"
GRIEVANCE_READ = "grievance:read"
GRIEVANCE_UPDATE = "grievance:update"
GRIEVANCE_ASSIGN = "grievance:assign"
GRIEVANCE_COMMENT = "grievance:comment"

# ── Notifications ─────────────────────────────────────────────────────────────
NOTIFICATION_READ = "notification:read"
NOTIFICATION_VIEW = "notification:view"
NOTIFICATION_MANAGE = "notification:manage"
NOTIFICATION_APPROVE = "notification:approve"
NOTIFICATION_REJECT = "notification:reject"
NOTIFICATION_PAUSE = "notification:pause"
NOTIFICATION_RESUME = "notification:resume"
NOTIFICATION_AUDIT = "notification:audit"
NOTIFICATION_GLOBAL_CONTROL = "notification:global_control"

# ── Client-facing permission aliases (app vocabulary) ────────────────────────
# The Flutter/web clients gate UI actions on coarse action verbs
# (rescue:write, donations:write, complaints:write, notifications:write) that
# differ from the fine-grained backend codes. These aliases are granted to the
# same roles that hold the matching backend code (see seed_roles_and_permissions
# ROLE_DEFINITIONS) so both vocabularies stay in sync without churning every
# require_permission call site.
RESCUE_WRITE = "rescue:write"  # client alias for rescue:create/update/delete
DONATIONS_WRITE = "donations:write"  # client alias for donation:manage/update
COMPLAINTS_WRITE = "complaints:write"  # client alias for grievance:*
NOTIFICATIONS_WRITE = "notifications:write"  # client alias for notification:manage

# ── Lost & found ─────────────────────────────────────────────────────────────
LOST_FOUND_BROADCAST = "lost_found:broadcast"

# ── Companion pets / veterinary access ───────────────────────────────────────
COMPANION_PET_CREATE = "companion_pet:create"
COMPANION_PET_READ = "companion_pet:read"
COMPANION_PET_UPDATE = "companion_pet:update"
COMPANION_PET_DELETE = "companion_pet:delete"
COMPANION_PET_MEDICAL_UPLOAD = "companion_pet:medical_upload"
SAFETY_TAG_MANAGE = "safety_tag:manage"
VET_CLINIC_READ = "vet_clinic:read"
VET_CLINIC_MANAGE = "vet_clinic:manage"
APPOINTMENT_CREATE = "appointment:create"
APPOINTMENT_READ = "appointment:read"
APPOINTMENT_CANCEL = "appointment:cancel"
APPOINTMENT_MANAGE = "appointment:manage"
