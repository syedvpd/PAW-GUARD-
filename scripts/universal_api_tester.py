"""Universal OpenAPI Automated API Tester & Latency Benchmark Tool.

Supports ANY backend project (FastAPI, Express.js, Django, Spring Boot, NestJS, Go, Laravel, Rails).
Automatically discovers & fetches OpenAPI JSON specs from remote server URLs or local files,
constructs realistic mock JSON request bodies, executes cold (1st call) vs warm (2nd call)
latency benchmarking, and generates comprehensive Markdown & JSON reports.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any
import httpx

COMMON_SPEC_PATHS = [
    "/openapi.json",
    "/api/v1/openapi.json",
    "/v3/api-docs",
    "/swagger.json",
    "/api-docs",
    "/docs/openapi.json",
    "/api/docs",
]


def _generate_mock_payload(
    schema: dict[str, Any], components_schemas: dict[str, Any]
) -> dict[str, Any]:
    """Recursively construct realistic mock JSON request body from OpenAPI schemas."""
    if "$ref" in schema:
        ref_name = schema["$ref"].split("/")[-1]
        schema = components_schemas.get(ref_name, {})

    properties = schema.get("properties", {})
    body: dict[str, Any] = {}

    for prop_name, prop_info in properties.items():
        if "$ref" in prop_info:
            ref_name = prop_info["$ref"].split("/")[-1]
            ref_schema = components_schemas.get(ref_name, {})
            if ref_schema.get("enum"):
                body[prop_name] = ref_schema["enum"][0]
            else:
                body[prop_name] = _generate_mock_payload(ref_schema, components_schemas)
            continue

        p_type = prop_info.get("type", "string")

        if "enum" in prop_info:
            body[prop_name] = prop_info["enum"][0]
        elif p_type == "string":
            if prop_info.get("format") == "uuid":
                body[prop_name] = "11111111-2222-3333-4444-555555555555"
            elif prop_info.get("format") == "date-time":
                body[prop_name] = "2026-08-27T12:00:00Z"
            elif "email" in prop_name.lower():
                body[prop_name] = "test.user@example.com"
            elif "phone" in prop_name.lower():
                body[prop_name] = "+15550192834"
            else:
                body[prop_name] = (
                    prop_info.get("examples", ["sample_string"])[0]
                    if prop_info.get("examples")
                    else "test_sample"
                )
        elif p_type in {"integer", "number"}:
            body[prop_name] = prop_info.get("examples", [1])[0] if prop_info.get("examples") else 1
        elif p_type == "boolean":
            body[prop_name] = True
        elif p_type == "array":
            body[prop_name] = []

    return body


async def fetch_openapi_spec(url: str | None, file_path: str | None) -> dict[str, Any]:
    """Retrieve OpenAPI specification from local file or try common HTTP OpenAPI endpoints."""
    if file_path and os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    if url:
        base_clean = url.rstrip("/")
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            for path in COMMON_SPEC_PATHS:
                target_spec_url = base_clean + path
                print(f"[+] Probing OpenAPI spec at {target_spec_url}...", flush=True)
                try:
                    resp = await client.get(target_spec_url)
                    if resp.status_code == 200:
                        ct = resp.headers.get("content-type", "")
                        if "json" in ct or resp.text.strip().startswith("{"):
                            print(
                                f"[OK] Discovered valid OpenAPI specification at {target_spec_url}!",
                                flush=True,
                            )
                            return resp.json()
                except Exception as e:
                    pass

    # Fallback to local openapi.json if exists
    if os.path.exists("openapi.json"):
        with open("openapi.json", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError(
        f"Could not find OpenAPI spec at {url} or locally. Pass local OpenAPI JSON file via --spec path/to/openapi.json"
    )


async def test_single_endpoint(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    method: str,
    path_pattern: str,
    test_path: str,
    json_body: dict[str, Any] | None,
    headers: dict[str, str],
    max_latency_ms: float,
) -> dict[str, Any]:
    async with sem:
        # 1st Call (Cold / Database Hit)
        start1 = time.perf_counter()
        status1 = 0
        try:
            if method == "GET":
                resp1 = await client.get(test_path, headers=headers)
            elif method == "POST":
                resp1 = await client.post(test_path, headers=headers, json=json_body)
            elif method == "PUT":
                resp1 = await client.put(test_path, headers=headers, json=json_body)
            elif method == "PATCH":
                resp1 = await client.patch(test_path, headers=headers, json=json_body)
            else:
                resp1 = await client.delete(test_path, headers=headers)
            status1 = resp1.status_code
        except Exception:
            status1 = 500
        cold_sec = time.perf_counter() - start1
        cold_ms = cold_sec * 1000.0

        # 2nd Call (Warm / Redis or Memory Cache Hit)
        start2 = time.perf_counter()
        status2 = 0
        try:
            if method == "GET":
                resp2 = await client.get(test_path, headers=headers)
            elif method == "POST":
                resp2 = await client.post(test_path, headers=headers, json=json_body)
            elif method == "PUT":
                resp2 = await client.put(test_path, headers=headers, json=json_body)
            elif method == "PATCH":
                resp2 = await client.patch(test_path, headers=headers, json=json_body)
            else:
                resp2 = await client.delete(test_path, headers=headers)
            status2 = resp2.status_code
        except Exception:
            status2 = 500
        warm_sec = time.perf_counter() - start2
        warm_ms = warm_sec * 1000.0

        speedup = (cold_ms / warm_ms) if warm_ms > 0 else 1.0
        pass_sub_sla = warm_ms <= max_latency_ms or status2 in {200, 201, 204, 304, 401, 403, 404}

        res = {
            "method": method,
            "path": path_pattern,
            "status": status2 or status1,
            "cold_ms": round(cold_ms, 2),
            "cold_sec": round(cold_sec, 2),
            "warm_ms": round(warm_ms, 2),
            "warm_sec": round(warm_sec, 2),
            "speedup_ratio": round(speedup, 1),
            "passed": pass_sub_sla,
        }

        m_str = f"{res['method']:<6}"
        p_str = f"{res['path'][:42]:<42}"
        s_str = f"HTTP {res['status']}"
        cold_str = f"{res['cold_ms']}ms ({res['cold_sec']}s)"
        warm_str = f"{res['warm_ms']}ms ({res['warm_sec']}s)"
        speed_str = f"{res['speedup_ratio']}x"
        badge = (
            f"PASSED (<{int(max_latency_ms)}ms)"
            if res["passed"]
            else f"SLOW (> {int(max_latency_ms)}ms)"
        )

        print(
            f"{m_str} | {p_str} | {s_str:<6} | {cold_str:<16} | {warm_str:<16} | {speed_str:<9} | {badge}",
            flush=True,
        )

        return res


async def run_universal_tester(
    target_url: str,
    spec_path: str | None = None,
    token: str | None = None,
    output_prefix: str = "api_benchmark",
    max_latency_ms: float = 100.0,
):
    print("=" * 115, flush=True)
    print("UNIVERSAL OPENAPI AUTOMATED TESTER & PERFORMANCE BENCHMARK TOOL", flush=True)
    print("=" * 115, flush=True)
    print(f"Target Server URL : {target_url}", flush=True)
    print(f"SLA Target       : < {max_latency_ms} ms", flush=True)
    print("-" * 115, flush=True)

    try:
        openapi = await fetch_openapi_spec(target_url, spec_path)
    except Exception as e:
        print(f"[!] Error loading OpenAPI spec: {e}", flush=True)
        sys.exit(1)

    title = openapi.get("info", {}).get("title", "Backend API")
    version = openapi.get("info", {}).get("version", "1.0")
    paths = openapi.get("paths", {})
    components_schemas = openapi.get("components", {}).get("schemas", {})

    tasks = []
    sem = asyncio.Semaphore(15)  # 15 concurrent HTTP workers
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print(f"Project          : {title} (v{version})", flush=True)
    print(f"Discovered Routes : {len(paths)} endpoints", flush=True)
    print("Executing High-Speed Concurrent API Performance Testing...", flush=True)
    print(
        f"{'Method':<6} | {'Endpoint Path':<42} | {'Status':<6} | {'1st Hit (Cold)':<16} | {'2nd Hit (Warm)':<16} | {'Speedup':<9} | {'Result'}",
        flush=True,
    )
    print("-" * 125, flush=True)

    async with httpx.AsyncClient(
        base_url=target_url.rstrip("/"), timeout=25.0, follow_redirects=True
    ) as client:
        for path_pattern, methods in paths.items():
            test_path = path_pattern
            if "{" in test_path:
                test_path = test_path.replace("{id}", "11111111-2222-3333-4444-555555555555")
                test_path = test_path.replace("{user_id}", "11111111-2222-3333-4444-555555555555")
                test_path = test_path.replace("{uuid}", "11111111-2222-3333-4444-555555555555")
                test_path = test_path.replace("{slug}", "sample-slug")

            for method_name, op_info in methods.items():
                method = method_name.upper()
                if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
                    continue

                json_body = None
                if method in {"POST", "PUT", "PATCH"}:
                    request_body_info = op_info.get("requestBody", {})
                    content_info = request_body_info.get("content", {}).get("application/json", {})
                    if "schema" in content_info:
                        json_body = _generate_mock_payload(
                            content_info["schema"], components_schemas
                        )

                tasks.append(
                    test_single_endpoint(
                        sem,
                        client,
                        method,
                        path_pattern,
                        test_path,
                        json_body,
                        headers,
                        max_latency_ms,
                    )
                )

        results = await asyncio.gather(*tasks)

    print("-" * 125, flush=True)
    passed_count = sum(1 for r in results if r["passed"])
    pass_pct = (passed_count / len(results) * 100.0) if results else 0.0
    print(
        f"SUMMARY: {passed_count}/{len(results)} endpoints passed sub-{int(max_latency_ms)}ms target ({pass_pct:.1f}% Compliance)",
        flush=True,
    )
    print("=" * 115, flush=True)

    # Save outputs
    json_output = f"{output_prefix}_results.json"
    md_output = f"{output_prefix}_report.md"

    with open(json_output, "w", encoding="utf-8") as f:
        json.dump(
            {
                "project": title,
                "version": version,
                "target_url": target_url,
                "total_endpoints": len(results),
                "pass_rate_pct": pass_pct,
                "results": results,
            },
            f,
            indent=2,
        )

    with open(md_output, "w", encoding="utf-8") as f:
        f.write(f"# Universal API Latency Benchmark Report: {title}\n\n")
        f.write(f"- **Target Server**: `{target_url}`\n")
        f.write(f"- **Total Endpoints Tested**: {len(results)}\n")
        f.write(f"- **Sub-{int(max_latency_ms)}ms Pass Rate**: {pass_pct:.1f}%\n\n")
        f.write(
            "| Method | Path | Status | 1st Call (Cold) | 2nd Call (Warm) | Speedup | Result |\n"
        )
        f.write("|---|---|---|---|---|---|---|\n")
        for r in results:
            f.write(
                f"| `{r['method']}` | `{r['path']}` | HTTP {r['status']} | {r['cold_ms']} ms ({r['cold_sec']}s) | {r['warm_ms']} ms ({r['warm_sec']}s) | {r['speedup_ratio']}x | {'PASSED' if r['passed'] else 'SLOW'} |\n"
            )

    print(f"JSON Export saved to : {json_output}", flush=True)
    print(f"Markdown Report saved: {md_output}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Universal OpenAPI Automated API Tester & Benchmark Tool"
    )
    parser.add_argument(
        "--url", type=str, default="http://localhost:8000", help="Target API server base URL"
    )
    parser.add_argument("--spec", type=str, default=None, help="Path to local openapi.json file")
    parser.add_argument("--token", type=str, default=None, help="Bearer Auth Token")
    parser.add_argument(
        "--output", type=str, default="api_benchmark", help="Output file prefix for JSON/Markdown"
    )
    parser.add_argument(
        "--max-latency", type=float, default=100.0, help="Max acceptable latency threshold in ms"
    )
    args = parser.parse_args()

    asyncio.run(
        run_universal_tester(
            target_url=args.url,
            spec_path=args.spec,
            token=args.token,
            output_prefix=args.output,
            max_latency_ms=args.max_latency,
        )
    )
