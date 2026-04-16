"""Async prediction queue with Redis primary backend and SQL fallback."""

from __future__ import annotations

import json
import os
import secrets
import socket
import threading
import time
from hashlib import sha256
from logging import Logger
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from backend.sql_backend import SQLBackend


LOCK_SECONDS = 45
POLL_SECONDS = 0.4
REDIS_BLOCK_SECONDS = 1


class PredictionQueue:
    """Queue facade that prefers Redis when configured and otherwise uses SQL."""

    def __init__(self, db_path: Path, database: SQLBackend | None = None) -> None:
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        backend_mode = os.getenv("SHIPSENSE_QUEUE_BACKEND", "auto").strip().lower()
        redis_url = os.getenv("SHIPSENSE_REDIS_URL", "").strip()
        if backend_mode == "redis" or (backend_mode == "auto" and redis_url):
            self._backend: _QueueBackend = _RedisQueueBackend(redis_url or "redis://127.0.0.1:6379/0")
        else:
            self._backend = _SQLQueueBackend(database or SQLBackend.from_env(db_path))

    def initialize(self) -> None:
        self._backend.initialize()

    def enqueue(self, payload: dict, idempotency_key: str | None = None) -> dict:
        return self._backend.enqueue(payload, idempotency_key)

    def get_job(self, job_id: str) -> dict | None:
        return self._backend.get_job(job_id)

    def stats(self) -> dict:
        snapshot = self._backend.stats()
        snapshot["workers"] = len(self._threads)
        snapshot["backend"] = self._backend.name
        return snapshot

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
            try:
                job = self._backend.claim_next(worker_id)
            except Exception as exc:
                logger.warning("Queue backend %s claim failed: %s", self._backend.name, exc)
                time.sleep(POLL_SECONDS)
                continue
            if not job:
                time.sleep(POLL_SECONDS)
                continue
            try:
                result = processor(job["payload"])
                self._backend.complete(job["id"], result)
            except Exception as exc:
                logger.exception("Async prediction job failed: %s", job["id"])
                self._backend.fail(job["id"], str(exc))


class _QueueBackend:
    name = "queue"

    def initialize(self) -> None:  # pragma: no cover - interface only
        raise NotImplementedError

    def enqueue(self, payload: dict, idempotency_key: str | None = None) -> dict:  # pragma: no cover
        raise NotImplementedError

    def get_job(self, job_id: str) -> dict | None:  # pragma: no cover
        raise NotImplementedError

    def stats(self) -> dict:  # pragma: no cover
        raise NotImplementedError

    def claim_next(self, worker_id: str) -> dict | None:  # pragma: no cover
        raise NotImplementedError

    def complete(self, job_id: str, result: dict) -> None:  # pragma: no cover
        raise NotImplementedError

    def fail(self, job_id: str, error: str) -> None:  # pragma: no cover
        raise NotImplementedError


class _SQLQueueBackend(_QueueBackend):
    """SQL-backed queue with SQLite default and PostgreSQL support."""

    def __init__(self, database: SQLBackend) -> None:
        self.db = database
        self.name = database.name

    def initialize(self) -> None:
        with self.db.connect() as conn:
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
        with self.db.connect() as conn:
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
            except self.db.integrity_errors:
                existing = conn.execute(
                    "SELECT id FROM prediction_jobs WHERE idempotency_key = ?",
                    (stable_key,),
                ).fetchone()
                if existing:
                    job_id = existing[0]
        return self.get_job(job_id) or {"id": job_id, "status": "queued"}

    def get_job(self, job_id: str) -> dict | None:
        with self.db.connect() as conn:
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
        with self.db.connect() as conn:
            rows = conn.execute("SELECT status, COUNT(*) FROM prediction_jobs GROUP BY status").fetchall()
        return {"statuses": {status: count for status, count in rows}}

    def claim_next(self, worker_id: str) -> dict | None:
        if self.db.engine == "postgres":
            return self._claim_next_postgres(worker_id)
        return self._claim_next_sqlite(worker_id)

    def complete(self, job_id: str, result: dict) -> None:
        now = time.time()
        with self.db.connect() as conn:
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

    def fail(self, job_id: str, error: str) -> None:
        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE prediction_jobs
                SET status = 'failed',
                    error = ?,
                    locked_by = NULL,
                    locked_until = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (error[:500], now, job_id),
            )

    def _claim_next_sqlite(self, worker_id: str) -> dict | None:
        now = time.time()
        lock_until = now + LOCK_SECONDS
        with self.db.connect(autocommit=True) as conn:
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

    def _claim_next_postgres(self, worker_id: str) -> dict | None:
        now = time.time()
        lock_until = now + LOCK_SECONDS
        with self.db.connect() as conn:
            row = conn.execute(
                """
                WITH candidate AS (
                    SELECT id, payload_json
                    FROM prediction_jobs
                    WHERE status = 'queued'
                       OR (status = 'running' AND locked_until < ?)
                    ORDER BY created_at
                    LIMIT 1
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE prediction_jobs AS jobs
                SET status = 'running',
                    locked_by = ?,
                    locked_until = ?,
                    attempts = jobs.attempts + 1,
                    updated_at = ?
                FROM candidate
                WHERE jobs.id = candidate.id
                RETURNING jobs.id, candidate.payload_json
                """,
                (now, worker_id, lock_until, now),
            ).fetchone()
        if not row:
            return None
        return {"id": row[0], "payload": json.loads(row[1])}


