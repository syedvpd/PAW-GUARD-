"""Unit tests for facility/zone scoping (PRR §2.1, §6.1).

Covers `facility_scope_for`, which derives a caller's allowed facilities
from the authenticated user so no client-supplied parameter can widen its
own visibility.
"""

import uuid

from pawguard.modules.auth.models import Role, User
from pawguard.modules.auth.scoping import facility_scope_for


def _user(role_name: str | None, facility_id: uuid.UUID | None = None) -> User:
    user = User(
        email="user@example.com",
        hashed_password="x",
        full_name="Test User",
        is_active=True,
        managed_facility_id=facility_id,
    )
    user.id = uuid.uuid4()
    user.roles = [Role(name=role_name, is_system=True)] if role_name else []
    return user


class TestFacilityScope:
    def test_super_admin_is_unscoped(self):
        """PRR §2.1: Super Administrator is the one globally-unrestricted
        role - it must never be narrowed to a facility."""
        assert facility_scope_for(_user("super_admin", uuid.uuid4())) is None

    def test_rescue_centre_admin_scoped_to_assigned_facility(self):
        facility_id = uuid.uuid4()

        assert facility_scope_for(_user("rescue_centre_admin", facility_id)) == [facility_id]

    def test_shelter_manager_scoped_to_assigned_facility(self):
        facility_id = uuid.uuid4()

        assert facility_scope_for(_user("shelter_manager", facility_id)) == [facility_id]

    def test_unassigned_scoped_role_fails_open(self):
        """Deliberate fail-OPEN: seeded admins ship with no facility, so
        failing closed would blank the app for every existing Rescue Centre
        Admin on deploy. Scoping starts applying the moment a facility is
        assigned - see the warning logged on this path."""
        assert facility_scope_for(_user("rescue_centre_admin", None)) is None

    def test_non_facility_bound_role_is_unscoped(self):
        assert facility_scope_for(_user("veterinarian", uuid.uuid4())) is None

    def test_anonymous_caller_is_unscoped(self):
        assert facility_scope_for(None) is None


class TestApprovalAuditCompleteness:
    """PRR §6.1 requires approvals and escalations to carry Pre/Post State
    Data, not just an action code. This scans the source rather than testing
    one call site, because the failure mode is a NEW approval/escalation
    handler being added later without state capture - which no per-handler
    test would catch."""

    # Supply dispatch is logistics, not an approval or escalation; it only
    # matches the scan because of the substring "DISPATCH".
    KNOWN_EXEMPT = {"FOSTER_SUPPLY_DISPATCHED"}
    APPROVAL_KEYS = (
        "APPROV",
        "REJECT",
        "ESCALAT",
        "OVERRIDE",
        "REVERS",
        "ASSIGN",
        "DISPATCH",
        "ROLE_",
    )

    def test_every_approval_or_escalation_audit_records_pre_post_state(self):
        import pathlib
        import re

        root = pathlib.Path(__file__).resolve().parents[2] / "src" / "pawguard"
        offenders: list[str] = []

        for path in root.rglob("*.py"):
            src = path.read_text(encoding="utf-8")
            for match in re.finditer(r"_audit\.record\(", src):
                idx, depth = match.end(), 1
                while idx < len(src) and depth:
                    if src[idx] == "(":
                        depth += 1
                    elif src[idx] == ")":
                        depth -= 1
                    idx += 1
                call = src[match.end() : idx]
                event = re.search(r"event_type=AuthAuditEventType\.(\w+)", call)
                if event is None:
                    continue
                name = event.group(1)
                if name in self.KNOWN_EXEMPT:
                    continue
                if not any(key in name for key in self.APPROVAL_KEYS):
                    continue
                if "before_state" not in call and "after_state" not in call:
                    offenders.append(f"{name} in {path.name}")

        assert not offenders, (
            "These approval/escalation audit records omit PRR §6.1 Pre/Post "
            f"State Data: {sorted(set(offenders))}"
        )


class TestMandatoryMfaRoles:
    def test_rescue_coordinator_requires_mfa(self):
        """Mirrors the admin client's _mfaMandatoryRoles. A coordinator holds
        dispatch authority over live rescues and sees unmasked reporter PII,
        so it is an administrative account for PRR §6.1 session governance
        even though it is not an admin for authorization."""
        from pawguard.modules.auth.service import MFA_MANDATORY_ROLE_NAMES, AuthService

        assert "rescue_coordinator" in MFA_MANDATORY_ROLE_NAMES
        assert AuthService._is_admin(_user("rescue_coordinator")) is True

    def test_ordinary_role_does_not_require_mfa(self):
        from pawguard.modules.auth.service import AuthService

        assert AuthService._is_admin(_user("volunteer")) is False
