"""API router for public portal CMS and user-facing content (RULE-004)."""

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.bulk import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    BulkStatusUpdateRequest,
    BulkStatusUpdateResponse,
)
from pawguard.core.cache_decorator import cache_response
from pawguard.core.cache_utils import etag_cache_response
from pawguard.core.exceptions import parse_enum
from pawguard.core.pagination import PageParams, build_pagination_meta, page_params
from pawguard.core.rate_limiter import rate_limit
from pawguard.core.responses import ApiResponse, PaginatedResponse
from pawguard.core.search import SortParams, sort_params
from pawguard.db.session import get_db
from pawguard.modules.auth.audit import get_audit_service
from pawguard.modules.auth.dependencies import (
    CurrentUser,
    get_current_user,
)
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.auth.router import _build_request_context
from pawguard.modules.portal.models import ContentStatus, LegalDocumentType
from pawguard.modules.portal.repository import PortalRepository
from pawguard.modules.portal.schemas import (
    BlogPostCreate,
    BlogPostResponse,
    BlogPostSummaryResponse,
    BlogPostUpdate,
    CmsPageResponse,
    CmsPageUpdate,
    ContactLocationCreate,
    ContactLocationResponse,
    ContactLocationUpdate,
    ContactMessageCreate,
    FAQEntryCreate,
    FAQEntryResponse,
    FAQEntryUpdate,
    LegalDocumentCreate,
    LegalDocumentResponse,
    LegalDocumentUpdate,
    NewsletterSubscribeRequest,
    NewsletterSubscriptionResponse,
    PublicCmsPageResponse,
    PublicHeroStats,
    SuccessStoryCreate,
    SuccessStoryResponse,
    SuccessStorySummaryResponse,
    SuccessStoryUpdate,
    SystemSettingResponse,
    SystemSettingUpsert,
    TransparencyStats,
    UrgentAlertCreate,
    UrgentAlertResponse,
    UrgentAlertUpdate,
    UserDashboardSummary,
    VeterinaryPartnerCreate,
    VeterinaryPartnerResponse,
    VeterinaryPartnerUpdate,
)
from pawguard.modules.portal.service import PortalService
from pawguard.modules.storage.models import FileFolder
from pawguard.modules.storage.repository import StorageRepository
from pawguard.modules.storage.schemas import (
    StoredFileCreate,
    StoredFileResponse,
    UploadUrlResponse,
)
from pawguard.modules.storage.service import StorageService as StorageModuleService
from pawguard.redis.client import RedisClient, get_redis
from pawguard.services.audit_service import AuditService
from pawguard.services.cache_service import CacheService
from pawguard.services.storage_service import StorageService as S3StorageService
from pawguard.workers.pool import get_arq_pool

router = APIRouter(prefix="/portal", tags=["portal"])

# Shared per-user budget for all CMS write routes (PRR §6.1 abuse controls).
# Declared after `get_current_user` in each handler so request.state.user_id is
# set and the limit keys on the admin's user id, not a shared office IP.
_ADMIN_WRITE_RATE_LIMIT = rate_limit("portal_admin_write", 30, 60)


CACHE_NAMESPACE = "portal"


def get_portal_service(
    db: AsyncSession = Depends(get_db),
    audit: AuditService = Depends(get_audit_service),
    redis: RedisClient = Depends(get_redis),
    arq_pool: Any = Depends(get_arq_pool),
) -> PortalService:
    return PortalService(
        PortalRepository(db),
        db,
        audit_service=audit,
        cache_service=CacheService(redis, namespace=CACHE_NAMESPACE),
        arq_pool=arq_pool,
    )


# ── Public reads (no auth) ───────────────────────────────────────────────────


