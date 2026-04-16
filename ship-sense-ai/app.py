"""HTTP API and static dashboard server for ShipSense AI.

The project uses Python's standard library server so it can run in a hackathon
environment without dependency installation. The API shape is intentionally
similar to a FastAPI service, so the same endpoints can be migrated later.
"""

from __future__ import annotations

import argparse
from http import cookies
import json
import logging
import os
import secrets
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from backend.agent import predict_risk
from backend.config import load_dotenv
from backend.data_store import (
    available_hubs,
    available_origins,
    available_ports,
    load_shipments,
    load_signals,
    recent_shipments,
    transport_reference,
)
from backend.live_signals import enrich_signals_for_payload, live_source_status
from backend.observability import METRICS, tail_log_lines
from backend.openai_agent import enrich_result_with_openai, openai_source_status
from backend.security import ACCESS_SECONDS, AuthStore, REFRESH_SECONDS
from backend.task_queue import PredictionQueue

RBAC_POLICY = {
    "admin": [
        "predict",
        "create_async_prediction_job",
        "view_job_status",
        "view_platform_status",
        "view_security_policy",
        "view_rbac_policy",
        "view_observability",
        "view_audit",
        "view_user_directory",
        "manage_accounts",
        "manage_demo",
    ],
    "user": [
        "predict",
        "create_async_prediction_job",
        "view_job_status",
        "view_platform_status",
        "view_security_policy",
    ],
}


ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
STATIC_DIR = ROOT / "static"
DATA_DIR = ROOT / "data"
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
LOGGER = logging.getLogger("shipsense")
SHIPMENTS = load_shipments(DATA_DIR)
SIGNALS = load_signals(DATA_DIR)
AUTH = AuthStore(DATA_DIR / "shipsense_auth.sqlite3", os.getenv("SHIPSENSE_SECRET", "dev-change-me"))
AUTH.initialize()
PREDICTION_QUEUE = PredictionQueue(DATA_DIR / "shipsense_jobs.sqlite3")
PREDICTION_QUEUE.initialize()


def build_prediction_result(payload: dict) -> dict:
    """Run the full prediction pipeline for sync and async endpoints."""
    active_signals, live_status = enrich_signals_for_payload(SIGNALS, payload, LOGGER)
    result = predict_risk(payload, SHIPMENTS, active_signals)
    result["recent_shipments"] = recent_shipments(SHIPMENTS)
    result["live_sources"] = live_status
    if live_status.get("openweather", {}).get("used"):
        result["data_sources"].append("OpenWeather live API")
    if live_status.get("newsapi", {}).get("used"):
        result["data_sources"].append("NewsAPI live feed")
    result = enrich_result_with_openai(result, LOGGER)
    if result.get("ai_agent", {}).get("used"):
        result["data_sources"].append("OpenAI explanation agent")
    return result


