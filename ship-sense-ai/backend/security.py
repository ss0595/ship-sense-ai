"""Authentication, session, MFA delivery, and protected-field storage.

This module keeps the mandatory security surface self-contained:
- login with server-side sessions
- password hashing with PBKDF2-HMAC-SHA256
- session tokens stored only as hashes
- no raw username stored in the database
- display names and contact details stored with demo field-level protection

For production, replace the demo protected-field routine with a managed KMS or
AES-GCM/Fernet implementation from an approved cryptography library.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.sql_backend import SQLBackend


ACCESS_SECONDS = 20 * 60
REFRESH_SECONDS = 12 * 60 * 60
SESSION_SECONDS = REFRESH_SECONDS
MFA_SECONDS = 5 * 60
PBKDF2_ROUNDS = 210_000
MAX_MFA_ATTEMPTS = 5


class AuthStore:
    """Small SQL-backed auth store for the hackathon demo."""

    def __init__(self, db_path: Path, secret: str, database: SQLBackend | None = None) -> None:
        self.db_path = db_path
        self.secret = secret.encode("utf-8")
        self.db = database or SQLBackend.from_env(db_path)

    def initialize(self) -> None:
        """Create auth tables, apply lightweight migrations, and seed demo users."""
        with self.db.connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username_hash TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    role TEXT NOT NULL,
                    display_name_cipher TEXT NOT NULL,
                    email_cipher TEXT NOT NULL DEFAULT '',
                    phone_cipher TEXT NOT NULL DEFAULT '',
                    otp_delivery TEXT NOT NULL DEFAULT 'email',
                    auth_provider TEXT NOT NULL DEFAULT 'local',
                    google_subject_hash TEXT NOT NULL DEFAULT '',
                    avatar_url_cipher TEXT NOT NULL DEFAULT '',
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
                    provider TEXT NOT NULL DEFAULT 'local',
                    delivery TEXT NOT NULL DEFAULT 'email',
                    delivery_target_cipher TEXT NOT NULL DEFAULT '',
                    attempts INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_events (
                    id """
                + self.db.identity_primary_key()
                + """,
                    event TEXT NOT NULL,
                    role TEXT NOT NULL,
                    ip_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            self._ensure_column(conn, "users", "email_cipher", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "phone_cipher", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "otp_delivery", "TEXT NOT NULL DEFAULT 'email'")
            self._ensure_column(conn, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
            self._ensure_column(conn, "users", "google_subject_hash", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "users", "avatar_url_cipher", "TEXT NOT NULL DEFAULT ''")
            self._ensure_column(conn, "mfa_challenges", "provider", "TEXT NOT NULL DEFAULT 'local'")
            self._ensure_column(conn, "mfa_challenges", "delivery", "TEXT NOT NULL DEFAULT 'email'")
            self._ensure_column(conn, "mfa_challenges", "delivery_target_cipher", "TEXT NOT NULL DEFAULT ''")

        self._create_user_if_missing(
            username="admin",
            password=os.getenv("SHIPSENSE_ADMIN_PASSWORD", "admin123"),
            role="admin",
            display_name="Operations Admin",
            email=os.getenv("SHIPSENSE_ADMIN_EMAIL", ""),
            phone=os.getenv("SHIPSENSE_ADMIN_PHONE", ""),
            otp_delivery=os.getenv("SHIPSENSE_ADMIN_OTP_DELIVERY", "email"),
        )
        self._create_user_if_missing(
            username="analyst",
            password=os.getenv("SHIPSENSE_ANALYST_PASSWORD", "analyst123"),
            role="user",
            display_name="Shipment Analyst",
            email=os.getenv("SHIPSENSE_ANALYST_EMAIL", ""),
            phone=os.getenv("SHIPSENSE_ANALYST_PHONE", ""),
            otp_delivery=os.getenv("SHIPSENSE_ANALYST_OTP_DELIVERY", "email"),
        )

    def login(self, username: str, password: str, ip_address: str) -> tuple[dict | None, str | None]:
        """Verify credentials and return a safe user/session payload."""
        username_hash = self._username_hash(username)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT password_hash, password_salt, role, display_name_cipher, email_cipher, phone_cipher, otp_delivery
                FROM users
                WHERE username_hash = ?
                """,
                (username_hash,),
            ).fetchone()

        if not row:
            self.audit("login_failed", "unknown", ip_address)
            return None, "Invalid username or password."

        password_hash, salt, role, display_name_cipher, email_cipher, phone_cipher, otp_delivery = row
        candidate = self._password_hash(password, salt)
        if not hmac.compare_digest(password_hash, candidate):
            self.audit("login_failed", role, ip_address)
            return None, "Invalid username or password."

        if self._mfa_enabled():
            challenge, error = self._create_mfa_challenge(
                username_hash=username_hash,
                role=role,
                display_name_cipher=display_name_cipher,
                email_cipher=email_cipher,
                phone_cipher=phone_cipher,
                otp_delivery=otp_delivery,
                ip_address=ip_address,
            )
            if not challenge:
                return None, error or "OTP delivery failed."
            return challenge, None

        self.audit("login_success", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher), None

    def verify_mfa(self, challenge_id: str, otp: str, ip_address: str) -> tuple[dict | None, str | None]:
        """Verify a one-time password and create access/refresh tokens."""
        challenge_hash = self._challenge_hash(challenge_id)
        now = time.time()
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT username_hash, role, display_name_cipher, otp_hash, attempts, expires_at
                , provider, delivery_target_cipher
                FROM mfa_challenges
                WHERE challenge_hash = ?
                """,
                (challenge_hash,),
            ).fetchone()
            if not row:
                return None, "OTP challenge not found. Please login again."

            username_hash, role, display_name_cipher, otp_hash, attempts, expires_at, provider, delivery_target_cipher = row
            if expires_at < now:
                conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))
                self.audit("mfa_expired", role, ip_address)
                return None, "OTP expired. Please login again."

            if attempts >= MAX_MFA_ATTEMPTS:
                conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))
                self.audit("mfa_locked", role, ip_address)
                return None, "Too many OTP attempts. Please login again."

            delivery_target = self._unprotect_text(delivery_target_cipher)
            is_valid = False
            provider_error = None
            if provider == "twilio_verify":
                is_valid, provider_error = self._check_twilio_verify(delivery_target, otp)
            else:
                is_valid = hmac.compare_digest(otp_hash, self._otp_hash(otp))

            if not is_valid:
                conn.execute(
                    "UPDATE mfa_challenges SET attempts = attempts + 1 WHERE challenge_hash = ?",
                    (challenge_hash,),
                )
                self.audit("mfa_failed", role, ip_address)
                return None, provider_error or "Invalid OTP."

            conn.execute("DELETE FROM mfa_challenges WHERE challenge_hash = ?", (challenge_hash,))

        self.audit("mfa_success", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher), None

    def signup(
        self,
        username: str,
        password: str,
        display_name: str,
        email: str,
        phone: str,
        otp_delivery: str,
        ip_address: str,
    ) -> tuple[dict | None, str | None]:
        """Create a new user account and begin the MFA verification flow."""
        username = username.strip()
        display_name = display_name.strip() or "Shipment User"
        email = self._normalize_email(email)
        phone = ""
        otp_delivery = "email"

        if len(username) < 3:
            return None, "User ID must be at least 3 characters."
        if len(password) < 6:
            return None, "Password must be at least 6 characters."
        if len(display_name) < 2:
            return None, "Display name must be at least 2 characters."
        if not email:
            return None, "Email is required for OTP delivery."
        if "@" not in email:
            return None, "Enter a valid email address."

        username_hash = self._username_hash(username)
        role = "user"
        display_name_cipher = self._protect_text(display_name)
        email_cipher = self._protect_text(email)
        phone_cipher = ""

        with self.db.connect() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
            if exists:
                self.audit("signup_duplicate", role, ip_address)
                return None, "User ID already exists."
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (
                    username_hash, password_hash, password_salt, role, display_name_cipher,
                    email_cipher, phone_cipher, otp_delivery, auth_provider, google_subject_hash, avatar_url_cipher, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username_hash,
                    self._password_hash(password, salt),
                    salt,
                    role,
                    display_name_cipher,
                    email_cipher,
                    phone_cipher,
                    otp_delivery,
                    "local",
                    "",
                    "",
                    time.time(),
                ),
            )

        self.audit("signup_success", role, ip_address)
        if self._mfa_enabled():
            challenge, error = self._create_mfa_challenge(
                username_hash=username_hash,
                role=role,
                display_name_cipher=display_name_cipher,
                email_cipher=email_cipher,
                phone_cipher=phone_cipher,
                otp_delivery=otp_delivery,
                ip_address=ip_address,
            )
            if not challenge:
                return None, error or "OTP delivery failed."
            return challenge, None

        return self._create_session(username_hash, role, display_name_cipher), None

    def _create_session(self, username_hash: str, role: str, display_name_cipher: str) -> dict:
        access_token = secrets.token_urlsafe(36)
        refresh_token = secrets.token_urlsafe(48)
        now = time.time()
        with self.db.connect() as conn:
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
                "account_id": username_hash,
                "role": role,
                "display_name": self._unprotect_text(display_name_cipher),
                "provider": "local",
            },
        }

    def refresh_session(self, refresh_token: str | None, ip_address: str) -> dict | None:
        """Create a new short-lived access token from a valid refresh token."""
        if not refresh_token:
            return None
        now = time.time()
        token_hash = self._token_hash(refresh_token)
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT users.username_hash, users.role, users.display_name_cipher, users.auth_provider, refresh_sessions.expires_at
                FROM refresh_sessions
                JOIN users ON users.username_hash = refresh_sessions.username_hash
                WHERE refresh_sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()
        if not row:
            return None
        username_hash, role, display_name_cipher, auth_provider, expires_at = row
        if expires_at < now:
            self.logout(None, refresh_token)
            return None
        access_token = self._create_access_token(username_hash, role)
        self.audit("access_token_refreshed", role, ip_address)
        return {
            "access_token": access_token,
            "user": {
                "account_id": username_hash,
                "role": role,
                "display_name": self._unprotect_text(display_name_cipher),
                "provider": auth_provider or "local",
            },
        }

    def _create_access_token(self, username_hash: str, role: str) -> str:
        access_token = secrets.token_urlsafe(36)
        now = time.time()
        with self.db.connect() as conn:
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
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT users.username_hash, users.role, users.display_name_cipher, users.auth_provider, sessions.expires_at
                FROM sessions
                JOIN users ON users.username_hash = sessions.username_hash
                WHERE sessions.token_hash = ?
                """,
                (token_hash,),
            ).fetchone()

        if not row:
            return None
        username_hash, role, display_name_cipher, auth_provider, expires_at = row
        if expires_at < now:
            self.logout(token)
            return None
        return {
            "account_id": username_hash,
            "role": role,
            "display_name": self._unprotect_text(display_name_cipher),
            "provider": auth_provider or "local",
        }

    def logout(self, access_token: str | None, refresh_token: str | None = None) -> None:
        """Delete a session token if it exists."""
        with self.db.connect() as conn:
            if access_token:
                conn.execute("DELETE FROM sessions WHERE token_hash = ?", (self._token_hash(access_token),))
            if refresh_token:
                conn.execute("DELETE FROM refresh_sessions WHERE token_hash = ?", (self._token_hash(refresh_token),))

    def audit(self, event: str, role: str, ip_address: str) -> None:
        """Store a minimal audit event without raw user identifiers."""
        with self.db.connect() as conn:
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
            "mfa": "OTP challenge delivered through backend SMTP email",
            "token_split": "Short-lived access cookie plus longer-lived refresh cookie",
            "password_storage": "PBKDF2-HMAC-SHA256 with per-user salt",
            "session_storage": "Only SHA-256 access and refresh token hashes are stored",
            "pii_policy": "No raw username is stored; contact details are protected ciphertext in the configured database backend",
            "protected_db_fields": "Display names, email addresses, and phone numbers are stored as protected ciphertext",
            "rbac": "Admin-only audit endpoint and user prediction endpoint separation",
            "sso": "Google OAuth 2.0 sign-in is supported when backend client credentials are configured",
        }

    def latest_audit_events(self, limit: int = 20) -> list[dict]:
        """Return recent audit metadata without raw user/IP identifiers."""
        safe_limit = max(1, min(limit, 100))
        with self.db.connect() as conn:
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

    def user_directory(self, limit: int = 50) -> list[dict]:
        """Return a safe admin-only directory of registered users."""
        safe_limit = max(1, min(limit, 200))
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT username_hash, role, display_name_cipher, email_cipher, otp_delivery, auth_provider, created_at
                FROM users
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        directory = []
        for username_hash, role, display_name_cipher, email_cipher, otp_delivery, auth_provider, created_at in rows:
            email = self._unprotect_text(email_cipher)
            directory.append(
                {
                    "account_id": username_hash,
                    "role": role,
                    "display_name": self._unprotect_text(display_name_cipher),
                    "email_hint": self._mask_email(email) if email else "No email",
                    "otp_delivery": otp_delivery or "email",
                    "auth_provider": auth_provider or "local",
                    "created_at": created_at,
                }
            )
        return directory

    def session_subject(self, token: str | None) -> dict | None:
        """Return the stable account identifier for the active access token."""
        session = self.get_session(token)
        if not session:
            return None
        return {
            "account_id": session["account_id"],
            "role": session["role"],
        }

    def admin_create_user(
        self,
        username: str,
        password: str,
        display_name: str,
        email: str,
        role: str,
        ip_address: str,
    ) -> tuple[dict | None, str | None]:
        """Create a local account from the admin console."""
        username = username.strip()
        display_name = display_name.strip() or username
        email = self._normalize_email(email)
        role = str(role or "user").strip().lower()
        if role not in {"admin", "user"}:
            return None, "Role must be admin or user."
        if len(username) < 3:
            return None, "User ID must be at least 3 characters."
        if len(password) < 6:
            return None, "Password must be at least 6 characters."
        if len(display_name) < 2:
            return None, "Display name must be at least 2 characters."
        if not email or "@" not in email:
            return None, "Enter a valid email address."

        username_hash = self._username_hash(username)
        with self.db.connect() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
            if exists:
                return None, "User ID already exists."
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (
                    username_hash, password_hash, password_salt, role, display_name_cipher,
                    email_cipher, phone_cipher, otp_delivery, auth_provider, google_subject_hash, avatar_url_cipher, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username_hash,
                    self._password_hash(password, salt),
                    salt,
                    role,
                    self._protect_text(display_name),
                    self._protect_text(email),
                    "",
                    "email",
                    "local",
                    "",
                    "",
                    time.time(),
                ),
            )
        self.audit("admin_account_created", "admin", ip_address)
        return {
            "account_id": username_hash,
            "role": role,
            "display_name": display_name,
            "email_hint": self._mask_email(email),
            "otp_delivery": "email",
            "auth_provider": "local",
            "created_at": time.time(),
        }, None

    def admin_delete_user(
        self,
        account_id: str,
        acting_account_id: str,
        ip_address: str,
    ) -> tuple[bool, str | None]:
        """Remove an account from the admin console while protecting core access."""
        account_id = str(account_id or "").strip()
        if not account_id:
            return False, "Account id is required."
        if account_id == acting_account_id:
            return False, "You cannot remove the account currently signed in."

        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT role
                FROM users
                WHERE username_hash = ?
                """,
                (account_id,),
            ).fetchone()
            if not row:
                return False, "Account not found."
            target_role = row[0]
            if target_role == "admin":
                admin_count = conn.execute("SELECT COUNT(*) FROM users WHERE role = 'admin'").fetchone()[0]
                if admin_count <= 1:
                    return False, "You cannot remove the last admin account."
            conn.execute("DELETE FROM sessions WHERE username_hash = ?", (account_id,))
            conn.execute("DELETE FROM refresh_sessions WHERE username_hash = ?", (account_id,))
            conn.execute("DELETE FROM mfa_challenges WHERE username_hash = ?", (account_id,))
            conn.execute("DELETE FROM users WHERE username_hash = ?", (account_id,))
        self.audit("admin_account_deleted", "admin", ip_address)
        return True, None

    def google_oauth_configured(self) -> bool:
        return bool(self._google_client_id() and self._google_client_secret())

    def google_authorization_url(self, redirect_uri: str, state: str) -> tuple[str | None, str | None]:
        client_id = self._google_client_id()
        if not client_id:
            return None, "Google sign-in is not configured on the backend."
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "access_type": "online",
            "include_granted_scopes": "true",
            "state": state,
        }
        prompt = os.getenv("SHIPSENSE_GOOGLE_PROMPT", "").strip()
        if prompt:
            params["prompt"] = prompt
        return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}", None

    def google_profile_from_code(self, code: str, redirect_uri: str) -> tuple[dict | None, str | None]:
        client_id = self._google_client_id()
        client_secret = self._google_client_secret()
        if not client_id or not client_secret:
            return None, "Google sign-in is not configured on the backend."

        request = Request(
            "https://oauth2.googleapis.com/token",
            data=urlencode(
                {
                    "code": code,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=10, context=self._google_tls_context()) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            logging.getLogger("shipsense").warning("Google token exchange failed (%s): %s", exc.code, detail[:400])
            if exc.code in {400, 401, 403}:
                return None, "Google sign-in was rejected. Check the client ID, client secret, and redirect URI."
            return None, f"Google sign-in failed with HTTP {exc.code}."
        except URLError as exc:
            logging.getLogger("shipsense").warning("Google token exchange network error: %s", exc)
            return None, "Could not reach Google to complete sign-in."
        except Exception as exc:
            logging.getLogger("shipsense").warning("Unexpected Google token exchange error: %s", exc)
            return None, "Google sign-in could not be completed right now."

        access_token = str(payload.get("access_token", "")).strip()
        if not access_token:
            return None, "Google sign-in did not return an access token."
        return self._google_userinfo(access_token)

    def google_oauth_login(self, profile: dict, ip_address: str) -> tuple[dict | None, str | None]:
        subject = str(profile.get("sub", "")).strip()
        email = self._normalize_email(profile.get("email", ""))
        if not subject:
            return None, "Google sign-in did not return a stable account identifier."
        if email and not bool(profile.get("email_verified", False)):
            return None, "The selected Google account email is not verified."

        display_name = str(
            profile.get("name")
            or profile.get("given_name")
            or (email.split("@", 1)[0] if email else "Google User")
        ).strip() or "Google User"
        avatar_url = str(profile.get("picture", "")).strip()
        google_subject_hash = self._external_subject_hash("google", subject)
        user = self._find_user_by_google_subject(google_subject_hash)
        if not user and email:
            user = self._find_user_by_email(email)

        if user:
            username_hash = user["username_hash"]
            role = user["role"]
            with self.db.connect() as conn:
                conn.execute(
                    """
                    UPDATE users
                    SET display_name_cipher = ?, email_cipher = ?, otp_delivery = ?, auth_provider = ?, google_subject_hash = ?, avatar_url_cipher = ?
                    WHERE username_hash = ?
                    """,
                    (
                        self._protect_text(display_name),
                        self._protect_text(email),
                        "email",
                        "google",
                        google_subject_hash,
                        self._protect_text(avatar_url),
                        username_hash,
                    ),
                )
        else:
            username_hash = self._username_hash(f"google:{subject}")
            role = self._role_for_email(email)
            with self.db.connect() as conn:
                exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
                if not exists:
                    salt = secrets.token_hex(16)
                    conn.execute(
                        """
                        INSERT INTO users (
                            username_hash, password_hash, password_salt, role, display_name_cipher,
                            email_cipher, phone_cipher, otp_delivery, auth_provider, google_subject_hash, avatar_url_cipher, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            username_hash,
                            self._password_hash(secrets.token_urlsafe(24), salt),
                            salt,
                            role,
                            self._protect_text(display_name),
                            self._protect_text(email),
                            "",
                            "email",
                            "google",
                            google_subject_hash,
                            self._protect_text(avatar_url),
                            time.time(),
                        ),
                    )

        display_name_cipher = self._display_name_cipher(username_hash)
        self.audit("google_oauth_login", role, ip_address)
        return self._create_session(username_hash, role, display_name_cipher), None

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

    def _create_user_if_missing(
        self,
        username: str,
        password: str,
        role: str,
        display_name: str,
        email: str = "",
        phone: str = "",
        otp_delivery: str = "email",
    ) -> None:
        username_hash = self._username_hash(username)
        email = self._normalize_email(email)
        phone = ""
        otp_delivery = "email"
        with self.db.connect() as conn:
            exists = conn.execute("SELECT 1 FROM users WHERE username_hash = ?", (username_hash,)).fetchone()
            if exists:
                updates = []
                params: list[str] = []
                if email:
                    updates.append("email_cipher = ?")
                    params.append(self._protect_text(email))
                if email:
                    updates.append("otp_delivery = ?")
                    params.append("email")
                if updates:
                    conn.execute(
                        f"UPDATE users SET {', '.join(updates)} WHERE username_hash = ?",
                        (*params, username_hash),
                    )
                return
            salt = secrets.token_hex(16)
            conn.execute(
                """
                INSERT INTO users (
                    username_hash, password_hash, password_salt, role, display_name_cipher,
                    email_cipher, phone_cipher, otp_delivery, auth_provider, google_subject_hash, avatar_url_cipher, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username_hash,
                    self._password_hash(password, salt),
                    salt,
                    role,
                    self._protect_text(display_name),
                    self._protect_text(email),
                    "",
                    "email",
                    "local",
                    "",
                    "",
                    time.time(),
                ),
            )

    def _display_name_cipher(self, username_hash: str) -> str:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT display_name_cipher FROM users WHERE username_hash = ?",
                (username_hash,),
            ).fetchone()
        return row[0] if row else self._protect_text("Verified User")

    def _create_mfa_challenge(
        self,
        username_hash: str,
        role: str,
        display_name_cipher: str,
        email_cipher: str,
        phone_cipher: str,
        otp_delivery: str,
        ip_address: str,
    ) -> tuple[dict | None, str | None]:
        challenge_id = secrets.token_urlsafe(24)
        display_name = self._unprotect_text(display_name_cipher)
        email = self._unprotect_text(email_cipher)
        phone = self._unprotect_text(phone_cipher)
        delivery = self._preferred_delivery(otp_delivery, email, phone)
        if not delivery:
            self.audit("mfa_delivery_missing", role, ip_address)
            return None, "No email or phone is configured for OTP delivery on this account."

        provider = "local"
        delivery_target = email if delivery == "email" else phone
        otp_hash = ""
        delivery_error = None
        if delivery == "phone" and self._twilio_verify_service_sid():
            provider = "twilio_verify"
            delivered, delivery_error = self._start_twilio_verify(phone)
        else:
            otp = f"{secrets.randbelow(1_000_000):06d}"
            otp_hash = self._otp_hash(otp)
            delivered, delivery_error = self._deliver_otp(
                delivery=delivery,
                display_name=display_name,
                email=email,
                phone=phone,
                otp=otp,
            )
        if not delivered:
            self.audit("mfa_delivery_failed", role, ip_address)
            return None, delivery_error or "OTP delivery failed."

        now = time.time()
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO mfa_challenges (
                    challenge_hash, username_hash, role, display_name_cipher,
                    otp_hash, provider, delivery, delivery_target_cipher, attempts, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    self._challenge_hash(challenge_id),
                    username_hash,
                    role,
                    display_name_cipher,
                    otp_hash,
                    provider,
                    delivery,
                    self._protect_text(delivery_target),
                    now + MFA_SECONDS,
                    now,
                ),
            )

        self.audit("mfa_challenge_created", role, ip_address)
        return {
            "mfa_required": True,
            "challenge_id": challenge_id,
            "expires_in_seconds": MFA_SECONDS,
            "delivery": delivery,
            "delivery_target_hint": self._mask_email(email) if delivery == "email" else self._mask_phone(phone),
        }, None

    def _deliver_otp(self, delivery: str, display_name: str, email: str, phone: str, otp: str) -> tuple[bool, str | None]:
        if delivery == "phone":
            return self._send_sms_otp(display_name, phone, otp)
        return self._send_email_otp(display_name, email, otp)

    def _send_email_otp(self, display_name: str, email: str, otp: str) -> tuple[bool, str | None]:
        host = os.getenv("SHIPSENSE_SMTP_HOST", "").strip()
        if not host:
            return False, "Email OTP delivery is not configured on the backend."
        port = int(os.getenv("SHIPSENSE_SMTP_PORT", "587"))
        username = os.getenv("SHIPSENSE_SMTP_USERNAME", "").strip()
        password = os.getenv("SHIPSENSE_SMTP_PASSWORD", "").strip().replace(" ", "")
        from_address = os.getenv("SHIPSENSE_SMTP_FROM", "").strip() or username
        if not from_address:
            return False, "SMTP sender address is missing."

        message = EmailMessage()
        message["Subject"] = "Your ShipSense AI verification code"
        message["From"] = from_address
        message["To"] = email
        message.set_content(
            "\n".join(
                [
                    f"Hello {display_name or 'ShipSense user'},",
                    "",
                    f"Your ShipSense AI verification code is {otp}.",
                    f"It expires in {MFA_SECONDS // 60} minutes.",
                    "",
                    "If you did not try to sign in, you can ignore this email.",
                ]
            )
        )

        try:
            with smtplib.SMTP(host, port, timeout=10) as smtp:
                if os.getenv("SHIPSENSE_SMTP_TLS", "true").strip().lower() not in {"0", "false", "no", "off"}:
                    verify_tls = os.getenv("SHIPSENSE_SMTP_TLS_VERIFY", "true").strip().lower() not in {"0", "false", "no", "off"}
                    tls_context = ssl.create_default_context() if verify_tls else ssl._create_unverified_context()
                    smtp.starttls(context=tls_context)
                if username:
                    smtp.login(username, password)
                smtp.send_message(message)
            return True, None
        except Exception as exc:
            logging.getLogger("shipsense").warning("SMTP email send failed: %s", exc)
            return False, "Could not send OTP email. Check SMTP settings."

    def _send_sms_otp(self, display_name: str, phone: str, otp: str) -> tuple[bool, str | None]:
        if self._twilio_verify_service_sid():
            return self._start_twilio_verify(phone)
        twilio_account_sid = os.getenv("SHIPSENSE_TWILIO_ACCOUNT_SID", "").strip()
        twilio_auth_token = os.getenv("SHIPSENSE_TWILIO_AUTH_TOKEN", "").strip()
        twilio_from_number = os.getenv("SHIPSENSE_TWILIO_FROM_NUMBER", "").strip()
        twilio_messaging_service_sid = os.getenv("SHIPSENSE_TWILIO_MESSAGING_SERVICE_SID", "").strip()
        if twilio_account_sid and twilio_auth_token and (twilio_from_number or twilio_messaging_service_sid):
            return self._send_twilio_sms(display_name, phone, otp)

        webhook_url = os.getenv("SHIPSENSE_SMS_WEBHOOK_URL", "").strip()
        if not webhook_url:
            return False, "Phone OTP delivery is not configured on the backend."
        token = os.getenv("SHIPSENSE_SMS_WEBHOOK_TOKEN", "").strip()
        payload = {
            "to": phone,
            "channel": "sms",
            "message": f"ShipSense AI verification code: {otp}. It expires in {MFA_SECONDS // 60} minutes.",
            "otp": otp,
            "display_name": display_name or "ShipSense user",
        }
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        request = Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return True, None
        except Exception:
            return False, "Could not send OTP to the configured phone channel."
        return False, "Could not send OTP to the configured phone channel."

    def _send_twilio_sms(self, display_name: str, phone: str, otp: str) -> tuple[bool, str | None]:
        account_sid = os.getenv("SHIPSENSE_TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("SHIPSENSE_TWILIO_AUTH_TOKEN", "").strip()
        from_number = os.getenv("SHIPSENSE_TWILIO_FROM_NUMBER", "").strip()
        messaging_service_sid = os.getenv("SHIPSENSE_TWILIO_MESSAGING_SERVICE_SID", "").strip()
        if not account_sid or not auth_token or not (from_number or messaging_service_sid):
            return False, "Twilio SMS delivery is not fully configured on the backend."
        if not phone.startswith("+"):
            return False, "Phone OTP requires international format, for example +919652909758."
        if from_number and not messaging_service_sid and not from_number.startswith("+"):
            return False, "Twilio sender must include the country code, for example +14155550123, or use a Messaging Service SID."

        payload = {
            "To": phone,
            "Body": f"ShipSense AI verification code: {otp}. It expires in {MFA_SECONDS // 60} minutes.",
        }
        if messaging_service_sid:
            payload["MessagingServiceSid"] = messaging_service_sid
        else:
            payload["From"] = from_number

        token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
        request = Request(
            f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
            data=urlencode(payload).encode("utf-8"),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return True, None
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            logging.getLogger("shipsense").warning("Twilio SMS failed (%s): %s", exc.code, detail[:400])
            if exc.code == 400:
                return False, "Twilio rejected the SMS request. Check the sender, destination number format, and whether the number is allowed in your Twilio account."
            if exc.code in {401, 403}:
                return False, "Twilio authentication failed. Check the Account SID and Auth Token."
            return False, f"Twilio SMS failed with HTTP {exc.code}."
        except URLError as exc:
            logging.getLogger("shipsense").warning("Twilio SMS network error: %s", exc)
            return False, "Could not reach Twilio from the backend. Check the internet connection and try again."
        except Exception as exc:
            logging.getLogger("shipsense").warning("Unexpected Twilio SMS error: %s", exc)
            return False, "Could not send OTP through Twilio. Check the SID, auth token, sender, and destination number."
        return False, "Could not send OTP through Twilio. Check the SID, auth token, sender, and destination number."

    def _start_twilio_verify(self, phone: str) -> tuple[bool, str | None]:
        account_sid = os.getenv("SHIPSENSE_TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("SHIPSENSE_TWILIO_AUTH_TOKEN", "").strip()
        service_sid = self._twilio_verify_service_sid()
        if not account_sid or not auth_token or not service_sid:
            return False, "Twilio Verify is not fully configured on the backend."
        if not phone.startswith("+"):
            return False, "Phone OTP requires international format, for example +919652909758."

        token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
        request = Request(
            f"https://verify.twilio.com/v2/Services/{service_sid}/Verifications",
            data=urlencode({"To": phone, "Channel": "sms"}).encode("utf-8"),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                if 200 <= response.status < 300:
                    return True, None
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            logging.getLogger("shipsense").warning("Twilio Verify start failed (%s): %s", exc.code, detail[:400])
            if exc.code == 400:
                return False, "Twilio Verify rejected the SMS request. Check the phone number, Verify Service SID, and whether the destination is allowed in your Twilio account."
            if exc.code in {401, 403}:
                return False, "Twilio Verify authentication failed. Check the Account SID, Auth Token, and Verify Service SID."
            return False, f"Twilio Verify failed with HTTP {exc.code}."
        except URLError as exc:
            logging.getLogger("shipsense").warning("Twilio Verify network error: %s", exc)
            return False, "Could not reach Twilio Verify from the backend. Check the internet connection and try again."
        return False, "Could not start Twilio Verify."

    def _check_twilio_verify(self, phone: str, otp: str) -> tuple[bool, str | None]:
        account_sid = os.getenv("SHIPSENSE_TWILIO_ACCOUNT_SID", "").strip()
        auth_token = os.getenv("SHIPSENSE_TWILIO_AUTH_TOKEN", "").strip()
        service_sid = self._twilio_verify_service_sid()
        if not account_sid or not auth_token or not service_sid:
            return False, "Twilio Verify is not fully configured on the backend."

        token = base64.b64encode(f"{account_sid}:{auth_token}".encode("utf-8")).decode("ascii")
        request = Request(
            f"https://verify.twilio.com/v2/Services/{service_sid}/VerificationCheck",
            data=urlencode({"To": phone, "Code": "".join(char for char in str(otp) if char.isdigit())}).encode("utf-8"),
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
                approved = payload.get("status") == "approved" or bool(payload.get("valid"))
                return (True, None) if approved else (False, "Invalid OTP.")
        except HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = ""
            logging.getLogger("shipsense").warning("Twilio Verify check failed (%s): %s", exc.code, detail[:400])
            if exc.code in {401, 403}:
                return False, "Twilio Verify authentication failed. Check the Account SID, Auth Token, and Verify Service SID."
            return False, "Twilio Verify could not validate the OTP."
        except URLError as exc:
            logging.getLogger("shipsense").warning("Twilio Verify check network error: %s", exc)
            return False, "Could not reach Twilio Verify to validate the OTP."
        except Exception as exc:
            logging.getLogger("shipsense").warning("Unexpected Twilio Verify check error: %s", exc)
            return False, "Could not verify the OTP right now."

    def _twilio_verify_service_sid(self) -> str:
        return os.getenv("SHIPSENSE_TWILIO_VERIFY_SERVICE_SID", "").strip()

    def _google_client_id(self) -> str:
        return os.getenv("SHIPSENSE_GOOGLE_CLIENT_ID", "").strip()

    def _google_client_secret(self) -> str:
        return os.getenv("SHIPSENSE_GOOGLE_CLIENT_SECRET", "").strip()

    def _google_tls_context(self) -> ssl.SSLContext:
        verify_tls = os.getenv("SHIPSENSE_GOOGLE_TLS_VERIFY", "true").strip().lower() not in {"0", "false", "no", "off"}
        return ssl.create_default_context() if verify_tls else ssl._create_unverified_context()

    def _google_userinfo(self, access_token: str) -> tuple[dict | None, str | None]:
        request = Request(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=10, context=self._google_tls_context()) as response:
                profile = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = self._http_error_detail(exc)
            logging.getLogger("shipsense").warning("Google userinfo failed (%s): %s", exc.code, detail[:400])
            if exc.code in {401, 403}:
                return None, "Google did not allow profile access for this sign-in."
            return None, f"Google profile lookup failed with HTTP {exc.code}."
        except URLError as exc:
            logging.getLogger("shipsense").warning("Google userinfo network error: %s", exc)
            return None, "Could not reach Google to fetch the account profile."
        except Exception as exc:
            logging.getLogger("shipsense").warning("Unexpected Google userinfo error: %s", exc)
            return None, "Google profile data could not be loaded right now."
        return profile, None

    def _find_user_by_google_subject(self, google_subject_hash: str) -> dict | None:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT username_hash, role
                FROM users
                WHERE google_subject_hash = ?
                """,
                (google_subject_hash,),
            ).fetchone()
        if not row:
            return None
        username_hash, role = row
        return {"username_hash": username_hash, "role": role}

    def _find_user_by_email(self, email: str) -> dict | None:
        if not email:
            return None
        normalized = self._normalize_email(email)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT username_hash, role, email_cipher
                FROM users
                """
            ).fetchall()
        for username_hash, role, email_cipher in rows:
            if self._normalize_email(self._unprotect_text(email_cipher)) == normalized:
                return {"username_hash": username_hash, "role": role}
        return None

    def _role_for_email(self, email: str) -> str:
        normalized = self._normalize_email(email)
        if normalized and normalized == self._normalize_email(os.getenv("SHIPSENSE_ADMIN_EMAIL", "")):
            return "admin"
        return "user"

    def _external_subject_hash(self, provider: str, subject: str) -> str:
        normalized = f"{provider}:{str(subject).strip()}".encode("utf-8")
        return hmac.new(self.secret, normalized, hashlib.sha256).hexdigest()

    def _http_error_detail(self, exc: HTTPError) -> str:
        try:
            return exc.read().decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _ensure_column(self, conn, table: str, column: str, definition: str) -> None:
        columns = self.db.column_names(conn, table)
        if column not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

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

    def _normalize_email(self, email: str) -> str:
        return str(email or "").strip().lower()

    def _normalize_phone(self, phone: str) -> str:
        value = str(phone or "").strip()
        if not value:
            return ""
        has_plus = value.startswith("+")
        digits = "".join(char for char in value if char.isdigit())
        if not digits:
            return ""
        return f"+{digits}" if has_plus else digits

    def _normalize_delivery(self, delivery: str) -> str:
        return "email"

    def _preferred_delivery(self, delivery: str, email: str, phone: str) -> str:
        return "email" if email else ""

    def _mask_email(self, email: str) -> str:
        if "@" not in email:
            return "your email"
        local, domain = email.split("@", 1)
        local_hint = (local[:2] + "*" * max(1, len(local) - 2)) if local else "***"
        domain_name, _, suffix = domain.partition(".")
        domain_hint = (domain_name[:1] + "*" * max(1, len(domain_name) - 1)) if domain_name else "*"
        if suffix:
            return f"{local_hint}@{domain_hint}.{suffix}"
        return f"{local_hint}@{domain_hint}"

    def _mask_phone(self, phone: str) -> str:
        digits = "".join(char for char in phone if char.isdigit())
        if len(digits) <= 4:
            return "your phone"
        return f"{'*' * max(2, len(digits) - 4)}{digits[-4:]}"

    def _protect_text(self, value: str) -> str:
        if not value:
            return ""
        nonce = secrets.token_bytes(16)
        plaintext = value.encode("utf-8")
        stream = self._stream(nonce, len(plaintext))
        ciphertext = bytes(left ^ right for left, right in zip(plaintext, stream))
        tag = hmac.new(self.secret, nonce + ciphertext, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(nonce + tag + ciphertext).decode("ascii")

    def _unprotect_text(self, protected_value: str) -> str:
        if not protected_value:
            return ""
        raw = base64.urlsafe_b64decode(protected_value.encode("ascii"))
        nonce = raw[:16]
        tag = raw[16:48]
        ciphertext = raw[48:]
        expected = hmac.new(self.secret, nonce + ciphertext, hashlib.sha256).digest()
        if not hmac.compare_digest(tag, expected):
            return ""
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
