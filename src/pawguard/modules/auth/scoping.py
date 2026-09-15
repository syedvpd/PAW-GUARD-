"""Facility/zone scoping for location-bound roles (PRR §2.1, §6.1).

PRR §2.1 gives every role except Super Administrator "full operational
read/write access, but SCOPED to assigned shelter locations and rescue
zones only". This module derives that scope from the *authenticated user*
so callers never trust a client-supplied filter.
"""

from __future__ import annotations

import uuid

from pawguard.core.logging import get_logger
from pawguard.modules.auth.models import User

logger = get_logger(__name__)

# Roles whose data access is bound to their assigned facility. super_admin is
# deliberately absent: it is the one globally-unrestricted role per PRR §2.1.
FACILITY_SCOPED_ROLE_NAMES = frozenset({"rescue_centre_admin", "shelter_manager"})


def facility_scope_for(user: User | None) -> list[uuid.UUID] | None:
    """Facility ids this user's queries must be limited to.

    Returns None when no filter should be applied — either the caller is
    unrestricted (super_admin, or a role that isn't facility-bound), or the
    caller IS facility-bound but has no facility assigned yet.

    That last case is a deliberate fail-OPEN: seeded admin accounts ship
    with `managed_facility_id` NULL, so failing closed would blank the app
    for every existing Rescue Centre Admin the moment this deploys. It is
    logged at warning level on every request so the gap is visible and the
    assignment backfill can be tracked — once facilities are assigned the
    scope applies automatically, with no code change.
    """
    if user is None:
        return None

    role_names = {role.name for role in user.roles}
    if not (role_names & FACILITY_SCOPED_ROLE_NAMES):
        return None

    facility_ids = user.managed_facility_ids
    if not facility_ids:
        logger.warning(
            "facility_scope_unassigned",
            user_id=str(user.id),
            roles=sorted(role_names),
            detail=(
                "Facility-scoped role has no managed facility assigned; "
                "serving UNSCOPED results (PRR 2.1 fail-open). Assign a "
                "facility to this account to enforce scoping."
            ),
        )
        return None

    return facility_ids
