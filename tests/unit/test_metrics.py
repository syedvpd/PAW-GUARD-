"""Tests for bounded metrics and route cardinality control."""

from unittest.mock import MagicMock
from uuid import uuid4

from pawguard.core.metrics import (
    _HistogramAccumulator,
    _MetricRegistry,
)
from pawguard.core.middleware import _resolve_route_path


def test_histogram_accumulator_fixed_memory():
    acc = _HistogramAccumulator(buckets=(10.0, 50.0, 100.0, 500.0))
    for i in range(1000):
        acc.observe(float(i % 200))

    data = acc.to_dict()
    assert data["count"] == 1000
    assert data["min"] == 0.0
    assert data["max"] == 199.0
    assert "buckets" in data
    assert sum(data["buckets"].values()) >= 1000
    # Object slots verify memory is strictly bounded (no unbounded list)
    assert not hasattr(acc, "__dict__")


def test_metric_registry_bounded_labels():
    reg = _MetricRegistry()
    for _ in range(50):
        reg.increment("test_counter", {"route": "/api/v1/dogs/{id}", "status": "200"})
        reg.observe("test_histogram", 45.2, {"route": "/api/v1/dogs/{id}", "status": "200"})

    snap = reg.snapshot()
    assert "counters" in snap
    assert "histograms" in snap
    assert snap["counters"]["test_counter[route=/api/v1/dogs/{id},status=200]"] == 50
    hist_entry = snap["histograms"]["test_histogram[route=/api/v1/dogs/{id},status=200]"]
    assert hist_entry["count"] == 50
    assert hist_entry["avg"] == 45.2


def test_resolve_route_path_replaces_uuids():
    req = MagicMock()
    req.scope = {}
    dog_id = uuid4()
    req.url.path = f"/api/v1/dogs/{dog_id}"

    resolved = _resolve_route_path(req)
    assert resolved == "/api/v1/dogs/{id}"
    assert str(dog_id) not in resolved


def test_resolve_route_path_prefers_matched_route():
    req = MagicMock()
    matched_route = MagicMock()
    matched_route.path = "/api/v1/dogs/{dog_id}"
    req.scope = {"route": matched_route}
    req.url.path = "/api/v1/dogs/123e4567-e89b-12d3-a456-426614174000"

    resolved = _resolve_route_path(req)
    assert resolved == "/api/v1/dogs/{dog_id}"
