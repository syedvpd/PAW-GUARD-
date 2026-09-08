"""Regression test for the volunteer delete endpoints' permission wiring.

DELETE /volunteers/{profile_id} and POST /volunteers/bulk/delete previously
required only `volunteer:update` — the same permission Volunteer Coordinator
holds for routine profile management — so a Coordinator could delete
volunteer profiles even though the seed data (scripts/seed_roles_and_permissions.py)
only grants `volunteer:delete` to rescue_centre_admin, not volunteer_coordinator.
They now require `volunteer:delete`.

This test inspects the router's dependency wiring directly rather than
exercising the endpoints over HTTP, so it doesn't depend on the auth/MFA
session flow that other integration tests use.
"""

from pawguard.modules.auth.rbac import RequirePermission
from pawguard.modules.volunteer.router import router


def _required_codes(path: str, method: str) -> tuple[str, ...] | None:
    for route in router.routes:
        if route.path == path and method in getattr(route, "methods", set()):
            for dep in route.dependant.dependencies:
                if isinstance(dep.call, RequirePermission):
                    return dep.call.permission_codes
    raise AssertionError(f"No route found for {method} {path}")


class TestVolunteerDeleteRouterPermissions:
    def test_single_delete_requires_volunteer_delete(self):
        assert _required_codes("/volunteers/{profile_id}", "DELETE") == ("volunteer:delete",)

    def test_bulk_delete_requires_volunteer_delete(self):
        assert _required_codes("/volunteers/bulk/delete", "POST") == ("volunteer:delete",)

    def test_update_profile_still_only_requires_volunteer_update(self):
        assert _required_codes("/volunteers/{profile_id}", "PUT") == ("volunteer:update",)

    def test_bulk_status_update_still_only_requires_volunteer_update(self):
        assert _required_codes("/volunteers/bulk/status", "POST") == ("volunteer:update",)


class TestVolunteerRosterRouterPermissions:
    """Regression test for the volunteer/application/attendance roster
    endpoints' permission wiring.

    All three previously required only `volunteer:read` - a permission also
    granted to the self-service `volunteer` role (scripts/seed_roles_and_permissions.py
    grants it VOLUNTEER_READ so it can... do nothing with it, since every
    actual self-service action either has no permission dependency at all or
    is gated by an is-owner-or-volunteer:update check). That meant any
    onboarded volunteer could call these staff-only roster endpoints and read
    every other volunteer's PII (emergency contacts, medical conditions,
    skills). They now require `volunteer:update`, which only staff roles
    (Volunteer Coordinator, Rescue Centre Admin, Super Admin) hold.
    """

    def test_list_profiles_requires_volunteer_update(self):
        assert _required_codes("/volunteers", "GET") == ("volunteer:update",)

    def test_list_applications_requires_volunteer_update(self):
        assert _required_codes("/volunteers/applications", "GET") == ("volunteer:update",)

    def test_list_shift_attendance_requires_volunteer_update(self):
        assert _required_codes("/volunteers/shifts/{shift_id}/attendance", "GET") == (
            "volunteer:update",
        )
