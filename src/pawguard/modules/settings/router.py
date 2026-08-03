"""API router for Settings & Configuration module (RULE-004)."""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.settings.repository import (
    BusinessRuleRepository,
    PasswordPolicyRepository,
    SystemSettingRepository,
)
from pawguard.modules.settings.schemas import (
    BusinessRuleCreate,
    BusinessRuleResponse,
    BusinessRuleUpdate,
    GeneralSettingsResponse,
    PasswordPolicyResponse,
    PasswordPolicyUpdate,
    PublicContentResponse,
    PublicContentUpdate,
    SystemSettingCreate,
    SystemSettingResponse,
    SystemSettingUpdate,
)
from pawguard.modules.settings.service import (
    AppConfigService,
    BusinessRuleService,
    PasswordPolicyService,
    PublicContentService,
    SystemSettingService,
)

router = APIRouter(prefix="/settings", tags=["settings"])


def get_setting_service(db: AsyncSession = Depends(get_db)) -> SystemSettingService:
    return SystemSettingService(SystemSettingRepository(db))


def get_password_policy_service(db: AsyncSession = Depends(get_db)) -> PasswordPolicyService:
    return PasswordPolicyService(PasswordPolicyRepository(db))


def get_business_rule_service(db: AsyncSession = Depends(get_db)) -> BusinessRuleService:
    return BusinessRuleService(BusinessRuleRepository(db))


def get_public_content_service(db: AsyncSession = Depends(get_db)) -> PublicContentService:
    return PublicContentService(SystemSettingRepository(db))


@router.get(
    "/general",
    response_model=ApiResponse[GeneralSettingsResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_general_settings() -> ApiResponse[GeneralSettingsResponse]:
    data = AppConfigService().get_general_settings()
    return ApiResponse(data=data)


@router.get(
    "/email",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_email_settings() -> ApiResponse[dict[str, Any]]:
    data = AppConfigService().get_email_settings()
    return ApiResponse(data=data)


@router.get(
    "/storage",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_storage_settings() -> ApiResponse[dict[str, Any]]:
    data = AppConfigService().get_storage_settings()
    return ApiResponse(data=data)


@router.get(
    "/public-content",
    response_model=ApiResponse[PublicContentResponse],
    dependencies=[Depends(require_permission("public:read"))],
)
async def get_public_content(
    service: PublicContentService = Depends(get_public_content_service),
) -> ApiResponse[PublicContentResponse]:
    content = await service.get_content()
    return ApiResponse(data=content)


@router.put(
    "/public-content",
    response_model=ApiResponse[PublicContentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_public_content(
    payload: PublicContentUpdate,
    service: PublicContentService = Depends(get_public_content_service),
) -> ApiResponse[PublicContentResponse]:
    content = await service.update_content(payload)
    return ApiResponse(
        data=content,
        message="Public content updated.",
    )


@router.get(
    "/system",
    response_model=ApiResponse[list[SystemSettingResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_settings(
    category: str | None = Query(None),
    service: SystemSettingService = Depends(get_setting_service),
) -> ApiResponse[list[SystemSettingResponse]]:
    if category:
        settings = await service.list_by_category(category)
    else:
        settings = await service.list_all()
    return ApiResponse(data=[SystemSettingResponse.model_validate(s) for s in settings])


@router.get(
    "/system/{key}",
    response_model=ApiResponse[SystemSettingResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_setting(
    key: str,
    service: SystemSettingService = Depends(get_setting_service),
) -> ApiResponse[SystemSettingResponse]:
    setting = await service.get_setting(key)
    return ApiResponse(data=SystemSettingResponse.model_validate(setting))


@router.post(
    "/system",
    response_model=ApiResponse[SystemSettingResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_setting(
    payload: SystemSettingCreate,
    service: SystemSettingService = Depends(get_setting_service),
) -> ApiResponse[SystemSettingResponse]:
    setting = await service.create_setting(payload)
    return ApiResponse(
        data=SystemSettingResponse.model_validate(setting),
        message="Setting created.",
    )


@router.put(
    "/system/{key}",
    response_model=ApiResponse[SystemSettingResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_setting(
    key: str,
    payload: SystemSettingUpdate,
    service: SystemSettingService = Depends(get_setting_service),
) -> ApiResponse[SystemSettingResponse]:
    setting = await service.update_setting(key, payload)
    return ApiResponse(
        data=SystemSettingResponse.model_validate(setting),
        message="Setting updated.",
    )


@router.delete(
    "/system/{setting_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_setting(
    setting_id: uuid.UUID,
    service: SystemSettingService = Depends(get_setting_service),
) -> None:
    await service.delete_setting(setting_id)


@router.get(
    "/password-policy",
    response_model=ApiResponse[PasswordPolicyResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_password_policy(
    service: PasswordPolicyService = Depends(get_password_policy_service),
) -> ApiResponse[PasswordPolicyResponse]:
    policy = await service.get_active()
    return ApiResponse(data=PasswordPolicyResponse.model_validate(policy))


@router.put(
    "/password-policy",
    response_model=ApiResponse[PasswordPolicyResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_password_policy(
    payload: PasswordPolicyUpdate,
    service: PasswordPolicyService = Depends(get_password_policy_service),
) -> ApiResponse[PasswordPolicyResponse]:
    policy = await service.update_policy(payload)
    return ApiResponse(
        data=PasswordPolicyResponse.model_validate(policy),
        message="Password policy updated.",
    )


@router.get(
    "/business-rules",
    response_model=ApiResponse[list[BusinessRuleResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_business_rules(
    module: str | None = Query(None),
    service: BusinessRuleService = Depends(get_business_rule_service),
) -> ApiResponse[list[BusinessRuleResponse]]:
    if module:
        rules = await service.list_by_module(module)
    else:
        rules = await service.list_all()
    return ApiResponse(data=[BusinessRuleResponse.model_validate(r) for r in rules])


@router.get(
    "/business-rules/{rule_key}",
    response_model=ApiResponse[BusinessRuleResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_business_rule(
    rule_key: str,
    service: BusinessRuleService = Depends(get_business_rule_service),
) -> ApiResponse[BusinessRuleResponse]:
    rule = await service.get_rule(rule_key)
    return ApiResponse(data=BusinessRuleResponse.model_validate(rule))


@router.post(
    "/business-rules",
    response_model=ApiResponse[BusinessRuleResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_business_rule(
    payload: BusinessRuleCreate,
    service: BusinessRuleService = Depends(get_business_rule_service),
) -> ApiResponse[BusinessRuleResponse]:
    rule = await service.create_rule(payload)
    return ApiResponse(
        data=BusinessRuleResponse.model_validate(rule),
        message="Business rule created.",
    )


@router.put(
    "/business-rules/{rule_key}",
    response_model=ApiResponse[BusinessRuleResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_business_rule(
    rule_key: str,
    payload: BusinessRuleUpdate,
    service: BusinessRuleService = Depends(get_business_rule_service),
) -> ApiResponse[BusinessRuleResponse]:
    rule = await service.update_rule(rule_key, payload)
    return ApiResponse(
        data=BusinessRuleResponse.model_validate(rule),
        message="Business rule updated.",
    )


@router.delete(
    "/business-rules/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_business_rule(
    rule_id: uuid.UUID,
    service: BusinessRuleService = Depends(get_business_rule_service),
) -> None:
    await service.delete_rule(rule_id)