class ShipSenseHandler(SimpleHTTPRequestHandler):
    """Serve both API responses and static dashboard assets."""

    server_version = "ShipSenseAI/1.0"

    def end_headers(self) -> None:
        """Attach CORS and no-cache headers for local demo reliability."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        if getattr(self, "_trace_id", ""):
            self.send_header("X-Trace-Id", self._trace_id)
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        LOGGER.info("%s - %s", self.address_string(), fmt % args)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        """Handle read-only API endpoints and static file requests."""
        self._begin_request()
        parsed = urlparse(self.path)
        if parsed.path == "/metrics":
            self._text(METRICS.prometheus(PREDICTION_QUEUE.stats()), content_type="text/plain; version=0.0.4")
            return
        if parsed.path == "/api/health":
            self._json(
                {
                    "status": "ok",
                    "service": "ShipSense AI",
                    "hubs": len(available_ports(SIGNALS)),
                    "workers": PREDICTION_QUEUE.stats()["workers"],
                }
            )
            return
        if parsed.path == "/api/me":
            user = self._session_user()
            if not user:
                self._json({"authenticated": False}, status=401)
                return
            self._json({"authenticated": True, "user": user})
            return
        if parsed.path == "/api/security-policy":
            self._json(AUTH.security_summary())
            return
        if parsed.path == "/api/auth-providers":
            self._json(
                {
                    "google": {
                        "configured": AUTH.google_oauth_configured(),
                        "login_path": "/auth/google/start",
                        "label": "Continue with Google" if AUTH.google_oauth_configured() else "Google sign-in unavailable",
                    }
                }
            )
            return
        if parsed.path == "/api/live-sources":
            self._json({**live_source_status(), "openai": openai_source_status()})
            return
        if parsed.path == "/api/platform-status":
            self._json(self._platform_status())
            return
        if parsed.path == "/auth/google/start":
            self._handle_google_oauth_start()
            return
        if parsed.path == "/auth/google/callback":
            self._handle_google_oauth_callback(parsed)
            return
        if parsed.path == "/api/rbac-policy":
            user = self._require_user()
            if not user:
                return
            role = str(user.get("role", "user"))
            payload = {"current_role": role, "allowed": RBAC_POLICY.get(role, [])}
            if role == "admin":
                payload["roles"] = RBAC_POLICY
            self._json(payload)
            return
        if parsed.path.startswith("/api/"):
            user = self._require_user()
            if not user:
                return
        if parsed.path == "/api/network":
            self._json(transport_reference(SHIPMENTS, SIGNALS))
            return
        if parsed.path == "/api/admin/audit":
            if not self._require_role({"admin"}):
                return
            limit = int(parse_qs(parsed.query).get("limit", ["20"])[0])
            self._json({"events": AUTH.latest_audit_events(limit=limit)})
            return
        if parsed.path == "/api/observability":
            if not self._require_role({"admin"}):
                return
            self._json({"metrics": METRICS.snapshot(), "queue": PREDICTION_QUEUE.stats()})
            return
        if parsed.path == "/api/admin/logs":
            if not self._require_role({"admin"}):
                return
            limit = int(parse_qs(parsed.query).get("limit", ["80"])[0])
            self._json({"lines": tail_log_lines(LOG_DIR / "app.log", limit=limit)})
            return
        if parsed.path == "/api/admin/traces":
            if not self._require_role({"admin"}):
                return
            limit = int(parse_qs(parsed.query).get("limit", ["25"])[0])
            self._json({"traces": METRICS.recent_traces(limit=limit)})
            return
        if parsed.path == "/api/admin/overview":
            if not self._require_role({"admin"}):
                return
            directory = AUTH.user_directory(limit=25)
            self._json(
                {
                    "rbac": RBAC_POLICY,
                    "metrics": METRICS.snapshot(),
                    "queue": PREDICTION_QUEUE.stats(),
                    "audit_events": AUTH.latest_audit_events(limit=12),
                    "users": directory,
                    "traces": METRICS.recent_traces(limit=18),
                    "logs": tail_log_lines(LOG_DIR / "app.log", limit=50),
                    "stack": self._observability_stack(),
                    "summary": {
                        "total_users": len(directory),
                        "admins": sum(1 for entry in directory if entry.get("role") == "admin"),
                        "standard_users": sum(1 for entry in directory if entry.get("role") == "user"),
                    },
                }
            )
            return
        if parsed.path.startswith("/api/prediction-jobs/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            job = PREDICTION_QUEUE.get_job(job_id)
            if not job:
                self._json({"error": "Job not found"}, status=404)
                return
            self._json({"job": job})
            return
        if parsed.path == "/api/ports":
            mode = parse_qs(parsed.query).get("mode", [""])[0]
            hubs = available_hubs(SIGNALS, mode=mode)
            self._json({"ports": hubs, "hubs": hubs})
            return
        if parsed.path == "/api/origins":
            mode = parse_qs(parsed.query).get("mode", [""])[0]
            self._json({"origins": available_origins(SHIPMENTS, mode=mode)})
            return
        if parsed.path == "/api/shipments":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["8"])[0])
            self._json({"shipments": recent_shipments(SHIPMENTS, limit=limit)})
            return
        if parsed.path == "/api/signals":
            self._json({"last_updated": SIGNALS.get("last_updated"), "hubs": SIGNALS.get("hubs", {})})
            return

        if self.path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        """Handle prediction requests sent by the dashboard."""
        self._begin_request()
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            self._handle_login()
            return
        if parsed.path == "/api/verify-mfa":
            self._handle_verify_mfa()
            return
        if parsed.path == "/api/signup":
            self._handle_signup()
            return
        if parsed.path == "/api/refresh":
            self._handle_refresh()
            return
        if parsed.path == "/api/google-login":
            self._handle_google_login()
            return
        if parsed.path == "/api/admin/accounts":
            if not self._require_role({"admin"}):
                return
            self._handle_admin_create_account()
            return
        if parsed.path == "/api/logout":
            AUTH.logout(self._access_token(), self._refresh_token())
            self._json({"ok": True}, headers=self._expired_cookies())
            return
        if parsed.path == "/api/prediction-jobs":
            user = self._require_user()
            if not user:
                return
            payload = self._payload()
            job = PREDICTION_QUEUE.enqueue(payload, self.headers.get("Idempotency-Key"))
            AUTH.audit("prediction_job_enqueued", user["role"], self.client_address[0])
            self._json({"job": job}, status=202)
            return
        if parsed.path != "/api/predict-risk":
            self._json({"error": "Not found"}, status=404)
            return

        user = self._require_user()
        if not user:
            return

        try:
            payload = self._payload()
            result = build_prediction_result(payload)
            AUTH.audit("predict_risk", user["role"], self.client_address[0])
            self._json(result)
        except Exception as exc:  # Keep demo API resilient and visible.
            LOGGER.exception("Prediction failed")
            self._json({"error": str(exc)}, status=400)

    def do_DELETE(self) -> None:
        self._begin_request()
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/admin/accounts/"):
            if not self._require_role({"admin"}):
                return
            self._handle_admin_delete_account(parsed.path.rsplit("/", 1)[-1])
            return
        self._json({"error": "Not found"}, status=404)

    def _handle_login(self) -> None:
        try:
            payload = self._payload()
            auth_result, error = AUTH.login(
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                ip_address=self.client_address[0],
            )
            if not auth_result:
                self._json({"error": error or "Invalid username or password"}, status=401)
                return
            if auth_result.get("mfa_required"):
                self._json(auth_result)
                return
            self._json(
                {"ok": True, "user": auth_result["user"]},
                headers=self._auth_cookies(auth_result),
            )
        except Exception:
            LOGGER.exception("Login failed unexpectedly")
            self._json({"error": "Login failed"}, status=400)

    def _handle_verify_mfa(self) -> None:
        try:
            payload = self._payload()
            auth_result, error = AUTH.verify_mfa(
                challenge_id=str(payload.get("challenge_id", "")),
                otp=str(payload.get("otp", "")),
                ip_address=self.client_address[0],
            )
            if not auth_result:
                self._json({"error": error or "OTP verification failed"}, status=401)
                return
            self._json(
                {"ok": True, "user": auth_result["user"]},
                headers=self._auth_cookies(auth_result),
            )
        except Exception:
            LOGGER.exception("MFA verification failed unexpectedly")
            self._json({"error": "MFA verification failed"}, status=400)

    def _handle_signup(self) -> None:
        try:
            payload = self._payload()
            auth_result, error = AUTH.signup(
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                display_name=str(payload.get("display_name", "")),
                email=str(payload.get("email", "")),
                phone="",
                otp_delivery="email",
                ip_address=self.client_address[0],
            )
            if not auth_result:
                self._json({"error": error or "Sign up failed"}, status=400)
                return
            if auth_result.get("mfa_required"):
                self._json(auth_result)
                return
            self._json(
                {"ok": True, "user": auth_result["user"]},
                headers=self._auth_cookies(auth_result),
            )
        except Exception:
            LOGGER.exception("Sign up failed unexpectedly")
            self._json({"error": "Sign up failed"}, status=400)

    def _handle_admin_create_account(self) -> None:
        try:
            payload = self._payload()
            created, error = AUTH.admin_create_user(
                username=str(payload.get("username", "")),
                password=str(payload.get("password", "")),
                display_name=str(payload.get("display_name", "")),
                email=str(payload.get("email", "")),
                role=str(payload.get("role", "user")),
                ip_address=self.client_address[0],
            )
            if not created:
                self._json({"error": error or "Could not create account"}, status=400)
                return
            self._json({"ok": True, "account": created})
        except Exception:
            LOGGER.exception("Admin account creation failed unexpectedly")
            self._json({"error": "Could not create account"}, status=400)

    def _handle_admin_delete_account(self, account_id: str) -> None:
        try:
            subject = AUTH.session_subject(self._access_token())
            if not subject:
                self._json({"error": "Login required"}, status=401)
                return
            deleted, error = AUTH.admin_delete_user(
                account_id=account_id,
                acting_account_id=str(subject.get("account_id", "")),
                ip_address=self.client_address[0],
            )
            if not deleted:
                self._json({"error": error or "Could not remove account"}, status=400)
                return
            self._json({"ok": True})
        except Exception:
            LOGGER.exception("Admin account deletion failed unexpectedly")
            self._json({"error": "Could not remove account"}, status=400)

    def _handle_refresh(self) -> None:
        try:
            auth_result = AUTH.refresh_session(self._refresh_token(), self.client_address[0])
            if not auth_result:
                self._json({"error": "Refresh token invalid"}, status=401, headers=self._expired_cookies())
                return
            self._json(
                {"ok": True, "user": auth_result["user"]},
                headers=[("Set-Cookie", self._access_cookie(auth_result["access_token"]))],
            )
        except Exception:
            LOGGER.exception("Token refresh failed unexpectedly")
            self._json({"error": "Token refresh failed"}, status=400)

    def _handle_google_login(self) -> None:
        try:
            if os.getenv("SHIPSENSE_GOOGLE_DEMO", "true").strip().lower() in {"0", "false", "no", "off"}:
                self._json({"error": "Google SSO demo is disabled"}, status=400)
                return
            auth_result = AUTH.google_demo_login(self.client_address[0])
            self._json(
                {"ok": True, "user": auth_result["user"], "provider": "google-demo"},
                headers=self._auth_cookies(auth_result),
            )
        except Exception:
            LOGGER.exception("Google SSO demo login failed unexpectedly")
            self._json({"error": "Google SSO login failed"}, status=400)

    def _handle_google_oauth_start(self) -> None:
        state = secrets.token_urlsafe(24)
        auth_url, error = AUTH.google_authorization_url(self._google_redirect_uri(), state)
        if not auth_url:
            self._redirect(
                self._oauth_redirect_target("google-error", error or "Google sign-in is not configured."),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return
        self._redirect(
            auth_url,
            headers=[("Set-Cookie", self._google_state_cookie(state))],
        )

    def _handle_google_oauth_callback(self, parsed) -> None:
        params = parse_qs(parsed.query)
        if params.get("error"):
            message = params.get("error_description", [params["error"][0]])[0]
            self._redirect(
                self._oauth_redirect_target("google-error", message),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return

        state = params.get("state", [""])[0]
        if not state or state != self._google_state():
            self._redirect(
                self._oauth_redirect_target("google-error", "Google sign-in state could not be verified. Please try again."),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return

        code = params.get("code", [""])[0]
        if not code:
            self._redirect(
                self._oauth_redirect_target("google-error", "Google sign-in did not return an authorization code."),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return

        profile, error = AUTH.google_profile_from_code(code, self._google_redirect_uri())
        if not profile:
            self._redirect(
                self._oauth_redirect_target("google-error", error or "Google sign-in could not be completed."),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return

        auth_result, error = AUTH.google_oauth_login(profile, self.client_address[0])
        if not auth_result:
            self._redirect(
                self._oauth_redirect_target("google-error", error or "Google sign-in could not create a session."),
                headers=[("Set-Cookie", self._clear_google_state_cookie())],
            )
            return

        self._redirect(
            self._oauth_redirect_target("google-success"),
            headers=self._auth_cookies(auth_result) + [("Set-Cookie", self._clear_google_state_cookie())],
        )

    def _payload(self) -> dict:
        """Decode a JSON request body into a Python dictionary."""
        length = int(self.headers.get("Content-Length", "0"))
        if length == 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body or "{}")

    def _access_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie(raw_cookie)
        if "shipsense_access" in jar:
            return jar["shipsense_access"].value
        if "shipsense_session" in jar:
            return jar["shipsense_session"].value
        return None

    def _refresh_token(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie(raw_cookie)
        if "shipsense_refresh" not in jar:
            return None
        return jar["shipsense_refresh"].value

    def _session_user(self) -> dict | None:
        return AUTH.get_session(self._access_token())

    def _require_user(self) -> dict | None:
        user = self._session_user()
        if not user:
            self._json({"error": "Login required"}, status=401)
            return None
        return user

    def _require_role(self, roles: set[str]) -> dict | None:
        user = self._require_user()
        if not user:
            return None
        if user.get("role") not in roles:
            self._json({"error": "Forbidden for this role"}, status=403)
            return None
        return user

    def _auth_cookies(self, auth_result: dict) -> list[tuple[str, str]]:
        return [
            ("Set-Cookie", self._access_cookie(auth_result["access_token"])),
            ("Set-Cookie", self._refresh_cookie(auth_result["refresh_token"])),
        ]

    def _access_cookie(self, token: str) -> str:
        jar = cookies.SimpleCookie()
        jar["shipsense_access"] = token
        jar["shipsense_access"]["path"] = "/"
        jar["shipsense_access"]["httponly"] = True
        jar["shipsense_access"]["samesite"] = "Lax"
        jar["shipsense_access"]["max-age"] = str(ACCESS_SECONDS)
        return jar.output(header="").strip()

    def _refresh_cookie(self, token: str) -> str:
        jar = cookies.SimpleCookie()
        jar["shipsense_refresh"] = token
        jar["shipsense_refresh"]["path"] = "/"
        jar["shipsense_refresh"]["httponly"] = True
        jar["shipsense_refresh"]["samesite"] = "Lax"
        jar["shipsense_refresh"]["max-age"] = str(REFRESH_SECONDS)
        return jar.output(header="").strip()

    def _expired_cookies(self) -> list[tuple[str, str]]:
        headers = []
        for name in ("shipsense_access", "shipsense_refresh", "shipsense_session", "shipsense_google_state"):
            jar = cookies.SimpleCookie()
            jar[name] = ""
            jar[name]["path"] = "/"
            jar[name]["httponly"] = True
            jar[name]["samesite"] = "Lax"
            jar[name]["max-age"] = "0"
            headers.append(("Set-Cookie", jar.output(header="").strip()))
        return headers

    def _json(self, payload: dict, status: int = 200, headers: list[tuple[str, str]] | None = None) -> None:
        """Send a JSON response with the correct content headers."""
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self._record_metric(status)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(encoded)

    def _text(self, text: str, status: int = 200, content_type: str = "text/plain") -> None:
        encoded = text.encode("utf-8")
        self._record_metric(status)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _redirect(self, location: str, headers: list[tuple[str, str]] | None = None, status: int = 302) -> None:
        self._record_metric(status)
        self.send_response(status)
        self.send_header("Location", location)
        for key, value in headers or []:
            self.send_header(key, value)
        self.end_headers()

    def _oauth_redirect_target(self, outcome: str, message: str | None = None) -> str:
        params = {"oauth": outcome}
        if message:
            params["message"] = message
        return f"/index.html?{urlencode(params)}"

    def _google_redirect_uri(self) -> str:
        configured = os.getenv("SHIPSENSE_GOOGLE_REDIRECT_URI", "").strip()
        if configured:
            return configured
        return f"{self._base_url()}/auth/google/callback"

    def _base_url(self) -> str:
        proto = self.headers.get("X-Forwarded-Proto", "http").strip() or "http"
        host = self.headers.get("Host", "127.0.0.1:8000").strip() or "127.0.0.1:8000"
        return f"{proto}://{host}"

    def _google_state(self) -> str | None:
        raw_cookie = self.headers.get("Cookie", "")
        jar = cookies.SimpleCookie(raw_cookie)
        if "shipsense_google_state" not in jar:
            return None
        return jar["shipsense_google_state"].value

    def _google_state_cookie(self, state: str) -> str:
        jar = cookies.SimpleCookie()
        jar["shipsense_google_state"] = state
        jar["shipsense_google_state"]["path"] = "/"
        jar["shipsense_google_state"]["httponly"] = True
        jar["shipsense_google_state"]["samesite"] = "Lax"
        jar["shipsense_google_state"]["max-age"] = "300"
        return jar.output(header="").strip()

    def _clear_google_state_cookie(self) -> str:
        jar = cookies.SimpleCookie()
        jar["shipsense_google_state"] = ""
        jar["shipsense_google_state"]["path"] = "/"
        jar["shipsense_google_state"]["httponly"] = True
        jar["shipsense_google_state"]["samesite"] = "Lax"
        jar["shipsense_google_state"]["max-age"] = "0"
        return jar.output(header="").strip()

    def _record_metric(self, status: int) -> None:
        started_at = getattr(self, "_request_started_at", time.perf_counter())
        duration = time.perf_counter() - started_at
        role = "anonymous"
        raw_cookie = self.headers.get("Cookie", "")
        if raw_cookie:
            user = AUTH.get_session(self._access_token())
            if user:
                role = str(user.get("role", "anonymous"))
        METRICS.record_http(self.command, urlparse(self.path).path, status, duration, trace_id=getattr(self, "_trace_id", ""), role=role)

    def _begin_request(self) -> None:
        self._request_started_at = time.perf_counter()
        self._trace_id = f"req_{secrets.token_hex(6)}"

    def _platform_status(self) -> dict:
        queue_backend = PREDICTION_QUEUE.stats().get("backend", "sqlite")
        return {
            "green": {
                "status": "done",
                "items": ["login", "signup", "PII protection", "Docker Compose", "REST API", "logs"],
            },
            "yellow": {
                "status": "done",
                "items": ["MFA OTP", "access/refresh cookies", "RBAC", "audit endpoint", "metrics"],
            },
            "blue": {
                "status": "done",
                "items": [
                    "Google sign-in",
                    "Redis queue" if queue_backend == "redis" else "Redis queue ready",
                    "two workers",
                    "idempotency",
                    "Minikube manifests",
                ],
            },
            "queue": PREDICTION_QUEUE.stats(),
            "oauth": {
                "google_configured": AUTH.google_oauth_configured(),
                "google_demo_enabled": os.getenv("SHIPSENSE_GOOGLE_DEMO", "true").strip().lower()
                not in {"0", "false", "no", "off"}
            },
        }

    def _observability_stack(self) -> list[dict]:
        queue_stats = PREDICTION_QUEUE.stats()
        fluent_bit_ready = (ROOT / "logging" / "fluent-bit" / "fluent-bit.conf").exists()
        kibana_ready = "kibana" in (ROOT / "docker-compose.yml").read_text(errors="replace")
        elasticsearch_ready = "elasticsearch" in (ROOT / "docker-compose.yml").read_text(errors="replace")
        return [
            {
                "service": "shipsense-api",
                "status": "live",
                "detail": "Admin APIs, metrics, audit trail, and log file are active.",
            },
            {
                "service": "database-backend",
                "status": getattr(AUTH.db, "name", "sqlite"),
                "detail": "Auth, sessions, MFA challenges, and SQL queue fallback share the configured relational backend.",
            },
            {
                "service": "openai-agent",
                "status": "configured" if bool(os.getenv("OPENAI_API_KEY", "").strip()) else "not configured",
                "detail": "OpenAI key is used only on the backend; the frontend never receives it.",
            },
            {
                "service": "request-tracing",
                "status": "live",
                "detail": "Recent requests are buffered in-memory with trace IDs and response timing.",
            },
            {
                "service": "queue-backend",
                "status": queue_stats.get("backend", "sqlite"),
                "detail": f"Workers active: {queue_stats.get('workers', 0)}. Status counts: {queue_stats.get('statuses', {})}.",
            },
            {
                "service": "fluent-bit",
                "status": "ready" if fluent_bit_ready else "not configured",
                "detail": "Docker logging profile tails app.log and forwards it into Elasticsearch.",
            },
            {
                "service": "elasticsearch",
                "status": "ready" if elasticsearch_ready else "not configured",
                "detail": "Holds indexed application logs for Kibana search and dashboards.",
            },
            {
                "service": "kibana",
                "status": "ready" if kibana_ready else "not configured",
                "detail": "Visual log exploration target for judges when the logging profile is started.",
            },
        ]


def main() -> None:
    """Start the local dashboard/API server."""
    parser = argparse.ArgumentParser(description="Run the ShipSense AI dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    worker_count = max(2, int(os.getenv("SHIPSENSE_WORKERS", "2")))
    PREDICTION_QUEUE.start_workers(worker_count, build_prediction_result, LOGGER)
    handler = partial(ShipSenseHandler, directory=str(STATIC_DIR))
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"ShipSense AI running at http://{args.host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
