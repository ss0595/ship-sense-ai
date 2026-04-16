"""Lightweight observability primitives for ShipSense AI."""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class Metrics:
    """In-memory counters exposed as JSON and Prometheus text."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_total: dict[tuple[str, str], float] = defaultdict(float)
        self._latency_count: dict[tuple[str, str], int] = defaultdict(int)

    def record_http(self, method: str, path: str, status: int, duration_seconds: float) -> None:
        key = (method, path, status)
        base_key = (method, path)
        with self._lock:
            self._requests[key] += 1
            self._latency_total[base_key] += duration_seconds
            self._latency_count[base_key] += 1

    def snapshot(self) -> dict:
        with self._lock:
            requests = [
                {"method": method, "path": path, "status": status, "count": count}
                for (method, path, status), count in sorted(self._requests.items())
            ]
            latency = []
            for (method, path), total in sorted(self._latency_total.items()):
                count = self._latency_count[(method, path)]
                latency.append(
                    {
                        "method": method,
                        "path": path,
                        "average_ms": round((total / max(count, 1)) * 1000, 2),
                        "count": count,
                    }
                )
        return {
            "uptime_seconds": int(time.time() - self.started_at),
            "requests": requests,
            "latency": latency,
        }

    def prometheus(self, queue_stats: dict | None = None) -> str:
        snapshot = self.snapshot()
        lines = [
            "# HELP shipsense_uptime_seconds Seconds since ShipSense started.",
            "# TYPE shipsense_uptime_seconds gauge",
            f"shipsense_uptime_seconds {snapshot['uptime_seconds']}",
            "# HELP shipsense_http_requests_total HTTP responses by method, path, and status.",
            "# TYPE shipsense_http_requests_total counter",
        ]
        for item in snapshot["requests"]:
            lines.append(
                "shipsense_http_requests_total"
                f'{{method="{item["method"]}",path="{item["path"]}",status="{item["status"]}"}} {item["count"]}'
            )

        lines.extend(
            [
                "# HELP shipsense_http_latency_average_ms Average HTTP latency in milliseconds.",
                "# TYPE shipsense_http_latency_average_ms gauge",
            ]
        )
        for item in snapshot["latency"]:
            lines.append(
                "shipsense_http_latency_average_ms"
                f'{{method="{item["method"]}",path="{item["path"]}"}} {item["average_ms"]}'
            )

        if queue_stats:
            lines.extend(
                [
                    "# HELP shipsense_prediction_jobs Jobs by async queue status.",
                    "# TYPE shipsense_prediction_jobs gauge",
                ]
            )
            for status, count in sorted(queue_stats.get("statuses", {}).items()):
                lines.append(f'shipsense_prediction_jobs{{status="{status}"}} {count}')

        return "\n".join(lines) + "\n"


METRICS = Metrics()
