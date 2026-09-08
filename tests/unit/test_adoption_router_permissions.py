"""Regression test for the adoption delete endpoints' permission wiring.

DELETE /adoptions/{app_id}, DELETE /adoptions/admin/adoptions/{app_id}, and
POST /adoptions/bulk/delete previously required only `adoption:process` —
the same permission Adoption Coordinator holds for routine pipeline work —
so a Coordinator could delete applications even though the workflow doc's
RBAC matrix (docs/workflow/08-adoption.md §16) reserves delete for Centre
Admin and Super Admin. They now require `adoption:delete`, a permission
that was already seeded for rescue_centre_admin (and bypassed entirely by
super_admin's admin override) but never actually enforced anywhere.

This test inspects the router's dependency wiring directly rather than
exercising the endpoints over HTTP, so it doesn't depend on the auth/MFA
session flow that other integration tests use.
"""

from pawguard.modules.adoption.router import router
from pawguard.modules.auth.rbac import RequirePermission


def _required_codes(path: str, method: str) -> tuple[str, ...] | None:
    for route in router.routes:
        if route.path == path and method in getattr(route, "methods", set()):
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, RequirePermission):
                    return dep.call.permission_codes
    raise AssertionError(f"No route found for {method} {path}")


class TestAdoptionDeleteRouterPermissions:
    def test_single_delete_requires_adoption_delete(self):
        assert _required_codes("/adoptions/{app_id}", "DELETE") == ("adoption:delete",)

    def test_admin_alias_delete_requires_adoption_delete(self):
        assert _required_codes("/adoptions/admin/adoptions/{app_id}", "DELETE") == (
            "adoption:delete",
        )

    def test_bulk_delete_requires_adoption_delete(self):
        assert _required_codes("/adoptions/bulk/delete", "POST") == ("adoption:delete",)

    def test_bulk_status_update_still_only_requires_adoption_process(self):
        """Status updates (the actual identified gap this session) remain on
        the broader `adoption:process` permission Coordinator holds — only
        delete was tightened."""
        assert _required_codes("/adoptions/bulk/status-update", "POST") == ("adoption:process",)