@router.get(
    "/stats",
    response_model=ApiResponse[PublicHeroStats],
)
@cache_response(ttl_seconds=300, namespace="portal")
async def get_hero_stats(
    request: Request,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    res_data: ApiResponse[PublicHeroStats] = ApiResponse(data=await service.get_hero_stats())
    return etag_cache_response(request, res_data)


@router.get("/success-stories", response_model=PaginatedResponse[SuccessStorySummaryResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def list_published_stories(
    request: Request,
    page: PageParams = Depends(page_params),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    stories, meta = await service.list_stories_paginated(
        page_params=page,
        status=ContentStatus.PUBLISHED,
    )
    res_data: PaginatedResponse[SuccessStorySummaryResponse] = PaginatedResponse(
        data=[SuccessStorySummaryResponse.model_validate(s) for s in stories],
        meta=meta,
    )
    return etag_cache_response(request, res_data)


@router.get("/success-stories/{story_id}", response_model=ApiResponse[SuccessStoryResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def get_published_story(
    request: Request,
    story_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    story = await service.get_story(story_id, published_only=True)
    res_data: ApiResponse[SuccessStoryResponse] = ApiResponse(
        data=SuccessStoryResponse.model_validate(story)
    )
    return etag_cache_response(request, res_data)


@router.get("/success-stories/slug/{slug}", response_model=ApiResponse[SuccessStoryResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def get_published_story_by_slug(
    request: Request,
    slug: str,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    story = await service.get_story_by_slug(slug, published_only=True)
    res_data: ApiResponse[SuccessStoryResponse] = ApiResponse(
        data=SuccessStoryResponse.model_validate(story)
    )
    return etag_cache_response(request, res_data)


@router.get("/blog", response_model=PaginatedResponse[BlogPostSummaryResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def list_published_blog(
    request: Request,
    page: PageParams = Depends(page_params),
    category: str | None = None,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    posts, meta = await service.list_blogs_paginated(
        page_params=page,
        status=ContentStatus.PUBLISHED,
        category=category,
    )
    res_data: PaginatedResponse[BlogPostSummaryResponse] = PaginatedResponse(
        data=[BlogPostSummaryResponse.model_validate(p) for p in posts],
        meta=meta,
    )
    return etag_cache_response(request, res_data)


@router.get("/blog/related", response_model=PaginatedResponse[BlogPostSummaryResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def list_related_blog_posts(
    request: Request,
    post_id: uuid.UUID = Query(
        ..., description="Source post id to find related posts for (excluded from results)"
    ),
    limit: int = Query(3, ge=1, le=12, description="Maximum related posts (server-enforced cap)"),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    posts = await service.get_related_blogs(post_id, limit)
    res_data: PaginatedResponse[BlogPostSummaryResponse] = PaginatedResponse(
        data=[BlogPostSummaryResponse.model_validate(p) for p in posts],
        meta=build_pagination_meta(total=len(posts), params=PageParams(page=1, page_size=limit)),
    )
    return etag_cache_response(request, res_data)


@router.get("/blog/slug/{slug}", response_model=ApiResponse[BlogPostResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def get_blog_by_slug(
    request: Request,
    slug: str,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    post = await service.get_blog_by_slug(slug, published_only=True)
    res_data: ApiResponse[BlogPostResponse] = ApiResponse(
        data=BlogPostResponse.model_validate(post)
    )
    return etag_cache_response(request, res_data)


@router.get("/veterinary-network", response_model=PaginatedResponse[VeterinaryPartnerResponse])
@cache_response(ttl_seconds=300, namespace="portal")
async def list_veterinary_partners(
    request: Request,
    emergency_only: bool = False,
    page: PageParams = Depends(page_params),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    partners, meta = await service.list_vets_paginated(
        active_only=True,
        emergency_only=emergency_only,
        page_params=page,
    )
    res_data: PaginatedResponse[VeterinaryPartnerResponse] = PaginatedResponse(
        data=[VeterinaryPartnerResponse.model_validate(p) for p in partners],
        meta=meta,
    )
    return etag_cache_response(request, res_data)


@router.get("/contact", response_model=ApiResponse[list[ContactLocationResponse]])
@cache_response(ttl_seconds=300, namespace="portal")
async def list_contact_locations(
    request: Request,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    locations = await service.list_contacts()
    res_data: ApiResponse[list[ContactLocationResponse]] = ApiResponse(
        data=[ContactLocationResponse.model_validate(loc) for loc in locations]
    )
    return etag_cache_response(request, res_data)


@router.post(
    "/contact",
    response_model=ApiResponse[None],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("portal_contact", max_requests=5, window_seconds=3600))],
)
async def submit_contact_message(
    payload: ContactMessageCreate,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    accepted = await service.submit_contact_message(payload)
    # Deliberately do not reveal whether an email belongs to an account.
    return ApiResponse(
        message=(
            "Your message was received."
            if accepted
            else "If that email belongs to a PawGuard account, your message was received."
        )
    )


@router.post(
    "/newsletter/subscribe",
    response_model=ApiResponse[NewsletterSubscriptionResponse],
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(rate_limit("portal_newsletter", max_requests=3, window_seconds=3600))],
)
async def subscribe_newsletter(
    payload: NewsletterSubscribeRequest,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[NewsletterSubscriptionResponse]:
    subscribed = await service.subscribe_newsletter(payload)
    return ApiResponse(
        data=NewsletterSubscriptionResponse(subscribed=subscribed),
        message=(
            "You are subscribed to PawGuard updates."
            if subscribed
            else "If that email belongs to a PawGuard account, subscription is available there."
        ),
    )


@router.get("/faq", response_model=ApiResponse[list[FAQEntryResponse]])
async def list_faq(
    request: Request,
    category: str | None = None,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    entries = await service.list_faqs(published_only=True, category=category)
    res_data: ApiResponse[list[FAQEntryResponse]] = ApiResponse(
        data=[FAQEntryResponse.model_validate(e) for e in entries]
    )
    return etag_cache_response(request, res_data)


@router.get("/legal", response_model=ApiResponse[list[LegalDocumentResponse]])
async def list_published_legal_docs(
    request: Request,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    docs = await service.list_legal_docs(published_only=True)
    res_data: ApiResponse[list[LegalDocumentResponse]] = ApiResponse(
        data=[LegalDocumentResponse.model_validate(d) for d in docs]
    )
    return etag_cache_response(request, res_data)


@router.get("/legal/{slug}", response_model=ApiResponse[LegalDocumentResponse])
async def get_published_legal_doc(
    request: Request,
    slug: str,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    doc = await service.get_legal_doc_by_slug(slug, published_only=True)
    res_data: ApiResponse[LegalDocumentResponse] = ApiResponse(
        data=LegalDocumentResponse.model_validate(doc)
    )
    return etag_cache_response(request, res_data)


@router.get("/urgent-alerts", response_model=PaginatedResponse[UrgentAlertResponse])
async def list_active_urgent_alerts(
    request: Request,
    page: PageParams = Depends(page_params),
    service: PortalService = Depends(get_portal_service),
) -> Response:
    alerts, meta = await service.get_active_alerts_paginated(page_params=page)
    res_data: PaginatedResponse[UrgentAlertResponse] = PaginatedResponse(
        data=[UrgentAlertResponse.model_validate(a) for a in alerts],
        meta=meta,
    )
    return etag_cache_response(request, res_data)


@router.get("/transparency", response_model=ApiResponse[TransparencyStats])
@cache_response(ttl_seconds=300, namespace="portal")
async def get_transparency_stats(
    request: Request,
    service: PortalService = Depends(get_portal_service),
) -> Response:
    res_data: ApiResponse[TransparencyStats] = ApiResponse(
        data=await service.get_transparency_stats()
    )
    return etag_cache_response(request, res_data)


@router.get("/me/dashboard", response_model=ApiResponse[UserDashboardSummary])
@cache_response(ttl_seconds=60, namespace="user_dashboard")
async def get_user_dashboard(
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[UserDashboardSummary]:
    summary = await service.get_user_dashboard(current_user.id, current_user.user.email)
    return ApiResponse(data=summary)


# ── Admin CMS writes ─────────────────────────────────────────────────────────


@router.post(
    "/admin/success-stories",
    response_model=ApiResponse[SuccessStoryResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_story(
    payload: SuccessStoryCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SuccessStoryResponse]:
    ip = request.client.host if request.client else None
    story = await service.create_story(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SuccessStoryResponse.model_validate(story),
        message="Success story created.",
    )


@router.put(
    "/admin/success-stories/{story_id}",
    response_model=ApiResponse[SuccessStoryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_story(
    story_id: uuid.UUID,
    payload: SuccessStoryUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SuccessStoryResponse]:
    ip = request.client.host if request.client else None
    story = await service.update_story(
        story_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SuccessStoryResponse.model_validate(story),
        message="Success story updated.",
    )


@router.post(
    "/admin/blog",
    response_model=ApiResponse[BlogPostResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_blog(
    payload: BlogPostCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[BlogPostResponse]:
    ip = request.client.host if request.client else None
    post = await service.create_blog(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BlogPostResponse.model_validate(post),
        message="Blog post created.",
    )


@router.put(
    "/admin/blog/{post_id}",
    response_model=ApiResponse[BlogPostResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_blog(
    post_id: uuid.UUID,
    payload: BlogPostUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[BlogPostResponse]:
    ip = request.client.host if request.client else None
    post = await service.update_blog(
        post_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BlogPostResponse.model_validate(post),
        message="Blog post updated.",
    )


@router.post(
    "/admin/veterinary-network",
    response_model=ApiResponse[VeterinaryPartnerResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_vet(
    payload: VeterinaryPartnerCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[VeterinaryPartnerResponse]:
    ip = request.client.host if request.client else None
    partner = await service.create_vet(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VeterinaryPartnerResponse.model_validate(partner),
        message="Veterinary partner added.",
    )


@router.put(
    "/admin/veterinary-network/{partner_id}",
    response_model=ApiResponse[VeterinaryPartnerResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_vet(
    partner_id: uuid.UUID,
    payload: VeterinaryPartnerUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[VeterinaryPartnerResponse]:
    ip = request.client.host if request.client else None
    partner = await service.update_vet(
        partner_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=VeterinaryPartnerResponse.model_validate(partner),
        message="Veterinary partner updated.",
    )


@router.post(
    "/admin/contact",
    response_model=ApiResponse[ContactLocationResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_contact(
    payload: ContactLocationCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[ContactLocationResponse]:
    ip = request.client.host if request.client else None
    location = await service.create_contact(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ContactLocationResponse.model_validate(location),
        message="Contact location added.",
    )


@router.put(
    "/admin/contact/{location_id}",
    response_model=ApiResponse[ContactLocationResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_contact(
    location_id: uuid.UUID,
    payload: ContactLocationUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[ContactLocationResponse]:
    ip = request.client.host if request.client else None
    location = await service.update_contact(
        location_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=ContactLocationResponse.model_validate(location),
        message="Contact location updated.",
    )


@router.post(
    "/admin/faq",
    response_model=ApiResponse[FAQEntryResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_faq(
    payload: FAQEntryCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[FAQEntryResponse]:
    ip = request.client.host if request.client else None
    entry = await service.create_faq(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FAQEntryResponse.model_validate(entry),
        message="FAQ entry created.",
    )


@router.put(
    "/admin/faq/{entry_id}",
    response_model=ApiResponse[FAQEntryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_faq(
    entry_id: uuid.UUID,
    payload: FAQEntryUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[FAQEntryResponse]:
    ip = request.client.host if request.client else None
    entry = await service.update_faq(
        entry_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=FAQEntryResponse.model_validate(entry),
        message="FAQ entry updated.",
    )


# ── Admin paginated list endpoints ────────────────────────────────────────────


@router.get(
    "/admin/success-stories",
    response_model=PaginatedResponse[SuccessStoryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def admin_list_stories(
    params: PageParams = Depends(page_params),
    status: ContentStatus | None = Query(None, description="Filter by status"),
    search: str | None = Query(None, description="Search by title, body, or summary"),
    sort: SortParams = Depends(sort_params),
    service: PortalService = Depends(get_portal_service),
) -> PaginatedResponse[SuccessStoryResponse]:
    stories, meta = await service.list_stories_paginated(
        page_params=params,
        status=status,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[SuccessStoryResponse.model_validate(s) for s in stories],
        meta=meta,
    )


@router.get(
    "/admin/blog",
    response_model=PaginatedResponse[BlogPostResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def admin_list_blogs(
    params: PageParams = Depends(page_params),
    status: ContentStatus | None = Query(None, description="Filter by status"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search by title, body, excerpt, or category"),
    sort: SortParams = Depends(sort_params),
    service: PortalService = Depends(get_portal_service),
) -> PaginatedResponse[BlogPostResponse]:
    blogs, meta = await service.list_blogs_paginated(
        page_params=params,
        status=status,
        category=category,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[BlogPostResponse.model_validate(b) for b in blogs],
        meta=meta,
    )


@router.get(
    "/admin/faq",
    response_model=PaginatedResponse[FAQEntryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def admin_list_faqs(
    params: PageParams = Depends(page_params),
    is_published: bool | None = Query(None, description="Filter by published status"),
    category: str | None = Query(None, description="Filter by category"),
    search: str | None = Query(None, description="Search by question, answer, or category"),
    sort: SortParams = Depends(sort_params),
    service: PortalService = Depends(get_portal_service),
) -> PaginatedResponse[FAQEntryResponse]:
    faqs, meta = await service.list_faqs_paginated(
        page_params=params,
        is_published=is_published,
        category=category,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[FAQEntryResponse.model_validate(e) for e in faqs],
        meta=meta,
    )


@router.put(
    "/admin/settings/{key}",
    response_model=ApiResponse[SystemSettingResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def upsert_setting(
    key: str,
    payload: SystemSettingUpsert,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SystemSettingResponse]:
    ip = request.client.host if request.client else None
    setting = await service.upsert_setting(
        key,
        payload.value,
        payload.description,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SystemSettingResponse.model_validate(setting),
        message="Setting saved.",
    )


@router.get(
    "/admin/settings",
    response_model=ApiResponse[list[SystemSettingResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_settings(
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[list[SystemSettingResponse]]:
    settings = await service.list_settings()
    return ApiResponse(data=[SystemSettingResponse.model_validate(s) for s in settings])


# ── Soft delete endpoints ────────────────────────────────────────────────────


@router.delete(
    "/admin/success-stories/{story_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def soft_delete_story(
    story_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_story(
        story_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Success story deleted.")


@router.delete(
    "/admin/blog/{post_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def soft_delete_blog(
    post_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_blog(
        post_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Blog post deleted.")


@router.delete(
    "/admin/faq/{entry_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def soft_delete_faq(
    entry_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_faq(
        entry_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="FAQ entry deleted.")


# ── Bulk operation endpoints ─────────────────────────────────────────────────


@router.post(
    "/admin/success-stories/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_delete_stories(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkDeleteResponse:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_stories(
        payload.ids,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkDeleteResponse(
        message=f"{deleted} success story(ies) deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/admin/success-stories/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_update_story_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkStatusUpdateResponse:
    ip = request.client.host if request.client else None
    status = parse_enum(ContentStatus, payload.status)
    updated = await service.bulk_update_story_status(
        payload.ids,
        status,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} success story(ies) updated.",
        updated_count=updated,
    )


@router.post(
    "/admin/blog/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_delete_blogs(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkDeleteResponse:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_blogs(
        payload.ids,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkDeleteResponse(
        message=f"{deleted} blog post(s) deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/admin/blog/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_update_blog_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkStatusUpdateResponse:
    ip = request.client.host if request.client else None
    status = parse_enum(ContentStatus, payload.status)
    updated = await service.bulk_update_blog_status(
        payload.ids,
        status,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} blog post(s) updated.",
        updated_count=updated,
    )


@router.post(
    "/admin/faq/bulk/delete",
    response_model=BulkDeleteResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_delete_faqs(
    payload: BulkDeleteRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkDeleteResponse:
    ip = request.client.host if request.client else None
    deleted = await service.bulk_delete_faqs(
        payload.ids,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkDeleteResponse(
        message=f"{deleted} FAQ entry(ies) deleted.",
        deleted_count=deleted,
    )


@router.post(
    "/admin/faq/bulk/status",
    response_model=BulkStatusUpdateResponse,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def bulk_update_faq_status(
    payload: BulkStatusUpdateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> BulkStatusUpdateResponse:
    ip = request.client.host if request.client else None
    is_published = payload.status.lower() == "true" or payload.status == "published"
    updated = await service.bulk_update_faq_status(
        payload.ids,
        is_published,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return BulkStatusUpdateResponse(
        message=f"{updated} FAQ entry(ies) updated.",
        updated_count=updated,
    )


# ── Legal documents (admin) ──────────────────────────────────────────────────


@router.post(
    "/admin/legal",
    response_model=ApiResponse[LegalDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_legal_doc(
    payload: LegalDocumentCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[LegalDocumentResponse]:
    ip = request.client.host if request.client else None
    doc = await service.create_legal_doc(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=LegalDocumentResponse.model_validate(doc),
        message="Legal document created.",
    )


@router.put(
    "/admin/legal/{doc_id}",
    response_model=ApiResponse[LegalDocumentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_legal_doc(
    doc_id: uuid.UUID,
    payload: LegalDocumentUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[LegalDocumentResponse]:
    ip = request.client.host if request.client else None
    doc = await service.update_legal_doc(
        doc_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=LegalDocumentResponse.model_validate(doc),
        message="Legal document updated.",
    )


@router.delete(
    "/admin/legal/{doc_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def soft_delete_legal_doc(
    doc_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_legal_doc(
        doc_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Legal document deleted.")


@router.get(
    "/admin/legal",
    response_model=PaginatedResponse[LegalDocumentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def admin_list_legal_docs(
    params: PageParams = Depends(page_params),
    status: ContentStatus | None = Query(None, description="Filter by status"),
    document_type: LegalDocumentType | None = Query(None, description="Filter by document type"),
    search: str | None = Query(None, description="Search by title, body, or slug"),
    sort: SortParams = Depends(sort_params),
    service: PortalService = Depends(get_portal_service),
) -> PaginatedResponse[LegalDocumentResponse]:
    docs, meta = await service.list_legal_docs_paginated(
        page_params=params,
        status=status,
        document_type=document_type.value if document_type else None,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[LegalDocumentResponse.model_validate(d) for d in docs],
        meta=meta,
    )


# ── Urgent alerts (admin) ────────────────────────────────────────────────────


@router.post(
    "/admin/urgent-alerts",
    response_model=ApiResponse[UrgentAlertResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def create_urgent_alert(
    payload: UrgentAlertCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[UrgentAlertResponse]:
    ip = request.client.host if request.client else None
    alert = await service.create_urgent_alert(
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=UrgentAlertResponse.model_validate(alert),
        message="Urgent alert created.",
    )


@router.put(
    "/admin/urgent-alerts/{alert_id}",
    response_model=ApiResponse[UrgentAlertResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_urgent_alert(
    alert_id: uuid.UUID,
    payload: UrgentAlertUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[UrgentAlertResponse]:
    ip = request.client.host if request.client else None
    alert = await service.update_urgent_alert(
        alert_id,
        payload,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=UrgentAlertResponse.model_validate(alert),
        message="Urgent alert updated.",
    )


@router.delete(
    "/admin/urgent-alerts/{alert_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def soft_delete_urgent_alert(
    alert_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_urgent_alert(
        alert_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Urgent alert deleted.")


@router.get(
    "/admin/urgent-alerts",
    response_model=PaginatedResponse[UrgentAlertResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def admin_list_urgent_alerts(
    params: PageParams = Depends(page_params),
    is_active: bool | None = Query(None, description="Filter by active status"),
    search: str | None = Query(None, description="Search by title or message"),
    sort: SortParams = Depends(sort_params),
    service: PortalService = Depends(get_portal_service),
) -> PaginatedResponse[UrgentAlertResponse]:
    alerts, meta = await service.list_urgent_alerts_paginated(
        page_params=params,
        is_active=is_active,
        search=search,
        sort=sort,
    )
    return PaginatedResponse(
        data=[UrgentAlertResponse.model_validate(a) for a in alerts],
        meta=meta,
    )


# ── Dynamic CMS Endpoints ───────────────────────────────────────────────────


@router.get(
    "/cms/pages/{slug}",
    response_model=ApiResponse[PublicCmsPageResponse],
)
async def get_public_cms_page(
    slug: str,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[PublicCmsPageResponse]:
    page = await service.get_public_cms_page(slug)
    return ApiResponse(data=page)


@router.get(
    "/admin/cms/pages",
    response_model=ApiResponse[list[CmsPageResponse]],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def list_admin_cms_pages(
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[list[CmsPageResponse]]:
    pages = await service.list_cms_pages()
    return ApiResponse(data=pages)


@router.get(
    "/admin/cms/pages/{slug}",
    response_model=ApiResponse[CmsPageResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_cms_page(
    slug: str,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[CmsPageResponse]:
    page = await service.get_admin_cms_page(slug)
    return ApiResponse(data=page)


@router.put(
    "/admin/cms/pages/{slug}",
    response_model=ApiResponse[CmsPageResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def update_admin_cms_page(
    slug: str,
    payload: CmsPageUpdate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[CmsPageResponse]:
    ctx = _build_request_context(request)
    page = await service.update_admin_cms_page(
        slug=slug,
        payload=payload,
        user_id=current_user.id,
        ctx=ctx,
    )
    return ApiResponse(data=page, message="CMS draft saved successfully.")


@router.post(
    "/admin/cms/pages/{slug}/publish",
    response_model=ApiResponse[CmsPageResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def publish_admin_cms_page(
    slug: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[CmsPageResponse]:
    ctx = _build_request_context(request)
    page = await service.publish_admin_cms_page(
        slug=slug,
        user_id=current_user.id,
        ctx=ctx,
    )
    return ApiResponse(data=page, message="CMS page published successfully.")


@router.post(
    "/admin/cms/pages/{slug}/discard",
    response_model=ApiResponse[CmsPageResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def discard_admin_cms_page(
    slug: str,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[CmsPageResponse]:
    ctx = _build_request_context(request)
    page = await service.discard_admin_cms_page(
        slug=slug,
        user_id=current_user.id,
        ctx=ctx,
    )
    return ApiResponse(data=page, message="CMS draft discarded successfully.")


# ── Admin Single GET details by ID endpoints ──────────────────────────────────


@router.get(
    "/admin/success-stories/{story_id}",
    response_model=ApiResponse[SuccessStoryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_story(
    story_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SuccessStoryResponse]:
    story = await service.get_story(story_id, published_only=False)
    return ApiResponse(data=SuccessStoryResponse.model_validate(story))


@router.get(
    "/admin/blog/{post_id}",
    response_model=ApiResponse[BlogPostResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_blog(
    post_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[BlogPostResponse]:
    post = await service.get_blog(post_id, published_only=False)
    return ApiResponse(data=BlogPostResponse.model_validate(post))


@router.get(
    "/admin/faq/{entry_id}",
    response_model=ApiResponse[FAQEntryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_faq(
    entry_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[FAQEntryResponse]:
    entry = await service.get_faq(entry_id)
    return ApiResponse(data=FAQEntryResponse.model_validate(entry))


@router.get(
    "/admin/legal/{doc_id}",
    response_model=ApiResponse[LegalDocumentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_legal_doc(
    doc_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[LegalDocumentResponse]:
    doc = await service.get_legal_doc(doc_id)
    return ApiResponse(data=LegalDocumentResponse.model_validate(doc))


@router.get(
    "/admin/contact/{location_id}",
    response_model=ApiResponse[ContactLocationResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_contact(
    location_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[ContactLocationResponse]:
    loc = await service.get_contact(location_id)
    return ApiResponse(data=ContactLocationResponse.model_validate(loc))


@router.get(
    "/admin/veterinary-network/{partner_id}",
    response_model=ApiResponse[VeterinaryPartnerResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def get_admin_vet(
    partner_id: uuid.UUID,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[VeterinaryPartnerResponse]:
    partner = await service.get_vet(partner_id)
    return ApiResponse(data=VeterinaryPartnerResponse.model_validate(partner))


# ── Contact Location and Veterinary Network Admin DELETE endpoints ────────────


@router.delete(
    "/admin/contact/{location_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_admin_contact(
    location_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_contact(
        location_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Contact location deleted successfully.")


@router.delete(
    "/admin/veterinary-network/{partner_id}",
    response_model=ApiResponse[None],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def delete_admin_vet(
    partner_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[None]:
    ip = request.client.host if request.client else None
    await service.soft_delete_vet(
        partner_id,
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(message="Veterinary partner deleted successfully.")


# ── Structured Content Admin Publish / Discard endpoints ─────────────────────


@router.post(
    "/admin/success-stories/{story_id}/publish",
    response_model=ApiResponse[SuccessStoryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def publish_admin_story(
    story_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SuccessStoryResponse]:
    ip = request.client.host if request.client else None
    story = await service.update_story(
        story_id,
        SuccessStoryUpdate(status=ContentStatus.PUBLISHED),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SuccessStoryResponse.model_validate(story),
        message="Success story published successfully.",
    )


@router.post(
    "/admin/success-stories/{story_id}/discard",
    response_model=ApiResponse[SuccessStoryResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def discard_admin_story(
    story_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[SuccessStoryResponse]:
    ip = request.client.host if request.client else None
    story = await service.update_story(
        story_id,
        SuccessStoryUpdate(status=ContentStatus.DRAFT),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=SuccessStoryResponse.model_validate(story),
        message="Success story draft discarded/unpublished successfully.",
    )


@router.post(
    "/admin/blog/{post_id}/publish",
    response_model=ApiResponse[BlogPostResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def publish_admin_blog(
    post_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[BlogPostResponse]:
    ip = request.client.host if request.client else None
    post = await service.update_blog(
        post_id,
        BlogPostUpdate(status=ContentStatus.PUBLISHED),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BlogPostResponse.model_validate(post),
        message="Blog post published successfully.",
    )


@router.post(
    "/admin/blog/{post_id}/discard",
    response_model=ApiResponse[BlogPostResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def discard_admin_blog(
    post_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[BlogPostResponse]:
    ip = request.client.host if request.client else None
    post = await service.update_blog(
        post_id,
        BlogPostUpdate(status=ContentStatus.DRAFT),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=BlogPostResponse.model_validate(post),
        message="Blog post draft discarded/unpublished successfully.",
    )


@router.post(
    "/admin/legal/{doc_id}/publish",
    response_model=ApiResponse[LegalDocumentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def publish_admin_legal_doc(
    doc_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[LegalDocumentResponse]:
    ip = request.client.host if request.client else None
    doc = await service.update_legal_doc(
        doc_id,
        LegalDocumentUpdate(status=ContentStatus.PUBLISHED),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=LegalDocumentResponse.model_validate(doc),
        message="Legal document published successfully.",
    )


@router.post(
    "/admin/legal/{doc_id}/discard",
    response_model=ApiResponse[LegalDocumentResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def discard_admin_legal_doc(
    doc_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    service: PortalService = Depends(get_portal_service),
) -> ApiResponse[LegalDocumentResponse]:
    ip = request.client.host if request.client else None
    doc = await service.update_legal_doc(
        doc_id,
        LegalDocumentUpdate(status=ContentStatus.DRAFT),
        actor_id=current_user.id,
        ip_address=ip,
    )
    return ApiResponse(
        data=LegalDocumentResponse.model_validate(doc),
        message="Legal document draft discarded/unpublished successfully.",
    )


# ── CMS media (secure admin upload, reuses S3 storage architecture) ──────────


@router.post(
    "/admin/cms/media/upload-url",
    response_model=ApiResponse[UploadUrlResponse],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("system:admin"))],
)
async def request_cms_media_upload_url(
    payload: StoredFileCreate,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    _: Annotated[None, Depends(_ADMIN_WRITE_RATE_LIMIT)] = None,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[UploadUrlResponse]:
    """Request a presigned S3 upload URL for CMS media (image/video/PDF).

    Reuses the shared storage architecture: declared MIME type and size are
    validated up front, an object key is reserved in the ``cms`` folder, and
    the caller PUTs bytes straight to S3 before confirming. The returned
    ``object_key`` is what admins persist inside CMS content fields; public
    read-time resolution generates presigned URLs on demand and never stores
    them permanently.
    """
    storage_service = StorageModuleService(StorageRepository(db), S3StorageService())
    result = await storage_service.request_upload_url(
        StoredFileCreate(
            original_filename=payload.original_filename,
            mime_type=payload.mime_type,
            file_size=payload.file_size,
            folder=FileFolder.CMS,
            entity_type="cms",
            entity_id=None,
        ),
        user_id=current_user.id,
    )
    return ApiResponse(data=result, message="CMS media upload URL generated.")


@router.post(
    "/admin/cms/media/{file_id}/confirm",
    response_model=ApiResponse[StoredFileResponse],
    dependencies=[Depends(require_permission("system:admin"))],
)
async def confirm_cms_media_upload(
    file_id: uuid.UUID,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[StoredFileResponse]:
    """Confirm a CMS media upload after the bytes reach S3.

    Re-verifies the real file size and magic-bytes signature before trusting
    the object, then marks it uploaded. Returns the stored file metadata; the
    ``object_key`` is what the admin saves in a CMS content field.
    """
    storage_service = StorageModuleService(StorageRepository(db), S3StorageService())
    stored = await storage_service.confirm_upload(file_id)
    return ApiResponse(
        data=StoredFileResponse.model_validate(stored),
        message="CMS media confirmed.",
    )
