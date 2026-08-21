"""Regression tests for Cycle-1 S5: rate-limit the public grievance endpoints.

Public POST /grievance (submit_complaint) and POST /grievance/feedback
(submit_feedback) were unmetered, leaving them open to spam/abuse. Both now
carry a Redis-backed sliding-window limit (10/hour per key).
"""

import pytest
from httpx import AsyncClient

COMPLAINT = {
    "reporter_name": "Public User",
    "reporter_phone": "+1122334455",
    "complaint_type": "service_delay",
    "details": "Rescue took too long to arrive.",
}


@pytest.mark.asyncio
class TestGrievanceRateLimit:
    async def test_complaint_submission_rate_limited(self, client: AsyncClient) -> None:
        for _ in range(10):
            resp = await client.post("/api/v1/grievance", json=COMPLAINT)
            assert resp.status_code == 201
        overflow = await client.post("/api/v1/grievance", json=COMPLAINT)
        assert overflow.status_code == 429

    async def test_feedback_submission_rate_limited(self, client: AsyncClient) -> None:
        payload = {"rating": 5, "comments": "Great service"}
        for _ in range(10):
            resp = await client.post("/api/v1/grievance/feedback", json=payload)
            assert resp.status_code == 201
        overflow = await client.post("/api/v1/grievance/feedback", json=payload)
        assert overflow.status_code == 429
