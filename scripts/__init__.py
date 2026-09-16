"""PawGuard operational and utility scripts package."""

import sys

from scripts.seed import seed_dogs, seed_roles_and_permissions

# Backward-compatibility module aliases for legacy import paths
sys.modules["scripts.seed_roles_and_permissions"] = seed_roles_and_permissions
sys.modules["scripts.seed_dogs"] = seed_dogs

__all__ = [
    "seed_roles_and_permissions",
    "seed_dogs",
]
