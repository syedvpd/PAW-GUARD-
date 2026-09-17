"""PawGuard OpenAPI API Performance Benchmark Script.

Scans the complete FastAPI OpenAPI surface across all registered modules (700+ paths / 900+ routes),
classifies endpoints into execution categories (A..F), benchmarks latencies, query behavior, and response sizes,
and outputs structured results to docs/API_PERFORMANCE_RESULTS.json.
"""

import json
import time
from typing import Any

from fastapi.testclient import TestClient

from pawguard.main import app


def classify_endpoint(path: str, method: str, operation_info: dict[str, Any]) -> tuple[str, str]:
    """Classify endpoint into execution category (A..F)."""
    method_upper = method.upper()

    # Destructive check
    if method_upper in ("DELETE", "PUT", "PATCH"):
        if any(kw in path for kw in ("soft-delete", "delete", "purge", "destroy")):
            return "E", "Destructive mutation operation"
        return "E", "State mutation operation (requires safe transaction rollbacks)"

    # Auth check
    security = operation_info.get("security") or []
    params = operation_info.get("parameters") or []

    # Check for path parameters (requires resource IDs)
    has_path_params = any(p.get("in") == "path" for p in params) or "{" in path

    if has_path_params:
        return "C", "Requires specific resource ID fixture"

    if security or "auth" in path or "admin" in path:
        return "B", "Requires authenticated role context"

    if method_upper == "GET":
        return "A", "Automatically executable read endpoint"

    return "C", "Requires valid request payload fixture"


def run_benchmark() -> None:
    print("Initializing PawGuard OpenAPI Surface Benchmark...")
    openapi_schema = app.openapi()
    paths = openapi_schema.get("paths", {})

    total_paths = len(paths)
    total_operations = 0
    results: list[dict[str, Any]] = []

    client = TestClient(app)

    cat_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0, "F": 0}
    method_counts: dict[str, int] = {}
    module_counts: dict[str, int] = {}

    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method.lower() not in ("get", "post", "put", "patch", "delete", "head", "options"):
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

            # Execute safe Category A endpoints
            measured_latency_ms: float | None = None
            status_code: int | None = None
            response_bytes: int | None = None
            measured_status = "UNMEASURED"

            if category == "A":
                try:
                    start_time = time.perf_counter()
                    response = client.get(path)
                    elapsed = (time.perf_counter() - start_time) * 1000.0
                    measured_latency_ms = round(elapsed, 2)
                    status_code = response.status_code
                    response_bytes = len(response.content)

                    if measured_latency_ms < 100:
                        measured_status = "FAST (<100ms)"
                    elif measured_latency_ms < 300:
                        measured_status = "ACCEPTABLE (100-300ms)"
                    elif measured_latency_ms < 1000:
                        measured_status = "INVESTIGATE (300-1000ms)"
                    elif measured_latency_ms < 3000:
                        measured_status = "SLOW (1-3s)"
                    else:
                        measured_status = "CRITICAL (>3s)"
                except Exception as exc:
                    measured_status = f"FAILED: {exc!s}"

            record = {
                "path": path,
                "method": method_upper,
                "operation_id": op_id,
                "summary": summary,
                "module": module,
                "category": category,
                "category_reason": category_reason,
                "status_code": status_code,
                "latency_ms": measured_latency_ms,
                "response_bytes": response_bytes,
                "performance_status": measured_status,
                "has_auth": bool(operation.get("security")),
            }
            results.append(record)

    output_data = {
        "metadata": {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_paths": total_paths,
            "total_operations": total_operations,
            "category_counts": cat_counts,
            "method_counts": method_counts,
            "module_counts": module_counts,
        },
        "operations": results,
    }

    with open("docs/API_PERFORMANCE_RESULTS.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print("\nBenchmark Surface Audit Complete:")
    print(f"Total Paths: {total_paths}")
    print(f"Total Operations: {total_operations}")
    print("Method Breakdown:", method_counts)
    print("Category Classification Breakdown:", cat_counts)
    print("Saved results to docs/API_PERFORMANCE_RESULTS.json")


if __name__ == "__main__":
    run_benchmark()
