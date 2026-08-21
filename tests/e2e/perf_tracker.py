"""Performance tracker: records latency for every endpoint call."""

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class EndpointResult:
    module: str
    method: str
    path: str
    status_code: int
    expected_status: int
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    max_ms: float = 0.0
    result: str = "NOT_TESTED"
    failure_reason: str = ""
    latencies: list = field(default_factory=list)

    @property
    def is_pass(self) -> bool:
        return self.result == "PASS"


class PerformanceTracker:
    def __init__(self):
        self.results: list[EndpointResult] = []
        self._current: EndpointResult | None = None

    def start(self, module: str, method: str, path: str):
        self._current = EndpointResult(
            module=module,
            method=method,
            path=path,
            status_code=0,
            expected_status=0,
        )

    def record(self, status_code: int, expected_status: int, latency_ms: float):
        if self._current:
            self._current.status_code = status_code
            self._current.expected_status = expected_status
            self._current.latencies.append(latency_ms)

    def finish(self, result: str, reason: str = ""):
        if self._current:
            self._current.result = result
            self._current.failure_reason = reason
            if self._current.latencies:
                lats = sorted(self._current.latencies)
                n = len(lats)
                self._current.p50_ms = lats[n // 2]
                self._current.p95_ms = lats[int(n * 0.95)] if n > 1 else lats[0]
                self._current.max_ms = max(lats)
            self.results.append(self._current)
            self._current = None

    def summary(self) -> dict:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.result == "PASS")
        failed = sum(1 for r in self.results if r.result == "FAIL")
        blocked = sum(1 for r in self.results if r.result == "BLOCKED")
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "blocked": blocked,
            "coverage": f"{(passed + failed + blocked) / max(total, 1) * 100:.1f}%",
        }

    def save(self, path: str):
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        csv_path = out.with_suffix(".csv")
        with open(csv_path, "w") as f:
            f.write(
                "module,method,path,status_code,expected_status,p50_ms,p95_ms,max_ms,result,failure_reason\n"
            )
            for r in self.results:
                f.write(
                    f"{r.module},{r.method},{r.path},{r.status_code},{r.expected_status},"
                    f"{r.p50_ms:.2f},{r.p95_ms:.2f},{r.max_ms:.2f},{r.result},{r.failure_reason}\n"
                )
        json_path = out.with_suffix(".json")
        with open(json_path, "w") as f:
            json.dump(
                [
                    {
                        "module": r.module,
                        "method": r.method,
                        "path": r.path,
                        "status_code": r.status_code,
                        "expected_status": r.expected_status,
                        "p50_ms": r.p50_ms,
                        "p95_ms": r.p95_ms,
                        "max_ms": r.max_ms,
                        "result": r.result,
                        "failure_reason": r.failure_reason,
                    }
                    for r in self.results
                ],
                f,
                indent=2,
            )
        return self.summary()


tracker = PerformanceTracker()
