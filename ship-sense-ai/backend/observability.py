"""Lightweight observability primitives for ShipSense AI."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path


class Metrics:
    """In-memory counters exposed as JSON and Prometheus text."""

    def __init__(self) -> None:
        self.started_at = time.time()
        self._lock = threading.Lock()
        self._requests: dict[tuple[str, str, int], int] = defaultdict(int)
        self._latency_total: dict[tuple[str, str], float] = defaultdict(float)
        self._latency_count: dict[tuple[str, str], int] = defaultdict(int)
        self._trace_limit = max(25, int(os.getenv("SHIPSENSE_TRACE_BUFFER", "160")))
        self._traces: deque[dict] = deque(maxlen=self._trace_limit)

    def record_http(
        self,
        method: str,
        path: str,
        status: int,
        duration_seconds: float,
        trace_id: str | None = None,
        role: str | None = None,
    ) -> None:
        key = (method, path, status)
        base_key = (method, path)
        now = time.time()
        with self._lock:
            self._requests[key] += 1
            self._latency_total[base_key] += duration_seconds
            self._latency_count[base_key] += 1
            self._traces.appendleft(
                {
                    "trace_id": trace_id or "",
                    "service": "shipsense-api",
                    "method": method,
                    "path": path,
                    "status": status,
                    "duration_ms": round(duration_seconds * 1000, 2),
                    "role": role or "anonymous",
                    "timestamp": now,
                }
            )

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
            traces = list(self._traces)
        return {
            "uptime_seconds": int(time.time() - self.started_at),
            "requests": requests,
            "latency": latency,
            "recent_traces": traces,
        }

    def recent_traces(self, limit: int = 25) -> list[dict]:
        safe_limit = max(1, min(limit, self._trace_limit))
        with self._lock:
            return list(self._traces)[:safe_limit]

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


def tail_log_lines(log_path: Path, limit: int = 80) -> list[str]:
    safe_limit = max(1, min(limit, 300))
    if not log_path.exists():
        return ["Log file not found yet."]
    lines = log_path.read_text(errors="replace").splitlines()
    tail = lines[-safe_limit:]
    return tail or ["Log file is empty."]
