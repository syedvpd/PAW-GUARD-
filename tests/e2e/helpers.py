"""Shared helpers for E2E tests."""

import time
import uuid

from tests.e2e.perf_tracker import tracker


async def call(client, module, method, path, headers=None, json=None, params=None, expected=200):
    """Call an endpoint, measure latency, record result."""
    tracker.start(module, method.upper(), path)
    t0 = time.perf_counter()
    try:
        r = await client.request(
            method, path, headers=headers, json=json, params=params, timeout=30
        )
        latency = (time.perf_counter() - t0) * 1000
        tracker.record(r.status_code, expected, latency)
        if r.status_code == expected:
            tracker.finish("PASS")
        else:
            body = r.text[:500]
            tracker.finish("FAIL", f"status={r.status_code} expected={expected} body={body}")
        return r
    except Exception as e:
        latency = (time.perf_counter() - t0) * 1000
        tracker.record(0, expected, latency)
        tracker.finish("FAIL", f"exception={e}")
        raise


def uid():
    return uuid.uuid4().hex[:8]
