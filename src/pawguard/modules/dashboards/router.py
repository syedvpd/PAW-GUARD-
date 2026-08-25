import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from pawguard.core.cache_decorator import cache_response
from pawguard.core.responses import ApiResponse
from pawguard.db.session import get_db
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.rbac import require_permission
from pawguard.modules.dashboards import service as dasvc
from pawguard.redis.client import RedisClient, get_redis

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get(
    "/rescue",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:rescue"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_rescue_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.rescue_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/rescue/operations",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:rescue"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_rescue_operations_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.rescue_operations_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/rescue/stream",
    responses={
        200: {
            "description": "Server-Sent Events stream of the live rescue dashboard",
            "content": {"text/event-stream": {}},
        }
    },
    dependencies=[Depends(require_permission("dashboard:rescue"))],
)
async def stream_rescue_dashboard(
    request: Request,
    interval: int = Query(30, ge=5, le=300, description="Snapshot interval (seconds)"),
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> StreamingResponse:
    """Real-time rescue dashboard feed (PRR 3.2).

    Subscribes to Redis Pub/Sub 'dispatch:events' channel for immediate updates on database writes,
    falling back to periodic snapshots every `interval` seconds (also acts as heartbeat).
    """

    async def _event_stream():
        pubsub = None
        if hasattr(redis, "pubsub"):
            try:
                pubsub = redis.pubsub()
                await pubsub.subscribe("dispatch:events")
            except Exception:
                pubsub = None

        # Send initial snapshot immediately
        try:
            data = await dasvc.rescue_dashboard(db)
            payload = json.dumps(
                {"data": data, "ts": datetime.now(UTC).isoformat()},
                default=str,
            )
            yield f"event: snapshot\ndata: {payload}\n\n"
        except Exception:
            yield ": initial snapshot unavailable, stream starting\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                received_event = False
                if pubsub is not None:
                    try:
                        # Wait for next event via pub/sub or timeout
                        msg = await pubsub.get_message(
                            ignore_subscribe_messages=True, timeout=interval
                        )
                        if msg is not None:
                            received_event = True
                    except Exception:
                        await asyncio.sleep(interval)
                else:
                    await asyncio.sleep(interval)

                if received_event:
                    try:
                        data = await dasvc.rescue_dashboard(db)
                        payload = json.dumps(
                            {"data": data, "ts": datetime.now(UTC).isoformat()},
                            default=str,
                        )
                        yield f"event: snapshot\ndata: {payload}\n\n"
                    except Exception:
                        yield ": snapshot unavailable, stream alive\n\n"
                else:
                    yield ": heartbeat\n\n"
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe("dispatch:events")
                    await pubsub.close()

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/shelter",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:shelter"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_shelter_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.shelter_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/medical",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:medical"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_medical_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.medical_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/adoption",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:adoption"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_adoption_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.adoption_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/foster",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:foster"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_foster_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.foster_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/volunteer",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:volunteer"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_volunteer_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.volunteer_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/inventory",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:inventory"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_inventory_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.inventory_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/finance",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:finance"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_finance_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.finance_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/donor",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("dashboard:donor"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_donor_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.donor_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/staff",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_staff_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.staff_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/executive",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=300, namespace="dashboards")
async def get_executive_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.executive_dashboard(db, redis=redis)
    return ApiResponse(data=data)


@router.get(
    "/public",
    response_model=ApiResponse[dict[str, Any]],
)
async def get_public_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
) -> Response:
    data = await dasvc.public_dashboard(db, redis=redis)
    res_data: ApiResponse[dict[str, Any]] = ApiResponse(data=data)
    from pawguard.core.cache_utils import etag_cache_response

    return etag_cache_response(request, res_data)


@router.get(
    "/operations",
    response_model=ApiResponse[dict[str, Any]],
    dependencies=[Depends(require_permission("system:admin"))],
)
@cache_response(ttl_seconds=60, namespace="dashboards")
async def get_operations_dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    redis: RedisClient = Depends(get_redis),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApiResponse[dict[str, Any]]:
    data = await dasvc.operations_dashboard(db, redis=redis)
    return ApiResponse(data=data)
