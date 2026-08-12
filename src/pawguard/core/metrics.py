"""Lightweight, bounded metrics abstraction for request counting, gauges, and timing.

Uses fixed-memory constant-space O(1) histogram accumulators with
standard Prometheus-compatible bucket thresholds to prevent unbounded memory growth.
Outputs Prometheus standard exposition format.
"""

import threading
import time
from collections import defaultdict
from typing import Any

DEFAULT_BUCKETS_MS: tuple[float, ...] = (
    5.0,
    10.0,
    25.0,
    50.0,
    100.0,
    250.0,
    500.0,
    1000.0,
    2500.0,
    5000.0,
    10000.0,
)


class _HistogramAccumulator:
    """Fixed-memory O(1) histogram counter. Prevents memory leaks under high throughput."""

    __slots__ = ("buckets", "count", "max", "min", "sum")

    def __init__(self, buckets: tuple[float, ...] = DEFAULT_BUCKETS_MS) -> None:
        self.count: int = 0
        self.sum: float = 0.0
        self.min: float = float("inf")
        self.max: float = 0.0
        self.buckets: dict[float, int] = {b: 0 for b in buckets}

    def observe(self, val: float) -> None:
        self.count += 1
        self.sum += val
        if val < self.min:
            self.min = val
        if val > self.max:
            self.max = val
        for b in self.buckets:
            if val <= b:
                self.buckets[b] += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "sum": round(self.sum, 2),
            "avg": round(self.sum / self.count, 2) if self.count else 0.0,
            "min": round(self.min, 2) if self.count else 0.0,
            "max": round(self.max, 2) if self.count else 0.0,
            "buckets": dict(self.buckets),
        }


class _MetricRegistry:
    """In-memory, fixed-memory bounded metric registry with Prometheus exposition."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
        self._histograms: dict[str, _HistogramAccumulator] = defaultdict(_HistogramAccumulator)

    def increment(self, name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._counters[key] += value

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] = value

    def inc_gauge(self, name: str, labels: dict[str, str] | None = None, delta: float = 1.0) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] += delta

    def dec_gauge(self, name: str, labels: dict[str, str] | None = None, delta: float = 1.0) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._gauges[key] -= delta

    def observe(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        key = self._label_key(name, labels)
        with self._lock:
            self._histograms[key].observe(value)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "gauges": dict(self._gauges),
                "histograms": {k: v.to_dict() for k, v in self._histograms.items()},
            }

    def generate_prometheus_text(self) -> str:
        """Render metrics in standard Prometheus text exposition format (version 0.0.4)."""
        lines: list[str] = []
        with self._lock:
            # 1. Counters
            counters_by_metric: dict[str, list[tuple[dict[str, str], int]]] = defaultdict(list)
            for k, val in self._counters.items():
                m_name, m_labels = self._parse_key(k)
                counters_by_metric[m_name].append((m_labels, val))

            for m_name, entries in sorted(counters_by_metric.items()):
                lines.append(f"# TYPE {m_name} counter")
                for m_labels, val in entries:
                    lbl_str = self._format_prom_labels(m_labels)
                    lines.append(f"{m_name}{lbl_str} {val}")

            # 2. Gauges
            gauges_by_metric: dict[str, list[tuple[dict[str, str], float]]] = defaultdict(list)
            for k, val in self._gauges.items():
                m_name, m_labels = self._parse_key(k)
                gauges_by_metric[m_name].append((m_labels, val))

            for m_name, entries in sorted(gauges_by_metric.items()):
                lines.append(f"# TYPE {m_name} gauge")
                for m_labels, val in entries:
                    lbl_str = self._format_prom_labels(m_labels)
                    lines.append(f"{m_name}{lbl_str} {val}")

            # 3. Histograms
            histograms_by_metric: dict[str, list[tuple[dict[str, str], _HistogramAccumulator]]] = defaultdict(list)
            for k, acc in self._histograms.items():
                m_name, m_labels = self._parse_key(k)
                histograms_by_metric[m_name].append((m_labels, acc))

            for m_name, entries in sorted(histograms_by_metric.items()):
                lines.append(f"# TYPE {m_name} histogram")
                for m_labels, acc in entries:
                    for b_val, count in sorted(acc.buckets.items()):
                        b_labels = dict(m_labels)
                        b_labels["le"] = str(b_val)
                        lbl_str = self._format_prom_labels(b_labels)
                        lines.append(f"{m_name}_bucket{lbl_str} {count}")
                    # +Inf bucket
                    inf_labels = dict(m_labels)
                    inf_labels["le"] = "+Inf"
                    lines.append(f"{m_name}_bucket{self._format_prom_labels(inf_labels)} {acc.count}")
                    lines.append(f"{m_name}_sum{self._format_prom_labels(m_labels)} {round(acc.sum, 4)}")
                    lines.append(f"{m_name}_count{self._format_prom_labels(m_labels)} {acc.count}")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _label_key(name: str, labels: dict[str, str] | None = None) -> str:
        if not labels:
            return name
        parts = [f"{k}={v}" for k, v in sorted(labels.items())]
        return f"{name}[{','.join(parts)}]"

    @staticmethod
    def _parse_key(key: str) -> tuple[str, dict[str, str]]:
        if "[" not in key or not key.endswith("]"):
            return key, {}
        name, rest = key[:-1].split("[", 1)
        labels: dict[str, str] = {}
        for part in rest.split(","):
            if "=" in part:
                k, v = part.split("=", 1)
                labels[k] = v
        return name, labels

    @staticmethod
    def _format_prom_labels(labels: dict[str, str]) -> str:
        if not labels:
            return ""
        parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        return "{" + ",".join(parts) + "}"


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


def increment_counter(name: str, labels: dict[str, str] | None = None, value: int = 1) -> None:
    _registry.increment(name, labels, value)


def set_gauge(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    _registry.set_gauge(name, value, labels)


def inc_gauge(name: str, labels: dict[str, str] | None = None, delta: float = 1.0) -> None:
    _registry.inc_gauge(name, labels, delta)


def dec_gauge(name: str, labels: dict[str, str] | None = None, delta: float = 1.0) -> None:
    _registry.dec_gauge(name, labels, delta)


def observe_histogram(name: str, value: float, labels: dict[str, str] | None = None) -> None:
    _registry.observe(name, value, labels)


def get_metrics_snapshot() -> dict[str, Any]:
    return _registry.snapshot()


def generate_prometheus_metrics() -> str:
    return _registry.generate_prometheus_text()


def create_timer(name: str, labels: dict[str, str] | None = None) -> MetricsTimer:
    return MetricsTimer(name, labels)
