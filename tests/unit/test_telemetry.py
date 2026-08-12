import threading

from starlette.testclient import TestClient

from pawguard.core.metrics import _MetricRegistry
from pawguard.db.session import collect_db_pool_metrics
from pawguard.main import create_app


def test_metric_registry_prometheus_text_format():
    reg = _MetricRegistry()
    reg.increment("http_requests_total", {"method": "GET", "route": "/api/v1/dogs", "status": "200"}, value=15)
    reg.set_gauge("http_requests_in_flight", 3.0, {"method": "GET"})
    reg.observe("http_request_duration_ms", 12.5, {"method": "GET", "route": "/api/v1/dogs"})

    prom_text = reg.generate_prometheus_text()
    assert "# TYPE http_requests_total counter" in prom_text
    assert 'http_requests_total{method="GET",route="/api/v1/dogs",status="200"} 15' in prom_text
    assert "# TYPE http_requests_in_flight gauge" in prom_text
    assert 'http_requests_in_flight{method="GET"} 3.0' in prom_text
    assert "# TYPE http_request_duration_ms histogram" in prom_text
    assert 'http_request_duration_ms_bucket{le="25.0",method="GET",route="/api/v1/dogs"} 1' in prom_text
    assert 'http_request_duration_ms_bucket{le="+Inf",method="GET",route="/api/v1/dogs"} 1' in prom_text
    assert 'http_request_duration_ms_count{method="GET",route="/api/v1/dogs"} 1' in prom_text


def test_metric_registry_concurrency_thread_safety():
    reg = _MetricRegistry()

    def _worker():
        for _ in range(100):
            reg.increment("thread_counter", {"worker": "t"})
            reg.inc_gauge("thread_gauge", {"worker": "t"}, 1.0)
            reg.dec_gauge("thread_gauge", {"worker": "t"}, 1.0)
            reg.observe("thread_hist", 5.0, {"worker": "t"})

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    snap = reg.snapshot()
    assert snap["counters"]["thread_counter[worker=t]"] == 1000
    assert snap["gauges"]["thread_gauge[worker=t]"] == 0.0
    assert snap["histograms"]["thread_hist[worker=t]"]["count"] == 1000


def test_db_pool_metrics_collector():
    metrics = collect_db_pool_metrics()
    assert "size" in metrics
    assert "checked_in" in metrics
    assert "checked_out" in metrics
    assert "overflow" in metrics


def test_metrics_endpoint_and_tracing_headers():
    app = create_app()
    client = TestClient(app)

    # 1. Hit health endpoint to trigger middleware and trace IDs
    res = client.get("/health", headers={"X-Trace-ID": "custom-trace-12345"})
    assert res.status_code == 200
    assert "X-Request-ID" in res.headers
    assert res.headers["X-Trace-ID"] == "custom-trace-12345"
    assert "X-Span-ID" in res.headers

    # 2. Hit Prometheus /metrics endpoint
    metrics_res = client.get("/metrics")
    assert metrics_res.status_code == 200
    assert "text/plain" in metrics_res.headers["content-type"]
    assert "# TYPE http_requests_total counter" in metrics_res.text
