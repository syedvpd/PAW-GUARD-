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

# ── Adoption ─────────────────────────────────────────────────────────────────
ADOPTION_READ = "adoption:read"
ADOPTION_PROCESS = "adoption:process"
ADOPTION_APPROVE = "adoption:approve"
ADOPTION_LOCK = "adoption:lock"

# ── Foster ───────────────────────────────────────────────────────────────────
FOSTER_CREATE = "foster:create"
FOSTER_READ = "foster:read"
FOSTER_UPDATE = "foster:update"
FOSTER_APPROVE = "foster:approve"

# ── Volunteer ────────────────────────────────────────────────────────────────
VOLUNTEER_CREATE = "volunteer:create"
VOLUNTEER_READ = "volunteer:read"
VOLUNTEER_UPDATE = "volunteer:update"
VOLUNTEER_SCHEDULE = "volunteer:schedule"

# ── Inventory ────────────────────────────────────────────────────────────────
INVENTORY_CREATE = "inventory:create"
INVENTORY_READ = "inventory:read"
INVENTORY_UPDATE = "inventory:update"
INVENTORY_DELETE = "inventory:delete"

# ── Finance ──────────────────────────────────────────────────────────────────
FINANCE_READ = "finance:read"
FINANCE_CREATE = "finance:create"
FINANCE_RECONCILE = "finance:reconcile"

# ── Donation / Sponsorship ───────────────────────────────────────────────────
DONATION_READ = "donation:read"
DONATION_MANAGE = "donation:manage"

# ── Public portal ────────────────────────────────────────────────────────────
PUBLIC_READ = "public:read"
PUBLIC_CREATE = "public:create"

# ── Audit ────────────────────────────────────────────────────────────────────
AUDIT_READ = "audit:read"
