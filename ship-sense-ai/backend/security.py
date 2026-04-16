"""Authentication, session, and protected-field storage.

This module keeps the mandatory security surface self-contained:
- login with server-side sessions
- password hashing with PBKDF2-HMAC-SHA256
- session tokens stored only as hashes
- no raw username/email stored in SQLite
- display names stored with demo field-level protection

For production, replace the demo protected-field routine with a managed KMS or
AES-GCM/Fernet implementation from an approved cryptography library.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sqlite3
import time
from pathlib import Path


ACCESS_SECONDS = 20 * 60
REFRESH_SECONDS = 12 * 60 * 60
SESSION_SECONDS = REFRESH_SECONDS
MFA_SECONDS = 5 * 60
PBKDF2_ROUNDS = 210_000
MAX_MFA_ATTEMPTS = 5


class AuthStore:
    """Small SQLite-backed auth store for the hackathon demo."""

    def __init__(self, db_path: Path, secret: str) -> None:
        self.db_path = db_path
        self.secret = secret.encode("utf-8")

    def initialize(self) -> None:
        """Create auth tables and seed demo users if they are missing."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username_hash TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    display_name_cipher TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    token_hash TEXT PRIMARY KEY,
                    username_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS refresh_sessions (
                    token_hash TEXT PRIMARY KEY,
                    username_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mfa_challenges (
                    challenge_hash TEXT PRIMARY KEY,
                    username_hash TEXT NOT NULL,
                    role TEXT NOT NULL,
                    display_name_cipher TEXT NOT NULL,
                    otp_hash TEXT NOT NULL,
                    attempts INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event TEXT NOT NULL,
                    role TEXT NOT NULL,
                    ip_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )

        self._create_user_if_missing(
            username="admin",
            password=os.getenv("SHIPSENSE_ADMIN_PASSWORD", "admin123"),
            role="admin",
            display_name="Operations Admin",
        )
        self._create_user_if_missing(
            username="analyst",
            password=os.getenv("SHIPSENSE_ANALYST_PASSWORD", "analyst123"),
            role="user",
            display_name="Shipment Analyst",
        )

    def login(self, username: str, password: str, ip_address: str) -> dict | None:
        """Verify credentials and return a safe user/session payload."""
        username_hash = self._username_hash(username)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT password_hash, password_salt, role, display_name_cipher
                FROM users
                WHERE username_hash = ?
                """,
                (username_hash,),
            ).fetchone()

        if not row:
            self.audit("login_failed", "unknown", ip_address)
            return None

        password_hash, salt, role, display_name_cipher = row
        candidate = self._password_hash(password, salt)
        if not hmac.compare_digest(password_hash, candidate):
            self.audit("login_failed", role, ip_address)
            return None

        if self._mfa_enabled():
            self.audit("mfa_challenge_created", role, ip_address)
            return self._create_mfa_challenge(username_hash, role, display_name_cipher)

        self.audit("login_success", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher)

    def verify_mfa(self, challenge_id: str, otp: str, ip_address: str) -> tuple[dict | None, str | None]:
        """Verify a one-time password and create access/refresh tokens."""
        challenge_hash = self._challenge_hash(challenge_id)
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT username_hash, role, display_name_cipher, otp_hash, attempts, expires_at
                FROM mfa_challenges
                WHERE challenge_hash = ?
                """,
                (challenge_hash,),
            ).fetchone()
            if not row:
                return None, "OTP challenge not found. Please login again."

            username_hash, role, display_name_cipher, otp_hash, attempts, expires_at = row
            if expires_at < now:
                conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))
                self.audit("mfa_expired", role, ip_address)
                return None, "OTP expired. Please login again."

            if attempts >= MAX_MFA_ATTEMPTS:
                conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))
                self.audit("mfa_locked", role, ip_address)
                return None, "Too many OTP attempts. Please login again."

            if not hmac.compare_digest(otp_hash, self._otp_hash(otp)):
                conn.execute(
                    "UPDATE mfa_challenges SET attempts = attempts + 1 WHERE challenge_hash = ?",
                    (challenge_hash,),
                )
                self.audit("mfa_failed", role, ip_address)
                return None, "Invalid OTP."

            conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))

        self.audit("mfa_success", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher), None

    def signup(self, username: str, password: str, display_name: str, ip_address: str) -> tuple[dict | None, str | None]:
        """Create a new user account and return a logged-in session payload."""
        username = username.strip()
        display_name = display_name.strip() or "Shipment User"
        if len(username) < 3:
            return None, "User ID must be at least 3 characters."
        if len(password) < 6:
            return None, "Password must be at least 6 characters."
        if len(display_name) < 2:
            return None, "Display name must be at least 2 characters."

        username_hash = self._username_hash(username)
        role = "user"
        display_name_cipher = self._protect_text(display_name)
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
            if exists:
                self.audit("signup_duplicate", role, ip_address)
                return None, "User ID already exists."
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (username_hash, password_hash, password_salt, role, display_name_cipher, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username_hash,
                    self._password_hash(password, salt),
                    salt,
                    role,
                    display_name_cipher,
                    time.time(),
                ),
            )
        self.audit("signup_success", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher), None

    def _create_session(self, username_hash: str, role: str, display_name_cipher: str) -> dict:
        access_token = secrets.token_urlsafe(36)
        refresh_token = secrets.token_urlsafe(48)
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (token_hash, username_hash, role, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._token_hash(access_token), username_hash, role, now + ACCESS_SECONDS, now),
            )
            conn.execute(
                """
                INSERT INTO refresh_sessions (token_hash, username_hash, role, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._token_hash(refresh_token), username_hash, role, now + REFRESH_SECONDS, now),
            )
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "role": role,
                "display_name": self._unprotect_text(display_name_cipher),
            },
        }

    def refresh_session(self, refresh_token: str | None, ip_address: str) -> dict | None:
        """Create a new short-lived access token from a valid refresh token."""
        if not refresh_token:
            return None
        now = time.time()
        token_hash = self._token_hash(refresh_token)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT users.username_hash, users.role, users.display_name_cipher, refresh_sessions.expires_at
                FROM refresh_sessions
                JOIN users ON users.username_hash = refresh_sessions.username_hash
                WHERE refresh_sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if not row:
            return None
        username_hash, role, display_name_cipher, expires_at = row
        if expires_at < now:
            self.logout(None, refresh_token)
            return None
        access_token = self._create_access_token(username_hash, role)
        self.audit("access_token_refreshed", role, ip_address)
        return {
            "access_token": access_token,
            "user": {
                "role": role,
                "display_name": self._unprotect_text(display_name_cipher),
            },
        }

    def _create_access_token(self, username_hash: str, role: str) -> str:
        access_token = secrets.token_urlsafe(36)
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions (token_hash, username_hash, role, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (self._token_hash(access_token), username_hash, role, now + ACCESS_SECONDS, now),
            )
        return access_token

    def get_session(self, token: str | None) -> dict | None:
        """Return a safe user object for a valid unexpired session token."""
        if not token:
            return None
        now = time.time()
        token_hash = self._token_hash(token)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT users.role, users.display_name_cipher, sessions.expires_at
                FROM sessions
                JOIN users ON users.username_hash = sessions.username_hash
                WHERE sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()

        if not row:
            return None
        role, display_name_cipher, expires_at = row
        if expires_at < now:
            self.logout(token)
            return None
        return {
            "role": role,
            "display_name": self._unprotect_text(display_name_cipher),
        }

    def logout(self, access_token: str | None, refresh_token: str | None = None) -> None:
        """Delete a session token if it exists."""
        with sqlite3.connect(self.db_path) as conn:
            if access_token:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(access_token),))
            if refresh_token:
                conn.execute("DELETE FROM refresh_sessions WHERE token_hash = ?", (self._token_hash(refresh_token),))

    def audit(self, event: str, role: str, ip_address: str) -> None:
        """Store a minimal audit event without raw user identifiers."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO audit_events (event, role, ip_hash, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (event, role, self._ip_hash(ip_address), time.time()),
            )

    def security_summary(self) -> dict:
        """Return a non-sensitive summary for judges and documentation."""
        return {
            "login": "Cookie-based server session",
            "mfa": "OTP challenge supported; local demo can show OTP while production should deliver by email/SMS",
            "token_split": "Short-lived access cookie plus longer-lived refresh cookie",
            "password_storage": "PBKDF2-HMAC-SHA256 with per-user salt",
            "session_storage": "Only SHA-256 access and refresh token hashes are stored",
            "pii_policy": "No raw email or username is stored; user identifiers are HMAC protected",
            "protected_db_fields": "Display names are stored as protected ciphertext in SQLite",
            "rbac": "Admin-only audit endpoint and user prediction endpoint separation",
            "sso": "Google SSO demo adapter is available; production uses Google OAuth/OIDC credentials",
        }

    def latest_audit_events(self, limit: int = 20) -> list[dict]:
        """Return recent audit metadata without raw user/IP identifiers."""
        safe_limit = max(1, min(limit, 100))
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT event, role, created_at
                FROM audit_events
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [{"event": event, "role": role, "created_at": created_at} for event, role, created_at in rows]

    def google_demo_login(self, ip_address: str) -> dict:
        """Create a local Google SSO demo session without external OAuth keys."""
        username = "google-demo-user"
        role = "user"
        display_name = "Google SSO User"
        self._create_user_if_missing(username, os.getenv("SHIPSENSE_GOOGLE_DEMO_PASSWORD", "google-demo"), role, display_name)
        username_hash = self._username_hash(username)
        display_name_cipher = self._display_name_cipher(username_hash)
        self.audit("google_sso_demo_login", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher)

    def _create_user_if_missing(self, username: str, password: str, role: str, display_name: str) -> None:
        username_hash = self._username_hash(username)
        with sqlite3.connect(self.db_path) as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
            if exists:
                return
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (username_hash, password_hash, password_salt, role, display_name_cipher, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username_hash,
                    self._password_hash(password, salt),
                    salt,
                    role,
                    self._protect_text(display_name),
                    time.time(),
                ),
            )

    def _display_name_cipher(self, username_hash: str) -> str:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT display_name_cipher FROM users WHERE username_hash = ?",
                (username_hash,),
            ).fetchone()
        return row[0] if row else self._protect_text("Verified User")

    def _create_mfa_challenge(self, username_hash: str, role: str, display_name_cipher: str) -> dict:
        challenge_id = secrets.token_urlsafe(24)
        otp = f"{secrets.randbelow(1_000_000):06d}"
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO mfa_challenges (
                    challenge_hash, username_hash, role, display_name_cipher,
                    otp_hash, attempts, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    self._challenge_hash(challenge_id),
                    username_hash,
                    role,
                    display_name_cipher,
                    self._otp_hash(otp),
                    now + MFA_SECONDS,
                    now,
                ),
            )
        response = {
            "mfa_required": True,
            "challenge_id": challenge_id,
            "expires_in_seconds": MFA_SECONDS,
            "delivery": "demo-ui" if self._show_demo_otp() else os.getenv("SHIPSENSE_MFA_DELIVERY", "email"),
        }
        if self._show_demo_otp():
            response["demo_otp"] = otp
        return response

    def _username_hash(self, username: str) -> str:
        normalized = username.strip().lower().encode("utf-8")
        return hmac.new(self.secret, normalized, hashlib.sha256).hexdigest()

    def _ip_hash(self, ip_address: str) -> str:
        return hmac.new(self.secret, ip_address.encode("utf-8"), hashlib.sha256).hexdigest()

    def _token_hash(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _challenge_hash(self, challenge_id: str) -> str:
        return hashlib.sha256(challenge_id.encode("utf-8")).hexdigest()

    def _otp_hash(self, otp: str) -> str:
        normalized = "".join(character for character in str(otp) if character.isdigit())
        return hmac.new(self.secret, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    def _password_hash(self, password: str, salt: str) -> str:
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ROUNDS)
        return digest.hex()

    def _mfa_enabled(self) -> bool:
        return os.getenv("SHIPSENSE_MFA_ENABLED", "true").strip().lower() not in {"0", "false", "no", "off"}

    def _show_demo_otp(self) -> bool:
        return os.getenv("SHIPSENSE_MFA_DEMO_CODE", "true").strip().lower() not in {"0", "false", "no", "off"}

    def _protect_text(self, value: str) -> str:
        nonce = secrets.token_bytes(16)
        plaintext = value.encode("utf-8")
        stream = self._stream(nonce, len(plaintext))
        ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream))
        tag = hmac.new(self.secret, nonce + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")

    def _unprotect_text(self, protected_value: str) -> str:
        raw = base64.urlsafe_b64decode(protected_value.encode("ascii"))
        nonce = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]
        expected = hmac.new(self.secret, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            return "Verified User"
        stream = self._stream(nonce, len(ciphertext))
        plaintext = bytes(left ^ right for left, right in zip(ciphertext, stream))
        return plaintext.decode("utf-8")

    def _stream(self, nonce: bytes, length: int) -> bytes:
        blocks = []
        counter = 0
        while sum(len(block) for block in blocks) < length:
            blocks.append(hmac.new(self.secret, nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest())
            counter += 1
        return b"".join(blocks)[:length]
