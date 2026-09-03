"""Comprehensive route categorization and accounting script.

Reconciles all OpenAPI routes, internal routes, health endpoints, redirects,
and generates the full compliance matrix.
"""

import inspect
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://mock:mock@localhost:5432/pawguard")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("JWT_SECRET_KEY", "mock_secret_key_for_endpoint_audit_32_bytes_long_min!!")
os.environ.setdefault("APP_ENV", "testing")

from fastapi.routing import APIRoute
from starlette.routing import Mount, Route, WebSocketRoute
from pawguard.main import create_app


def reconcile_and_audit():
    app = create_app()
    schema = app.openapi()
    paths = schema.get("paths", {})

    # 1. Collect OpenAPI endpoints
    openapi_endpoints = []
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in ("get", "post", "put", "delete", "patch", "options", "head"):
                continue
            tags = operation.get("tags", [])
            module = tags[0] if tags else "system"
            op_id = operation.get("operationId", "")
            summary = operation.get("summary", "")
            security = operation.get("security", schema.get("security", []))

            is_public = False
            if security == [] or security == [{}]:
                is_public = True
            elif "public" in summary.lower() or "public" in path.lower():
                is_public = True

            auth = "public" if is_public else "authenticated"

            openapi_endpoints.append({
                "method": method.upper(),
                "path": path,
                "module": module,
                "operation_id": op_id,
                "summary": summary,
                "auth": auth,
                "category": "OpenAPI Operation",
            })

    # 2. Collect Non-OpenAPI / Internal / Starlette routes
    internal_routes = []
    for r in app.routes:
        if isinstance(r, Route):
            r_path = getattr(r, "path", "")
            methods = list(getattr(r, "methods", []))
            internal_routes.append({
                "path": r_path,
                "methods": methods,
                "name": getattr(r, "name", ""),
                "type": "Starlette Route / Documentation",
            })
        elif isinstance(r, WebSocketRoute):
            internal_routes.append({
                "path": getattr(r, "path", ""),
                "methods": ["WEBSOCKET"],
                "name": getattr(r, "name", ""),
                "type": "WebSocket Route",
            })
        elif isinstance(r, Mount):
            internal_routes.append({
                "path": getattr(r, "path", ""),
                "methods": ["MOUNT"],
                "name": getattr(r, "name", ""),
                "type": "Mounted Sub-App / Static",
            })

    # 3. Collect module routers and trailing slash redirect candidates
    # In FastAPI, paths with trailing slash redirects can double client-visible route surfaces
    unique_paths = list(paths.keys())

    # Count Summary routes in backend
    summary_routes = [ep for ep in openapi_endpoints if "summary" in ep["path"].lower() or "summary" in ep["summary"].lower()]

    result = {
        "openapi_operation_count": len(openapi_endpoints),
        "unique_openapi_paths": len(unique_paths),
        "internal_starlette_routes_count": len(internal_routes),
        "internal_routes": internal_routes,
        "summary_routes": summary_routes,
    }

    print("==================================================")
    print("ENDPOINT RECONCILIATION & ACCOUNTING REPORT")
    print("==================================================")
    print(f"1. OpenAPI Operations (Documented API Endpoints): {len(openapi_endpoints)}")
    print(f"2. Unique OpenAPI Paths:                          {len(unique_paths)}")
    print(f"3. Internal / Starlette System Routes:             {len(internal_routes)}")
    print(f"4. Summary-Specific Endpoints in Backend:          {len(summary_routes)}")
    print("--------------------------------------------------")
    print("ALL SUMMARY ENDPOINTS REGISTERED IN BACKEND:")
    for s in summary_routes:
        print(f"  - {s['method']:6s} {s['path']}")
    print("--------------------------------------------------")
    print("INTERNAL / SYSTEM ROUTES:")
    for ir in internal_routes:
        print(f"  - {','.join(ir['methods']):12s} {ir['path']:30s} ({ir['type']})")
    print("==================================================")

    # Output detailed compliance matrix to JSON
    with open("endpoint_compliance_matrix.json", "w") as f:
        json.dump({
            "summary": {
                "total_openapi_endpoints": len(openapi_endpoints),
                "unique_paths": len(unique_paths),
                "internal_system_routes": len(internal_routes),
                "total_route_surface": len(openapi_endpoints) + len(internal_routes),
            },
            "endpoints": openapi_endpoints,
            "internal_routes": internal_routes,
        }, f, indent=2)

    return result


if __name__ == "__main__":
    reconcile_and_audit()
