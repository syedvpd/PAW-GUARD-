"""Data access for Settings module (RULE-002)."""

import uuid
from collections.abc import Sequence

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.modules.settings.models import BusinessRule, PasswordPolicy, SystemSetting


class SystemSettingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, key: str) -> SystemSetting | None:
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, setting_id: uuid.UUID) -> SystemSetting | None:
        stmt = select(SystemSetting).where(SystemSetting.id == setting_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_category(self, category: str) -> Sequence[SystemSetting]:
        stmt = select(SystemSetting).where(
            SystemSetting.category == category
        ).order_by(SystemSetting.key)
        return (await self._session.execute(stmt)).scalars().all()

    async def list_all(self) -> Sequence[SystemSetting]:
        stmt = select(SystemSetting).order_by(SystemSetting.category, SystemSetting.key)
        return (await self._session.execute(stmt)).scalars().all()

    async def create(self, setting: SystemSetting) -> SystemSetting:
        self._session.add(setting)
        await self._session.flush()
        return setting

    async def update_by_key(self, key: str, value: str) -> SystemSetting | None:
        stmt = (
            update(SystemSetting)
            .where(SystemSetting.key == key)
            .values(value=value)
        )
        await self._session.execute(stmt)
        return await self.get_by_key(key)

    async def delete(self, setting_id: uuid.UUID) -> None:
        stmt = select(SystemSetting).where(SystemSetting.id == setting_id)
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            await self._session.delete(obj)


class PasswordPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_active(self) -> PasswordPolicy | None:
        stmt = select(PasswordPolicy).where(PasswordPolicy.is_active.is_(True)).limit(1)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, policy_id: uuid.UUID) -> PasswordPolicy | None:
        stmt = select(PasswordPolicy).where(PasswordPolicy.id == policy_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_all(self) -> Sequence[PasswordPolicy]:
        stmt = select(PasswordPolicy).order_by(PasswordPolicy.created_at.desc())
        return (await self._session.execute(stmt)).scalars().all()

    async def create(self, policy: PasswordPolicy) -> PasswordPolicy:
        self._session.add(policy)
        await self._session.flush()
        return policy


class BusinessRuleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_key(self, rule_key: str) -> BusinessRule | None:
        stmt = select(BusinessRule).where(BusinessRule.rule_key == rule_key)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, rule_id: uuid.UUID) -> BusinessRule | None:
        stmt = select(BusinessRule).where(BusinessRule.id == rule_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_by_module(self, module: str) -> Sequence[BusinessRule]:
        stmt = select(BusinessRule).where(
            BusinessRule.module == module
        ).order_by(BusinessRule.rule_key)
        return (await self._session.execute(stmt)).scalars().all()

    async def list_all(self) -> Sequence[BusinessRule]:
        stmt = select(BusinessRule).order_by(BusinessRule.module, BusinessRule.rule_key)
        return (await self._session.execute(stmt)).scalars().all()

    async def create(self, rule: BusinessRule) -> BusinessRule:
        self._session.add(rule)
        await self._session.flush()
        return rule

    async def update_by_key(self, rule_key: str, rule_value: str) -> BusinessRule | None:
        stmt = (
            update(BusinessRule)
            .where(BusinessRule.rule_key == rule_key)
            .values(rule_value=rule_value)
        )
        await self._session.execute(stmt)
        return await self.get_by_key(rule_key)

    async def delete(self, rule_id: uuid.UUID) -> None:
        stmt = select(BusinessRule).where(BusinessRule.id == rule_id)
        obj = (await self._session.execute(stmt)).scalar_one_or_none()
        if obj:
            await self._session.delete(obj)
