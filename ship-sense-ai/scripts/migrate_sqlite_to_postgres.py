from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import psycopg


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.config import load_dotenv

AUTH_SQLITE = ROOT / "data" / "shipsense_auth.sqlite3"
JOBS_SQLITE = ROOT / "data" / "shipsense_jobs.sqlite3"


def read_rows(db_path: Path, table: str, columns: list[str]) -> list[tuple]:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            f"SELECT {', '.join(columns)} FROM {table}"
        ).fetchall()


def main() -> None:
    load_dotenv(ROOT / ".env")
    database_url = os.getenv("SHIPSENSE_DATABASE_URL", "").strip()
    if not database_url.startswith(("postgres://", "postgresql://")):
        raise SystemExit("SHIPSENSE_DATABASE_URL must point to PostgreSQL before running this migration.")

    user_columns = [
        "username_hash",
        "password_hash",
        "password_salt",
        "role",
        "display_name_cipher",
        "created_at",
        "email_cipher",
        "phone_cipher",
        "otp_delivery",
        "auth_provider",
        "google_subject_hash",
        "avatar_url_cipher",
    ]
    session_columns = ["token_hash", "username_hash", "role", "expires_at", "created_at"]
    mfa_columns = [
        "challenge_hash",
        "username_hash",
        "role",
        "display_name_cipher",
        "otp_hash",
        "attempts",
        "expires_at",
        "created_at",
        "provider",
        "delivery",
        "delivery_target_cipher",
    ]
    audit_columns = ["event", "role", "ip_hash", "created_at"]
    job_columns = [
        "id",
        "idempotency_key",
        "status",
        "payload_json",
        "result_json",
        "error",
        "attempts",
        "locked_by",
        "locked_until",
        "created_at",
        "updated_at",
    ]

    users = read_rows(AUTH_SQLITE, "users", user_columns)
    sessions = read_rows(AUTH_SQLITE, "sessions", session_columns)
    refresh_sessions = read_rows(AUTH_SQLITE, "refresh_sessions", session_columns)
    mfa_challenges = read_rows(AUTH_SQLITE, "mfa_challenges", mfa_columns)
    audit_events = read_rows(AUTH_SQLITE, "audit_events", audit_columns)
    jobs = read_rows(JOBS_SQLITE, "prediction_jobs", job_columns)

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO users (
                    username_hash, password_hash, password_salt, role, display_name_cipher,
                    created_at, email_cipher, phone_cipher, otp_delivery, auth_provider,
                    google_subject_hash, avatar_url_cipher
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (username_hash) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    password_salt = EXCLUDED.password_salt,
                    role = EXCLUDED.role,
                    display_name_cipher = EXCLUDED.display_name_cipher,
                    created_at = EXCLUDED.created_at,
                    email_cipher = EXCLUDED.email_cipher,
                    phone_cipher = EXCLUDED.phone_cipher,
                    otp_delivery = EXCLUDED.otp_delivery,
                    auth_provider = EXCLUDED.auth_provider,
                    google_subject_hash = EXCLUDED.google_subject_hash,
                    avatar_url_cipher = EXCLUDED.avatar_url_cipher
                """,
                users,
            )
            cur.executemany(
                """
                INSERT INTO sessions (token_hash, username_hash, role, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                sessions,
            )
            cur.executemany(
                """
                INSERT INTO refresh_sessions (token_hash, username_hash, role, expires_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (token_hash) DO NOTHING
                """,
                refresh_sessions,
            )
            cur.executemany(
                """
                INSERT INTO mfa_challenges (
                    challenge_hash, username_hash, role, display_name_cipher, otp_hash,
                    attempts, expires_at, created_at, provider, delivery, delivery_target_cipher
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (challenge_hash) DO NOTHING
                """,
                mfa_challenges,
            )
            for row in audit_events:
                cur.execute(
                    """
                    INSERT INTO audit_events (event, role, ip_hash, created_at)
                    SELECT %s, %s, %s, %s
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM audit_events
                        WHERE event = %s
                          AND role = %s
                          AND ip_hash = %s
                          AND created_at = %s
                    )
                    """,
                    (*row, *row),
                )
            cur.executemany(
                """
                INSERT INTO prediction_jobs (
                    id, idempotency_key, status, payload_json, result_json, error,
                    attempts, locked_by, locked_until, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    idempotency_key = EXCLUDED.idempotency_key,
                    status = EXCLUDED.status,
                    payload_json = EXCLUDED.payload_json,
                    result_json = EXCLUDED.result_json,
                    error = EXCLUDED.error,
                    attempts = EXCLUDED.attempts,
                    locked_by = EXCLUDED.locked_by,
                    locked_until = EXCLUDED.locked_until,
                    created_at = EXCLUDED.created_at,
                    updated_at = EXCLUDED.updated_at
                """,
                jobs,
            )
        conn.commit()

    print(
        f"Migrated users={len(users)} audit_events={len(audit_events)} "
        f"sessions={len(sessions)} refresh_sessions={len(refresh_sessions)} "
        f"mfa_challenges={len(mfa_challenges)} prediction_jobs={len(jobs)}"
    )


if __name__ == "__main__":
    main()
