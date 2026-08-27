"""Universal OpenAPI/Swagger Automated API Tester & Latency Benchmark Tool.

Supports ANY backend project (FastAPI, Express.js, Django, Spring Boot, NestJS, Go, Laravel).
Automatically fetches OpenAPI JSON specs from remote URLs or local files, constructs mock
request payloads, executes cold (1st call) vs warm (2nd call) performance testing, and
generates comprehensive Markdown & JSON performance reports.
"""

import argparse
import asyncio
import json
import os
import sys
import time
from typing import Any

import httpx


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
    """Retrieve OpenAPI specification from local file or HTTP endpoint."""
    if file_path and os.path.exists(file_path):
        with open(file_path, encoding="utf-8") as f:
            return json.load(f)

    if url:
        openapi_url = url.rstrip("/") + "/openapi.json"
        print(f"📡 Fetching OpenAPI schema from {openapi_url}...")
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.get(openapi_url)
                if resp.status_code == 200:
                    return resp.json()
            except Exception as e:
                print(f"⚠️ Could not fetch from {openapi_url}: {e}")

    # Fallback to local openapi.json if exists
    if os.path.exists("openapi.json"):
        with open("openapi.json", encoding="utf-8") as f:
            return json.load(f)

    raise FileNotFoundError("Could not find openapi.json locally or fetch it via --url")


async def run_universal_tester(
    target_url: str,
    spec_path: str | None = None,
    token: str | None = None,
    output_prefix: str = "api_benchmark",
    max_latency_ms: float = 100.0,
):
    print("=" * 110)
    print("🌐 UNIVERSAL OPENAPI AUTOMATED TESTER & PERFORMANCE BENCHMARK TOOL")
    print("=" * 110)
    print(f"🎯 Target Server URL : {target_url}")
    print(f"⏱️ SLA Threshold     : < {max_latency_ms} ms")
    print("-" * 110)

    try:
        openapi = await fetch_openapi_spec(target_url, spec_path)
    except Exception as e:
        print(f"❌ Error loading OpenAPI spec: {e}")
        sys.exit(1)

    title = openapi.get("info", {}).get("title", "Backend API")
    version = openapi.get("info", {}).get("version", "1.0")
    paths = openapi.get("paths", {})
    components_schemas = openapi.get("components", {}).get("schemas", {})

    total_routes = sum(
        len([m for m in methods.keys() if m.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}])
        for methods in paths.values()
    )
    print(f"📋 Project          : {title} (v{version})")
    print(f"🔍 Discovered Routes : {total_routes} endpoints")
    print("🚀 Starting execution...")
    print("-" * 110)

    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    results = []

    async with httpx.AsyncClient(base_url=target_url.rstrip("/"), timeout=15.0) as client:
        for path_pattern, methods in paths.items():
            # Substitute path params
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

                # Build body for POST/PUT/PATCH
                json_body = None
                if method in {"POST", "PUT", "PATCH"}:
                    request_body_info = op_info.get("requestBody", {})
                    content_info = request_body_info.get("content", {}).get("application/json", {})
                    if "schema" in content_info:
                        json_body = _generate_mock_payload(
                            content_info["schema"], components_schemas
                        )

                # --- 1st Call (Cold / Database Hit) ---
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
                cold_ms = (time.perf_counter() - start1) * 1000.0

                # --- 2nd Call (Warm / Redis or In-Memory Cache Hit) ---
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
                warm_ms = (time.perf_counter() - start2) * 1000.0

                speedup = (cold_ms / warm_ms) if warm_ms > 0 else 1.0
                is_passed = warm_ms <= max_latency_ms

                item = {
                    "method": method,
                    "path": path_pattern,
                    "status": status2 or status1,
                    "cold_ms": round(cold_ms, 2),
                    "warm_ms": round(warm_ms, 2),
                    "speedup_ratio": round(speedup, 1),
                    "passed": is_passed,
                }
                results.append(item)

    # Output Table
    print(
        f"{'Method':<6} | {'Endpoint Path':<45} | {'Status':<6} | {'1st Hit (Cold)':<14} | {'2nd Hit (Warm)':<14} | {'Speedup':<9} | {'Result'}"
    )
    print("-" * 115)

    passed_count = 0
    for r in results:
        m_str = f"{r['method']:<6}"
        p_str = f"{r['path'][:45]:<45}"
        s_str = f"HTTP {r['status']}"
        cold_str = f"{r['cold_ms']} ms"
        warm_str = f"{r['warm_ms']} ms"
        speed_str = f"{r['speedup_ratio']}x"
        badge = (
            f"✅ PASSED (<{int(max_latency_ms)}ms)"
            if r["passed"]
            else f"⚠️ (> {int(max_latency_ms)}ms)"
        )
        if r["passed"]:
            passed_count += 1

        print(
            f"{m_str} | {p_str} | {s_str:<6} | {cold_str:<14} | {warm_str:<14} | {speed_str:<9} | {badge}"
        )

    print("-" * 115)
    pass_pct = (passed_count / len(results) * 100.0) if results else 0.0
    print(
        f"📊 SUMMARY: {passed_count}/{len(results)} endpoints passed sub-{int(max_latency_ms)}ms target ({pass_pct:.1f}% Compliance)"
    )
    print("=" * 110)

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
        f.write(f"- **Target URL**: {target_url}\n")
        f.write(f"- **Total Endpoints Tested**: {len(results)}\n")
        f.write(f"- **Sub-{int(max_latency_ms)}ms Pass Rate**: {pass_pct:.1f}%\n\n")
        f.write(
            "| Method | Path | Status | 1st Call (Cold) | 2nd Call (Warm) | Speedup | Result |\n"
        )
        f.write("|---|---|---|---|---|---|---|\n")
        for r in results:
            f.write(
                f"| `{r['method']}` | `{r['path']}` | HTTP {r['status']} | {r['cold_ms']} ms | {r['warm_ms']} ms | {r['speedup_ratio']}x | {'✅ PASSED' if r['passed'] else '⚠️ SLOW'} |\n"
            )

    print(f"📝 JSON Export saved to : {json_output}")
    print(f"📄 Markdown Report saved: {md_output}")


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
