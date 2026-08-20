"""SettingsService: owns configuration business behaviour (RULE-003)."""

import uuid
from typing import Any

from pawguard.core.config import get_settings
from pawguard.core.exceptions import ConflictError, NotFoundError
from pawguard.modules.settings.models import BusinessRule, PasswordPolicy, SystemSetting
from pawguard.modules.settings.repository import (
    BusinessRuleRepository,
    PasswordPolicyRepository,
    SystemSettingRepository,
)
from pawguard.modules.settings.schemas import (
    BusinessRuleCreate,
    BusinessRuleUpdate,
    GeneralSettingsResponse,
    PasswordPolicyUpdate,
    PublicContentResponse,
    PublicContentUpdate,
    SystemSettingCreate,
    SystemSettingUpdate,
)


class SystemSettingService:
    def __init__(self, repository: SystemSettingRepository) -> None:
        self._repo = repository

    async def get_setting(self, key: str) -> SystemSetting:
        setting = await self._repo.get_by_key(key)
        if setting is None:
            raise NotFoundError(f"Setting '{key}' not found.")
        return setting

    async def list_by_category(self, category: str) -> list[SystemSetting]:
        return list(await self._repo.list_by_category(category))

    async def list_all(self) -> list[SystemSetting]:
        return list(await self._repo.list_all())

    async def create_setting(self, payload: SystemSettingCreate) -> SystemSetting:
        existing = await self._repo.get_by_key(payload.key)
        if existing is not None:
            raise ConflictError(f"Setting '{payload.key}' already exists.")
        setting = SystemSetting(**payload.model_dump())
        return await self._repo.create(setting)

    async def update_setting(self, key: str, payload: SystemSettingUpdate) -> SystemSetting:
        setting = await self._repo.get_by_key(key)
        if setting is None:
            raise NotFoundError(f"Setting '{key}' not found.")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(setting, field, value)
        return setting

    async def delete_setting(self, setting_id: uuid.UUID) -> None:
        setting = await self._repo.get_by_id(setting_id)
        if setting is None:
            raise NotFoundError(f"Setting with id '{setting_id}' not found.")
        await self._repo.delete(setting_id)


class PasswordPolicyService:
    def __init__(self, repository: PasswordPolicyRepository) -> None:
        self._repo = repository
        self._session = repository._session

    async def get_active(self) -> PasswordPolicy:
        policy = await self._repo.get_active()
        if policy is None:
            # Auto-provision the default policy the first time it's read,
            # rather than returning a transient, unpersisted PasswordPolicy()
            # - its column defaults (min_length, etc.) are only applied by
            # SQLAlchemy on flush/INSERT, so an unsaved instance has every
            # field as None and fails response serialization with a 500.
            policy = await self._repo.create(PasswordPolicy())
        return policy

    async def update_policy(self, payload: PasswordPolicyUpdate) -> PasswordPolicy:
        policy = await self._repo.get_active()
        if policy is None:
            policy = PasswordPolicy()
            self._session.add(policy)
            for field, value in payload.model_dump(exclude_unset=True).items():
                setattr(policy, field, value)
            return policy
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(policy, field, value)
        return policy

    async def list_all(self) -> list[PasswordPolicy]:
        return list(await self._repo.list_all())


