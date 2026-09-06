"""Central domain model registry and declarative mapper configuration.

Imports all domain models across all modules so they register on `Base.metadata`,
and triggers `configure_mappers()` on startup so all cross-module foreign keys
and relationships (e.g. `ReportMedia` -> `rescue_requests`, `LostReport` -> `companion_pets`,
`RescueRequest` -> `DogProfile`, and `User`) are deterministically resolved and compiled.
"""

from sqlalchemy.orm import configure_mappers

# 6. Adoption, Foster, Volunteer
from pawguard.modules.adoption import models as adoption_models  # noqa: F401

# 1. Core Auth & Users
from pawguard.modules.auth import models as auth_models  # noqa: F401

# 2. Companion Pets & Tags
from pawguard.modules.companion_pet import models as companion_pet_models  # noqa: F401

# 3. Dog Management & Shelter
from pawguard.modules.dog import models as dog_models  # noqa: F401

# 8. Finance, Donation, Grievance
from pawguard.modules.donation import models as donation_models  # noqa: F401
from pawguard.modules.finance import models as finance_models  # noqa: F401
from pawguard.modules.fleet import models as fleet_models  # noqa: F401
from pawguard.modules.foster import models as foster_models  # noqa: F401
from pawguard.modules.grievance import models as grievance_models  # noqa: F401
from pawguard.modules.inventory import models as inventory_models  # noqa: F401

# 4. Lost & Found
from pawguard.modules.lost_found import models as lost_found_models  # noqa: F401

# 7. Medical, Inventory, Fleet
from pawguard.modules.medical import models as medical_models  # noqa: F401
from pawguard.modules.notifications import models as notification_models  # noqa: F401
from pawguard.modules.outbox import models as outbox_models  # noqa: F401

# 9. Portal, Notifications, Settings, Storage, Outbox
from pawguard.modules.portal import models as portal_models  # noqa: F401

# 5. Emergency Rescue
from pawguard.modules.rescue import models as rescue_models  # noqa: F401
from pawguard.modules.settings import models as settings_models  # noqa: F401
from pawguard.modules.shelter import models as shelter_models  # noqa: F401
from pawguard.modules.storage import models as storage_models  # noqa: F401
from pawguard.modules.volunteer import models as volunteer_models  # noqa: F401

# Eagerly compile and validate all mapper relationships across all registered tables
configure_mappers()
