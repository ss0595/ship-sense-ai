"""SQLite-backed async prediction queue with atomic task pickup."""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
import time
from hashlib import sha256
from logging import Logger
from pathlib import Path
from typing import Callable


LOCK_SECONDS = 45
POLL_SECONDS = 0.4


class PredictionQueue:
    """Durable enough queue for a hackathon demo and worker architecture proof."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS prediction_jobs (
                    id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    attempts INTEGER NOT NULL,
                    locked_by TEXT,
                    locked_until REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )

    def enqueue(self, payload: dict, idempotency_key: str | None = None) -> dict:
        payload_json = json.dumps(payload, sort_keys=True)
        stable_key = idempotency_key.strip() if idempotency_key else sha256(payload_json.encode("utf-8")).hexdigest()
        now = time.time()
        job_id = secrets.token_urlsafe(12)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO prediction_jobs (
                        id, idempotency_key, status, payload_json, attempts, created_at, updated_at
                    )
                    VALUES (?, ?, 'queued', ?, 0, ?, ?)
                    """,
                    (job_id, stable_key, payload_json, now, now),
                )
            except sqlite3.IntegrityError:
                existing = conn.execute(
                    "SELECT id FROM prediction_jobs WHERE idempotency_key = ?",
                    (stable_key,),
                ).fetchone()
                if existing:
                    job_id = existing[0]
        return self.get_job(job_id) or {"id": job_id, "status": "queued"}

    def get_job(self, job_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT id, status, payload_json, result_json, error, attempts, locked_by, created_at, updated_at
                FROM prediction_jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        if not row:
            return None
        result = json.loads(row[3]) if row[3] else None
        return {
            "id": row[0],
            "status": row[1],
            "payload": json.loads(row[2]),
            "result": result,
            "error": row[4],
            "attempts": row[5],
            "locked_by": row[6],
            "created_at": row[7],
            "updated_at": row[8],
        }

    def stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) FROM prediction_jobs GROUP BY status"
            ).fetchall()
        return {
            "workers": len(self._threads),
            "statuses": {status: count for status, count in rows},
        }

    def start_workers(self, count: int, processor: Callable[[dict], dict], logger: Logger) -> None:
        if self._threads:
            return
        for index in range(count):
            worker_id = f"worker-{index + 1}"
            thread = threading.Thread(
                target=self._worker_loop,
                args=(worker_id, processor, logger),
                daemon=True,
                name=f"shipsense-{worker_id}",
            )
            thread.start()
            self._threads.append(thread)
        logger.info("Started %s async prediction workers", len(self._threads))

    def stop_workers(self) -> None:
        self._stop.set()

    def _worker_loop(self, worker_id: str, processor: Callable[[dict], dict], logger: Logger) -> None:
        while not self._stop.is_set():
            job = self._claim_next(worker_id)
            if not job:
                time.sleep(POLL_SECONDS)
                continue
            try:
                result = processor(job["payload"])
                self._complete(job["id"], result)
            except Exception as exc:
                logger.exception("Async prediction job failed: %s", job["id"])
                self._fail(job["id"], str(exc))

    def _claim_next(self, worker_id: str) -> dict | None:
        now = time.time()
        lock_until = now + LOCK_SECONDS
        with sqlite3.connect(self.db_path, isolation_level=None) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                """
                SELECT id, payload_json
                FROM prediction_jobs
                WHERE status = 'queued'
                   OR (status = 'running' AND locked_until < ?)
                ORDER BY created_at
                LIMIT 1
                """,
                (now,),
            ).fetchone()
            if not row:
                conn.execute("COMMIT")
                return None
            conn.execute(
                """
                UPDATE prediction_jobs
                SET status = 'running',
                    locked_by = ?,
                    locked_until = ?,
                    attempts = attempts + 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (worker_id, lock_until, now, row[0]),
            )
            conn.execute("COMMIT")
        return {"id": row[0], "payload": json.loads(row[1])}

    def _complete(self, job_id: str, result: dict) -> None:
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE prediction_jobs
                SET status = 'completed',
                    result_json = ?,
                    error = NULL,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (json.dumps(result), now, job_id),
            )

    def _fail(self, job_id: str, error: str) -> None:
        now = time.time()
        status = "failed"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE prediction_jobs
                SET status = ?,
                    error = ?,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (status, error[:500], now, job_id),
            )