class BusinessRuleService:
    def __init__(self, repository: BusinessRuleRepository) -> None:
        self._repo = repository

    async def get_rule(self, rule_key: str) -> BusinessRule:
        rule = await self._repo.get_by_key(rule_key)
        if rule is None:
            raise NotFoundError(f"Business rule '{rule_key}' not found.")
        return rule

    async def list_by_module(self, module: str) -> list[BusinessRule]:
        return list(await self._repo.list_by_module(module))

    async def list_all(self) -> list[BusinessRule]:
        return list(await self._repo.list_all())

    async def create_rule(self, payload: BusinessRuleCreate) -> BusinessRule:
        existing = await self._repo.get_by_key(payload.rule_key)
        if existing is not None:
            raise ConflictError(f"Business rule '{payload.rule_key}' already exists.")
        rule = BusinessRule(
            rule_key=payload.rule_key,
            rule_value=payload.rule_value,
            description=payload.description,
            module=payload.module,
        )
        return await self._repo.create(rule)

    async def update_rule(self, rule_key: str, payload: BusinessRuleUpdate) -> BusinessRule:
        rule = await self._repo.get_by_key(rule_key)
        if rule is None:
            raise NotFoundError(f"Business rule '{rule_key}' not found.")
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        return rule

    async def delete_rule(self, rule_id: uuid.UUID) -> None:
        rule = await self._repo.get_by_id(rule_id)
        if rule is None:
            raise NotFoundError(f"Business rule with id '{rule_id}' not found.")
        await self._repo.delete(rule_id)


ABOUT_US_KEY = "public_about_us"
MISSION_KEY = "public_mission"
PUBLIC_CONTENT_CATEGORY = "content"
PUBLIC_CONTENT_KEYS = (ABOUT_US_KEY, MISSION_KEY)

DEFAULT_ABOUT_US = (
    "PawGuard is a community-driven rescue organisation that rescues, "
    "rehabilitates and rehomes stray animals. Our shelters, rescue teams and "
    "volunteers work around the clock to give every animal a second chance."
)
DEFAULT_MISSION = (
    "To protect every stray animal and build a compassionate, adoption-ready "
    "community through rescue, medical care and responsible rehoming."
)


class PublicContentService:
    """Owns the publicly visible About & Mission copy (RULE-003).

    Content is stored as `SystemSetting` rows (`content` category) so admins
    can edit it from the Admin Portal without a deploy. Missing settings fall
    back to the built-in defaults, keeping the public endpoint stable.
    """

    def __init__(self, repository: SystemSettingRepository) -> None:
        self._repo = repository

    async def get_content(self) -> PublicContentResponse:
        about = await self._repo.get_by_key(ABOUT_US_KEY)
        mission = await self._repo.get_by_key(MISSION_KEY)
        updated = None
        for setting in (about, mission):
            if setting is not None and (
                updated is None or setting.updated_at > updated
            ):
                updated = setting.updated_at
        return PublicContentResponse(
            about_us=about.value if about else DEFAULT_ABOUT_US,
            mission=mission.value if mission else DEFAULT_MISSION,
            updated_at=updated,
        )

    async def update_content(self, payload: PublicContentUpdate) -> PublicContentResponse:
        updates = {
            key: value
            for key, value in (
                (ABOUT_US_KEY, payload.about_us),
                (MISSION_KEY, payload.mission),
            )
            if value is not None
        }
        if not updates:
            return await self.get_content()
        for key, value in updates.items():
            existing = await self._repo.get_by_key(key)
            if existing is None:
                label = key.removeprefix("public_").replace("_", " ")
                await self._repo.create(
                    SystemSetting(
                        key=key,
                        value=value,
                        category=PUBLIC_CONTENT_CATEGORY,
                        description=f"Public-facing {label} content.",
                    )
                )
            else:
                existing.value = value
        return await self.get_content()


class AppConfigService:
    def get_general_settings(self) -> GeneralSettingsResponse:
        s = get_settings()
        return GeneralSettingsResponse(
            app_name=s.app_name,
            environment=s.environment,
            debug=s.debug,
            allowed_hosts=s.allowed_hosts,
            cors_origins=s.cors_origins,
            web_app_url=s.web_app_url,
            admin_app_url=s.admin_app_url,
            mobile_deep_link_base=s.mobile_deep_link_base,
        )

    def get_email_settings(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "mail_from": s.mail_from,
            "mail_host": s.mail_host,
            "mail_port": s.mail_port,
            "mail_use_tls": s.mail_use_tls,
        }

    def get_storage_settings(self) -> dict[str, Any]:
        s = get_settings()
        return {
            "s3_bucket_name": s.s3_bucket_name,
            "s3_region": s.s3_region,
        }