class _RedisQueueBackend(_QueueBackend):
    """Redis-backed queue using lists, hashes, and lock timestamps."""

    name = "redis"

    def __init__(self, redis_url: str) -> None:
        parsed = urlparse(redis_url)
        self.host = parsed.hostname or "127.0.0.1"
        self.port = parsed.port or 6379
        self.password = parsed.password or ""
        self.db = int((parsed.path or "/0").lstrip("/") or "0")
        self.prefix = os.getenv("SHIPSENSE_REDIS_PREFIX", "shipsense").strip() or "shipsense"

    def initialize(self) -> None:
        self._command("PING")

    def enqueue(self, payload: dict, idempotency_key: str | None = None) -> dict:
        payload_json = json.dumps(payload, sort_keys=True)
        stable_key = idempotency_key.strip() if idempotency_key else sha256(payload_json.encode("utf-8")).hexdigest()
        idempotency_key_name = self._idempotency_key(stable_key)
        existing_job_id = self._command("GET", idempotency_key_name)
        if existing_job_id:
            return self.get_job(existing_job_id) or {"id": existing_job_id, "status": "queued"}

        job_id = secrets.token_urlsafe(12)
        created_at = time.time()
        was_created = int(self._command("SETNX", idempotency_key_name, job_id) or 0)
        if not was_created:
            existing_job_id = self._command("GET", idempotency_key_name)
            return self.get_job(existing_job_id) or {"id": existing_job_id, "status": "queued"}

        self._command("EXPIRE", idempotency_key_name, str(7 * 24 * 60 * 60))
        self._command(
            "HSET",
            self._job_key(job_id),
            "id",
            job_id,
            "status",
            "queued",
            "payload_json",
            payload_json,
            "result_json",
            "",
            "error",
            "",
            "attempts",
            "0",
            "locked_by",
            "",
            "locked_until",
            "",
            "created_at",
            str(created_at),
            "updated_at",
            str(created_at),
        )
        self._command("SADD", self._jobs_key(), job_id)
        self._command("RPUSH", self._ready_key(), job_id)
        return self.get_job(job_id) or {"id": job_id, "status": "queued"}

    def get_job(self, job_id: str) -> dict | None:
        data = self._hgetall(self._job_key(job_id))
        if not data:
            return None
        result_json = data.get("result_json", "")
        payload_json = data.get("payload_json", "{}")
        return {
            "id": data.get("id", job_id),
            "status": data.get("status", "queued"),
            "payload": json.loads(payload_json or "{}"),
            "result": json.loads(result_json) if result_json else None,
            "error": data.get("error") or None,
            "attempts": int(data.get("attempts", "0") or 0),
            "locked_by": data.get("locked_by") or None,
            "created_at": float(data.get("created_at", "0") or 0),
            "updated_at": float(data.get("updated_at", "0") or 0),
        }

    def stats(self) -> dict:
        job_ids = self._command("SMEMBERS", self._jobs_key()) or []
        counts: dict[str, int] = {}
        for job_id in job_ids:
            status = self._command("HGET", self._job_key(job_id), "status") or "queued"
            counts[status] = counts.get(status, 0) + 1
        return {"statuses": counts}

    def claim_next(self, worker_id: str) -> dict | None:
        self._requeue_stale()
        entry = self._command("BRPOP", self._ready_key(), str(REDIS_BLOCK_SECONDS), timeout=REDIS_BLOCK_SECONDS + 2)
        if not entry:
            return None
        job_id = entry[1] if isinstance(entry, list) and len(entry) == 2 else entry
        payload_json = self._command("HGET", self._job_key(job_id), "payload_json")
        if not payload_json:
            return None
        now = time.time()
        lock_until = now + LOCK_SECONDS
        self._command("HINCRBY", self._job_key(job_id), "attempts", "1")
        self._command(
            "HSET",
            self._job_key(job_id),
            "status",
            "running",
            "locked_by",
            worker_id,
            "locked_until",
            str(lock_until),
            "updated_at",
            str(now),
        )
        self._command("ZADD", self._locks_key(), str(lock_until), job_id)
        return {"id": job_id, "payload": json.loads(payload_json)}

    def complete(self, job_id: str, result: dict) -> None:
        now = time.time()
        self._command(
            "HSET",
            self._job_key(job_id),
            "status",
            "completed",
            "result_json",
            json.dumps(result),
            "error",
            "",
            "locked_by",
            "",
            "locked_until",
            "",
            "updated_at",
            str(now),
        )
        self._command("ZREM", self._locks_key(), job_id)

    def fail(self, job_id: str, error: str) -> None:
        now = time.time()
        self._command(
            "HSET",
            self._job_key(job_id),
            "status",
            "failed",
            "error",
            error[:500],
            "locked_by",
            "",
            "locked_until",
            "",
            "updated_at",
            str(now),
        )
        self._command("ZREM", self._locks_key(), job_id)

    def _requeue_stale(self) -> None:
        now = time.time()
        stale_ids = self._command("ZRANGEBYSCORE", self._locks_key(), "-inf", str(now), "LIMIT", "0", "25") or []
        for job_id in stale_ids:
            status = self._command("HGET", self._job_key(job_id), "status")
            if status == "running":
                self._command(
                    "HSET",
                    self._job_key(job_id),
                    "status",
                    "queued",
                    "locked_by",
                    "",
                    "locked_until",
                    "",
                    "updated_at",
                    str(now),
                )
                self._command("RPUSH", self._ready_key(), job_id)
            self._command("ZREM", self._locks_key(), job_id)

    def _job_key(self, job_id: str) -> str:
        return f"{self.prefix}:jobs:{job_id}"

    def _jobs_key(self) -> str:
        return f"{self.prefix}:jobs"

    def _ready_key(self) -> str:
        return f"{self.prefix}:queue:ready"

    def _locks_key(self) -> str:
        return f"{self.prefix}:queue:locks"

    def _idempotency_key(self, stable_key: str) -> str:
        return f"{self.prefix}:idempotency:{stable_key}"

    def _hgetall(self, key: str) -> dict[str, str]:
        response = self._command("HGETALL", key) or []
        items = list(response)
        return {str(items[index]): str(items[index + 1]) for index in range(0, len(items), 2)}

    def _command(self, *parts: str, timeout: float = 5.0):
        with socket.create_connection((self.host, self.port), timeout=timeout) as connection:
            connection.settimeout(timeout)
            stream = connection.makefile("rwb")
            if self.password:
                self._send(stream, "AUTH", self.password)
                self._read(stream)
            if self.db:
                self._send(stream, "SELECT", str(self.db))
                self._read(stream)
            self._send(stream, *parts)
            return self._read(stream)

    def _send(self, stream, *parts: str) -> None:
        encoded = [self._as_bytes(part) for part in parts]
        stream.write(f"*{len(encoded)}\r\n".encode("utf-8"))
        for part in encoded:
            stream.write(f"${len(part)}\r\n".encode("utf-8"))
            stream.write(part)
            stream.write(b"\r\n")
        stream.flush()

    def _read(self, stream):
        prefix = stream.read(1)
        if not prefix:
            raise ConnectionError("Redis connection closed unexpectedly.")
        if prefix == b"+":
            return stream.readline().decode("utf-8").rstrip("\r\n")
        if prefix == b"-":
            raise RuntimeError(stream.readline().decode("utf-8").rstrip("\r\n"))
        if prefix == b":":
            return int(stream.readline().decode("utf-8").rstrip("\r\n"))
        if prefix == b"$":
            length = int(stream.readline().decode("utf-8").rstrip("\r\n"))
            if length == -1:
                return None
            value = stream.read(length)
            stream.read(2)
            return value.decode("utf-8")
        if prefix == b"*":
            count = int(stream.readline().decode("utf-8").rstrip("\r\n"))
            if count == -1:
                return None
            return [self._read(stream) for _ in range(count)]
        raise RuntimeError(f"Unsupported Redis response prefix: {prefix!r}")

    def _as_bytes(self, value: str) -> bytes:
        if isinstance(value, bytes):
            return value
        return str(value).encode("utf-8")
