"""Lightweight metrics abstraction for request counting and timing.

Can be backed by Prometheus client or a no-op in test/dev environments.
"""

import time
from collections import defaultdict
from typing import Any


class _MetricRegistry:
    """In-memory counter/histogram store. Replace with Prometheus in production."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def increment(self, name: str, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        self._counters[key] += 1

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        self._histograms[key].append(value)

    def snapshot(self) -> dict[str, Any]:
        return {
            "counters": dict(self._counters),
            "histograms": {k: _summarize(v) for k, v in self._histograms.items()},
        }

    @staticmethod
    def _label_key(name: str, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return name
        parts = [f"{k}={v}" for k, v in sorted(labels.items())]
        return f"{name}[{','.join(parts)}]"


def _summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0, "sum": 0.0, "avg": 0.0, "min": 0.0, "max": 0.0}
    return {
        "count": len(values),
        "sum": sum(values),
        "avg": sum(values) / len(values),
        "min": min(values),
        "max": max(values),
    }


_registry = _MetricRegistry()


class MetricsTimer:
    """Context manager for timing code blocks."""

    def __init__(self, name: str, labels: dict[str, str] | None = None) -> None:
        self._name = name
        self._labels = labels
        self._start: float | None = None

    def __enter__(self) -> "MetricsTimer":
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        if self._start is not None:
            elapsed = (time.perf_counter() - self._start) * 1000
            _registry.observe(self._name, elapsed, self._labels)


def increment_counter(name: str, labels: dict[str, str] | None = None) -> None:
    _registry.increment(name, labels)


def observe_histogram(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    _registry.observe(name, value, labels)


def get_metrics_snapshot() -> dict[str, Any]:
    return _registry.snapshot()


def create_timer(name: str, labels: dict[str, str] | None = None) -> MetricsTimer:
    return MetricsTimer(name, labels)
