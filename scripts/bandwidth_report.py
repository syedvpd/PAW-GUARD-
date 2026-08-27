#!/usr/bin/env python3
"""PawGuard bandwidth attribution report tool (read-only, measurement only).

Parses the Prometheus exposition served at /metrics and produces:
  * Top-N HTTP routes by response bytes (with request count, avg, P50/P95/P99 latency)
  * SSE byte / message / connection totals
  * Outbound service bytes by destination (public egress = excluding Redis)
  * A Render reconciliation hint (HTTP Responses vs Service-Initiated)

Subcommands:
  snapshot  --url URL --out DIR      fetch /metrics and save a timestamped scrape
  report    --from F --to F --seconds N   delta between two snapshots -> rates

No production data is mutated. The only side effect is writing snapshot files.
This tool never changes application behavior or business logic.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib import error, request

SAMPLE_RE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)"
    r"(?:\{(?P<labels>.*)\})?\s+(?P<value>[-0-9.eE+]+)\s*$"
)
LABEL_RE = re.compile(r'(?P<k>[^=,]+)="(?P<v>(?:[^"\\]|\\.)*)"')


def _parse_labels(raw: str | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not raw:
        return labels
    for m in LABEL_RE.finditer(raw):
        labels[m.group("k")] = m.group("v")
    return labels


def load_metrics(path: Path) -> dict[str, list[tuple[dict[str, str], float]]]:
    """Parse a Prometheus exposition text file into name -> [(labels, value)]."""
    series: dict[str, list[tuple[dict[str, str], float]]] = defaultdict(list)
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = SAMPLE_RE.match(line)
        if not m:
            continue
        try:
            value = float(m.group("value"))
        except ValueError:
            continue
        series[m.group("name")].append((_parse_labels(m.group("labels")), value))
    return series


def _hist_quantile(buckets: list[tuple[float, float]], total: float, q: float) -> float:
    """Interpolate a quantile from (le, cumulative_count) buckets."""
    if total <= 0 or not buckets:
        return 0.0
    buckets = sorted(buckets, key=lambda b: b[0])
    target = q * total
    prev_le, prev_cum = 0.0, 0.0
    for le, cum in buckets:
        if cum >= target:
            if cum == prev_cum:
                return le
            ratio = (target - prev_cum) / (cum - prev_cum)
            return prev_le + ratio * (le - prev_le)
        prev_le, prev_cum = le, cum
    return buckets[-1][0]


def _aggregate_hist(series: dict[str, list], base_name: str, key_fn) -> dict:
    """Aggregate *_bucket series into per-key (le, cum_count) lists + total count."""
    out: dict = defaultdict(lambda: defaultdict(float))
    totals: dict = defaultdict(float)
    for labels, value in series.get(f"{base_name}_bucket", []):
        key = key_fn(labels)
        le = float(labels.get("le", "0"))
        out[key][le] += value
    for labels, value in series.get(f"{base_name}_count", []):
        totals[key_fn(labels)] += value
    result = {}
    for key, le_map in out.items():
        buckets = sorted(le_map.items())
        result[key] = (buckets, totals.get(key, 0.0))
    return result


def compute_http(series: dict, top_n: int) -> list[dict]:
    bytes_series = series.get("pawguard_http_response_bytes_total", [])
    count_series = series.get("http_requests_total", [])
    counts: dict[tuple[str, str, str], float] = defaultdict(float)
    for labels, value in count_series:
        counts[(labels.get("method", ""), labels.get("route", ""), labels.get("status", ""))] += (
            value
        )

    lat = _aggregate_hist(
        series,
        "http_request_duration_ms",
        lambda lb: (lb.get("method", ""), lb.get("route", "")),
    )

    rows: dict[tuple[str, str, str], dict] = {}
    for labels, value in bytes_series:
        method = labels.get("method", "")
        route = labels.get("route", "")
        status = labels.get("status", "")
        key = (method, route, status)
        row = rows.setdefault(key, {"bytes": 0.0, "count": 0.0})
        row["bytes"] += value
        row["count"] += counts.get(key, 0.0)

    result = []
    for (method, route, status), row in rows.items():
        cnt = row["count"] or 0.0
        lat_buckets, lat_total = lat.get((method, route), ([], 0.0))
        result.append(
            {
                "method": method,
                "route": route,
                "status": status,
                "count": cnt,
                "bytes": row["bytes"],
                "avg": (row["bytes"] / cnt) if cnt else 0.0,
                "p50": _hist_quantile(lat_buckets, lat_total, 0.50),
                "p95": _hist_quantile(lat_buckets, lat_total, 0.95),
                "p99": _hist_quantile(lat_buckets, lat_total, 0.99),
            }
        )
    result.sort(key=lambda r: r["bytes"], reverse=True)
    return result[:top_n]


def compute_sse(series: dict) -> dict:
    out = {
        "snapshot_bytes": 0.0,
        "heartbeat_bytes": 0.0,
        "snapshot_msgs": 0.0,
        "heartbeat_msgs": 0.0,
        "active": 0.0,
    }
    for labels, value in series.get("pawguard_sse_bytes_total", []):
        if labels.get("type") == "snapshot":
            out["snapshot_bytes"] += value
        else:
            out["heartbeat_bytes"] += value
    for labels, value in series.get("pawguard_sse_messages_total", []):
        if labels.get("type") == "snapshot":
            out["snapshot_msgs"] += value
        else:
            out["heartbeat_msgs"] += value
    for _labels, value in series.get("pawguard_sse_active_connections", []):
        out["active"] = value  # gauge: take latest
    return out


def compute_outbound(series: dict, exclude: set[str]) -> dict:
    agg: dict[str, dict] = defaultdict(lambda: {"sent": 0.0, "received": 0.0})
    for labels, value in series.get("pawguard_outbound_bytes_total", []):
        dest = labels.get("destination", "")
        if dest in exclude:
            continue
        direction = labels.get("direction", "sent")
        if direction == "received":
            agg[dest]["received"] += value
        else:
            agg[dest]["sent"] += value
    return dict(agg)


def render_delta(before: dict, after: dict, seconds: float, top_n: int) -> None:
    def _delta(name: str) -> float:
        return after.get(name, 0.0) - before.get(name, 0.0)

    print("=" * 78)
    print("PawGuard Bandwidth Attribution Report")
    print(f"Window seconds: {seconds:.0f}  (~{seconds / 86400:.2f} days)")
    print("=" * 78)

    http = compute_http(after, top_n)
    print(f"\nHTTP TOP {len(http)} ROUTES BY RESPONSE BYTES (compressed, cumulative delta)")
    print(f"{'METHOD':6} {'ROUTE':42} {'ST':3} {'REQ':>9} {'TOTAL':>12} {'AVG':>9} {'P95ms':>7}")
    for r in http:
        print(
            f"{r['method']:6} {r['route'][:42]:42} {r['status'][:3]:3} "
            f"{r['count']:>9.0f} {r['bytes']:>12.0f} {r['avg']:>9.0f} {r['p95']:>7.0f}"
        )

    sse = compute_sse(after)
    http_total = sum(r["bytes"] for r in http)
    sse_total = sse["snapshot_bytes"] + sse["heartbeat_bytes"]
    print(f"\nHTTP response bytes (delta): {http_total:,.0f}")
    print(
        f"SSE bytes (delta):           {sse_total:,.0f} "
        f"(snapshot={sse['snapshot_bytes']:,.0f}, heartbeat={sse['heartbeat_bytes']:,.0f})"
    )
    print(
        f"SSE messages:                snapshot={sse['snapshot_msgs']:,.0f}, "
        f"heartbeat={sse['heartbeat_msgs']:,.0f}, active_connections={sse['active']:.0f}"
    )

    meas_http = http_total + sse_total
    rate_http_gb_day = (meas_http / seconds) * 86400 / 1e9 if seconds else 0.0
    print(
        f"\nMEASURED HTTP-equivalent (HTTP + SSE): {meas_http:,.0f} bytes "
        f"-> {rate_http_gb_day:.3f} GB/day"
    )
    print("   Compare this to Render 'HTTP Responses'.")

    out = compute_outbound(after, exclude={"redis"})
    print("\nSERVICE-INITIATED BY DESTINATION (public egress; redis excluded)")
    print(f"{'DEST':14} {'SENT':>14} {'RECEIVED':>14} {'TOTAL':>14}")
    total_sent = total_recv = 0.0
    for dest, v in sorted(
        out.items(), key=lambda kv: kv[1]["sent"] + kv[1]["received"], reverse=True
    ):
        print(
            f"{dest:14} {v['sent']:>14.0f} {v['received']:>14.0f} {v['sent'] + v['received']:>14.0f}"
        )
        total_sent += v["sent"]
        total_recv += v["received"]
    svc_total = total_sent + total_recv
    rate_svc_gb_day = (svc_total / seconds) * 86400 / 1e9 if seconds else 0.0
    print(f"{'TOTAL':14} {total_sent:>14.0f} {total_recv:>14.0f} {svc_total:>14.0f}")
    print(
        f"\nMEASURED Service-Initiated (excl. redis): {svc_total:,.0f} bytes "
        f"-> {rate_svc_gb_day:.3f} GB/day"
    )
    print("   Compare this to Render 'Service-Initiated'.")
    print("   NOTE: redis + PostgreSQL are Render private-network traffic and are")
    print("   excluded from public egress by design.")
    print("=" * 78)


def cmd_snapshot(args: argparse.Namespace) -> None:
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with request.urlopen(args.url, timeout=15) as resp:  # noqa: S310 - local/monitoring URL
            body = resp.read().decode("utf-8")
    except error.URLError as exc:
        print(f"ERROR fetching {args.url}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    dest = out_dir / f"bandwidth_{stamp}.txt"
    dest.write_text(f"# scraped_at {stamp}\n{body}", encoding="utf-8")
    print(f"Saved snapshot: {dest}")


def cmd_report(args: argparse.Namespace) -> None:
    before = load_metrics(Path(args.before))
    after = load_metrics(Path(args.after))
    render_delta(before, after, float(args.seconds), int(args.top))


def main() -> None:
    parser = argparse.ArgumentParser(description="PawGuard bandwidth report tool")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="Fetch /metrics and save a snapshot")
    s.add_argument("--url", default="http://localhost:8000/metrics")
    s.add_argument("--out", default="monitoring/bandwidth_snapshots")
    s.set_defaults(func=cmd_snapshot)

    r = sub.add_parser("report", help="Compute delta between two snapshots")
    r.add_argument("--from", dest="before", required=True)
    r.add_argument("--to", dest="after", required=True)
    r.add_argument(
        "--seconds", type=float, required=True, help="Seconds elapsed between the two snapshots"
    )
    r.add_argument("--top", type=int, default=50)
    r.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
