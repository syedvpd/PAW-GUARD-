"""Unit tests for Settings persistence and CRUD operations."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from pawguard.core.security import AccessTokenClaims
from pawguard.main import app
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import Role, User
from pawguard.modules.settings.models import BusinessRule, PasswordPolicy
from pawguard.modules.settings.router import (
    get_business_rule_service,
    get_password_policy_service,
    get_setting_service,
)
from pawguard.modules.settings.schemas import (
    EmailSettingsResponse,
    GeneralSettingsResponse,
)
from pawguard.modules.settings.service import (
    BusinessRuleService,
    PasswordPolicyService,
    SystemSettingService,
)


@pytest.fixture
def mock_admin_user():
    user = User(
        id=uuid.uuid4(),
        email="admin@pawguard.org",
        full_name="Super Admin",
        is_active=True,
        is_verified=True,
    )
    role = Role(id=uuid.uuid4(), name="super_admin")
    user.roles = [role]
    claims = AccessTokenClaims(
        user_id=user.id,
        session_id=uuid.uuid4(),
        roles=["super_admin"],
        jti="test_jti",
        expires_at=datetime.now(UTC),
    )
    return CurrentUser(user=user, claims=claims, db=MagicMock(), redis=MagicMock())


@pytest.mark.asyncio
async def test_get_and_put_general_settings(mock_admin_user):
    mock_service = AsyncMock(spec=SystemSettingService)
    mock_service.get_general_settings.return_value = GeneralSettingsResponse(
        app_name="PawGuard",
        environment="production",
        debug=False,
        allowed_hosts="localhost",
        cors_origins="*",
        web_app_url="http://localhost:3000",
        admin_app_url="http://localhost:5173",
        mobile_deep_link_base="pawguard://",
    )
    mock_service.update_general_settings.return_value = {
        "app_name": "PawGuard Rescue Network",
        "environment": "production",
    }

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_setting_service] = lambda: mock_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            headers = {"Authorization": "Bearer mock_token"}

            # GET /api/v1/settings/general
            r_get = await client.get("/api/v1/settings/general", headers=headers)
            assert r_get.status_code == 200
            assert r_get.json()["data"]["app_name"] == "PawGuard"

            # PUT /api/v1/settings/general
            r_put = await client.put(
                "/api/v1/settings/general",
                headers=headers,
                json={"app_name": "PawGuard Rescue Network", "environment": "production"},
            )
            assert r_put.status_code == 200
            assert r_put.json()["data"]["app_name"] == "PawGuard Rescue Network"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_setting_service, None)


@pytest.mark.asyncio
async def test_get_and_put_password_policy(mock_admin_user):
    mock_policy = PasswordPolicy(
        id=uuid.uuid4(),
        min_length=12,
        require_uppercase=True,
        require_lowercase=True,
        require_digit=True,
        require_special_char=True,
        max_age_days=90,
        password_history_count=5,
        max_login_attempts=5,
        lockout_duration_minutes=15,
        is_active=True,
        updated_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    mock_service = AsyncMock(spec=PasswordPolicyService)
    mock_service.get_active.return_value = mock_policy
    mock_service.update_policy.return_value = mock_policy

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_password_policy_service] = lambda: mock_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            headers = {"Authorization": "Bearer mock_token"}

            # GET /api/v1/settings/password-policy
            r_get = await client.get("/api/v1/settings/password-policy", headers=headers)
            assert r_get.status_code == 200
            assert r_get.json()["data"]["min_length"] == 12

            # PUT /api/v1/settings/password-policy
            r_put = await client.put(
                "/api/v1/settings/password-policy",
                headers=headers,
                json={"min_length": 12, "require_special": True},
            )
            assert r_put.status_code == 200
            assert r_put.json()["data"]["min_length"] == 12
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_password_policy_service, None)


@pytest.mark.asyncio
async def test_get_and_put_business_rule(mock_admin_user):
    mock_rule = BusinessRule(
        id=uuid.uuid4(),
        rule_key="adoption_fee_waiver",
        rule_value="enabled",
        description="Fee waiver for senior dogs",
        module="general",
        is_active=True,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_service = AsyncMock(spec=BusinessRuleService)
    mock_service.get_rule.return_value = mock_rule
    mock_service.update_rule.return_value = mock_rule

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_business_rule_service] = lambda: mock_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            headers = {"Authorization": "Bearer mock_token"}

            # GET /api/v1/settings/business-rules/{rule_key}
            r_get = await client.get(
                "/api/v1/settings/business-rules/adoption_fee_waiver",
                headers=headers,
            )
            assert r_get.status_code == 200
            assert r_get.json()["data"]["rule_value"] == "enabled"

            # PUT /api/v1/settings/business-rules/{rule_key}
            r_put = await client.put(
                "/api/v1/settings/business-rules/adoption_fee_waiver",
                headers=headers,
                json={"rule_value": "enabled", "description": "Fee waiver for senior dogs"},
            )
            assert r_put.status_code == 200
            assert r_put.json()["data"]["rule_value"] == "enabled"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_business_rule_service, None)


@pytest.mark.asyncio
async def test_get_and_put_email_settings(mock_admin_user):
    mock_service = AsyncMock(spec=SystemSettingService)
    mock_service.get_email_settings.return_value = EmailSettingsResponse(
        mail_from="notifications@pawguard.org",
        mail_host="smtp.sendgrid.net",
        mail_port=587,
        mail_use_tls=True,
    )
    mock_service.update_email_settings.return_value = EmailSettingsResponse(
        mail_from="notifications@pawguard.org",
        mail_host="smtp.sendgrid.net",
        mail_port=587,
        mail_use_tls=True,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_admin_user
    app.dependency_overrides[get_setting_service] = lambda: mock_service

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://localhost:8000") as client:
            headers = {"Authorization": "Bearer mock_token"}

            # GET /api/v1/settings/email
            r_get = await client.get("/api/v1/settings/email", headers=headers)
            assert r_get.status_code == 200
            assert r_get.json()["data"]["mail_from"] == "notifications@pawguard.org"

            # PUT /api/v1/settings/email
            r_put = await client.put(
                "/api/v1/settings/email",
                headers=headers,
                json={
                    "mail_from": "notifications@pawguard.org",
                    "mail_host": "smtp.sendgrid.net",
                    "mail_port": 587,
                    "mail_use_tls": True,
                },
            )
            assert r_put.status_code == 200
            assert r_put.json()["data"]["mail_port"] == 587
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_setting_service, None)
