"""PawGuard Rigorous OpenAPI Surface API Performance Benchmark Script.

Scans the complete FastAPI OpenAPI surface across all 917 operations (703 paths),
classifies execution categories (A..F), overrides current_user auth dependency with admin claims,
performs 5 measured iterations (+1 warmup) per executable endpoint using httpx.AsyncClient,
records exact HTTP response status codes (2xx vs 401/403/404/422/500),
and writes structured empirical sample metrics to docs/API_PERFORMANCE_RESULTS.json.
"""

import asyncio
import json
import statistics
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from pawguard.core.security import AccessTokenClaims, create_access_token
from pawguard.main import app
from pawguard.modules.auth.dependencies import CurrentUser, get_current_user
from pawguard.modules.auth.models import User


class MockRedis:
    """Mock Redis client for benchmark test context to prevent NoneType attribute errors."""

    async def get(self, key: str) -> Any:
        return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        pass

    async def delete(self, key: str) -> None:
        pass


async def override_get_current_user() -> CurrentUser:
    """Dependency override providing an authenticated admin user context."""
    user_id = uuid.UUID("11111111-1111-1111-1111-111111111111")
    session_id = uuid.UUID("22222222-2222-2222-2222-222222222222")
    user = User(
        id=user_id,
        email="admin@pawguard.org",
        full_name="Benchmark System Admin",
        is_active=True,
    )
    claims = AccessTokenClaims(
        user_id=user_id,
        session_id=session_id,
        roles=["system_admin", "admin", "shelter_manager", "veterinarian", "rescue_agent"],
        jti="bench_jti",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    return CurrentUser(user=user, claims=claims, db=None, redis=MockRedis())  # type: ignore[arg-type]


app.dependency_overrides[get_current_user] = override_get_current_user


def generate_admin_jwt() -> str:
    """Generate a valid test JWT access token with system_admin permissions."""
    return create_access_token(
        user_id=uuid.UUID("11111111-1111-1111-1111-111111111111"),
        session_id=uuid.UUID("22222222-2222-2222-2222-222222222222"),
        roles=["system_admin", "admin", "shelter_manager", "veterinarian", "rescue_agent"],
    )


def classify_endpoint(path: str, method: str, operation_info: dict[str, Any]) -> tuple[str, str]:
    """Classify endpoint into execution category (A..F)."""
    method_upper = method.upper()

    # External dependency check
    ext_keywords = (
        "storage",
        "upload",
        "download",
        "presigned",
        "report",
        "export",
        "webhook",
        "geocoding",
        "stream",
    )
    if any(kw in path for kw in ext_keywords):
        return "D", "Interacts with out-of-process service (S3, Redis PubSub, Geocoding, Worker)"

    # Destructive / State Mutation check
    if method_upper in ("DELETE", "PUT", "PATCH"):
        return "E", "State mutation operation (requires isolated transaction rollback)"
    if method_upper == "POST":
        if not any(kw in path for kw in ("search", "filter", "query", "login", "token")):
            return "E", "State mutation POST operation (requires isolated transaction rollback)"

    # Path parameter check (requires specific resource ID fixture)
    params = operation_info.get("parameters") or []
    has_path_params = any(p.get("in") == "path" for p in params) or "{" in path
    if has_path_params:
        return "C", "Requires specific resource UUID path parameter fixture"

    # Auth check
    security = operation_info.get("security") or []
    if security or "auth" in path or "admin" in path:
        return "B", "Authenticated read endpoint (executed with test JWT token)"

    if method_upper == "GET":
        return "A", "Publicly executable read endpoint"

    return "C", "Requires valid request payload fixture"


async def run_benchmark_async() -> None:
    print("Initializing PawGuard OpenAPI Surface Rigorous Benchmark (Async)...")
    openapi_schema = app.openapi()
    paths = openapi_schema.get("paths", {})

    total_paths = len(paths)
    total_operations = 0
    results: list[dict[str, Any]] = []

    admin_token = generate_admin_jwt()
    auth_headers = {"Authorization": f"Bearer {admin_token}"}

    cat_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
    method_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}

    executed_count = 0
    success_2xx_count = 0
    auth_guarded_count = 0

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        for path, path_item in paths.items():
            for method, operation in path_item.items():
                if method.lower() not in (
                    "get",
                    "post",
                    "put",
                    "patch",
                    "delete",
                    "head",
                    "options",
                ):
                    continue

                total_operations += 1
                method_upper = method.upper()
                method_counts[method_upper] = method_counts.get(method_upper, 0) + 1

                tags = operation.get("tags", ["default"])
                module = tags[0] if tags else "core"
                module_counts[module] = module_counts.get(module, 0) + 1

                category, category_reason = classify_endpoint(path, method, operation)
                cat_counts[category] = cat_counts.get(category, 0) + 1

                op_id = operation.get("operationId", f"{method_upper}_{path}")
                summary = operation.get("summary", "")

                samples_ms: list[float] = []
                status_codes: list[int] = []
                response_bytes_list: list[int] = []
                measured_status = "UNEXECUTED"
                sample_count = 0
                successful_samples = 0
                failed_samples = 0

                is_executable = category in ("A", "B") or (
                    category == "D" and method_upper == "GET" and "{" not in path
                )

                if is_executable:
                    executed_count += 1
                    headers = auth_headers if category in ("B", "D") else {}

                    # Warmup request
                    try:
                        await client.get(path, headers=headers)
                    except Exception:
                        pass

                    # 5 Measured Iterations
                    for _ in range(5):
                        sample_count += 1
                        try:
                            start_time = time.perf_counter()
                            res = await client.get(path, headers=headers)
                            elapsed = (time.perf_counter() - start_time) * 1000.0
                            samples_ms.append(elapsed)
                            status_codes.append(res.status_code)
                            response_bytes_list.append(len(res.content))

                            if 200 <= res.status_code < 300:
                                successful_samples += 1
                            else:
                                failed_samples += 1
                        except Exception:
                            failed_samples += 1

                    if successful_samples > 0:
                        success_2xx_count += 1
                    elif status_codes and any(code in (401, 403) for code in status_codes):
                        auth_guarded_count += 1

                min_ms = round(min(samples_ms), 2) if samples_ms else None
                max_ms = round(max(samples_ms), 2) if samples_ms else None
                mean_ms = round(statistics.mean(samples_ms), 2) if samples_ms else None
                median_ms = round(statistics.median(samples_ms), 2) if samples_ms else None
                primary_status_code = status_codes[0] if status_codes else None
                primary_response_bytes = (
                    response_bytes_list[0] if response_bytes_list else None
                )

                if median_ms is not None:
                    if primary_status_code and 200 <= primary_status_code < 300:
                        if median_ms < 100:
                            measured_status = "200 OK — FAST (<100ms)"
                        elif median_ms < 300:
                            measured_status = "200 OK — ACCEPTABLE (100-300ms)"
                        elif median_ms < 1000:
                            measured_status = "200 OK — INVESTIGATE (300-1000ms)"
                        else:
                            measured_status = "200 OK — SLOW (>1000ms)"
                    else:
                        measured_status = (
                            f"HTTP {primary_status_code} GUARD RESPONSE ({median_ms}ms)"
                        )

                record = {
                    "path": path,
                    "method": method_upper,
                    "operation_id": op_id,
                    "summary": summary,
                    "module": module,
                    "category": category,
                    "category_reason": category_reason,
                    "sample_count": sample_count,
                    "successful_samples": successful_samples,
                    "failed_samples": failed_samples,
                    "status_code": primary_status_code,
                    "min_ms": min_ms,
                    "max_ms": max_ms,
                    "mean_ms": mean_ms,
                    "median_ms": median_ms,
                    "response_bytes": primary_response_bytes,
                    "performance_status": measured_status,
                    "has_auth": bool(operation.get("security")),
                }
                results.append(record)

    output_data = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_paths": total_paths,
            "total_operations": total_operations,
            "executed_count": executed_count,
            "success_2xx_count": success_2xx_count,
            "auth_guarded_count": auth_guarded_count,
            "unexecuted_count": total_operations - executed_count,
            "samples_per_endpoint": 5,
            "category_counts": cat_counts,
            "method_counts": method_counts,
            "module_counts": module_counts,
        },
        "operations": results,
    }

    with open("docs/API_PERFORMANCE_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("\nRigorous Benchmark Surface Audit Complete:")
    print(f"Total Paths: {total_paths}")
    print(f"Total Operations: {total_operations}")
    print(f"Executed Endpoints: {executed_count}")
    print(f"  - 200 OK Business Executions: {success_2xx_count}")
    print(f"  - Auth/Guard Responses: {auth_guarded_count}")
    print(
        f"Unexecuted (Category C/E - Resource UUIDs/Mutations): {total_operations - executed_count}"
    )
    print("Method Breakdown:", method_counts)
    print("Category Classification Breakdown:", cat_counts)
    print("Saved results to docs/API_PERFORMANCE_RESULTS.json")


def main() -> None:
    asyncio.run(run_benchmark_async())


if __name__ == "__main__":
    main()
