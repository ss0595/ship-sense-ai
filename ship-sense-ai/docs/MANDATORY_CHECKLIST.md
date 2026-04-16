# Green, Yellow, and Blue Checklist

This file tracks the mandatory and advanced items visible in the provided evaluation screenshots.

## Green: Platform Security

- Login: implemented with `/api/login`, `/api/me`, and `/api/logout`.
- Sign up: implemented with `/api/signup`; new users are safely added with the `user` role.
- PII should not be exposed in frontend API calls: regular dashboard calls use an HttpOnly session cookie and do not send email or raw user identifiers.
- Encryption/protection of PII in DB: the auth database stores no raw email/username. User identifiers are HMAC protected, passwords are PBKDF2 hashed, access/refresh/session tokens are hashed, and display names are stored as protected ciphertext.

## Green: Scalability

- All components dockerized: `Dockerfile` added.
- Single Docker network: `docker-compose.yml` defines `shipsense-net`.
- Single docker-compose file: `docker-compose.yml` runs the app with service discovery through the `shipsense-api` service name.

## Green: Maintainability

- Clean project structure:
  - `backend/` for model/service/security logic
  - `static/` for dashboard view
  - `data/` for demo datasets
  - `observability/` for Prometheus scrape configuration
  - `k8s/` for Minikube deployment manifests
  - `docs/` for R&D and presentation material
- `README.md`: includes problem statement, solution, tech stack, run instructions, and API information.
- MVC-style separation:
  - Model/service: `backend/agent.py`, `backend/data_store.py`, `backend/security.py`, `backend/task_queue.py`
  - View: `static/index.html`, `static/styles.css`
  - Controller/router: `app.py`
- REST API structure:
  - `GET /api/health`
  - `POST /api/login`
  - `POST /api/signup`
  - `POST /api/verify-mfa`
  - `POST /api/refresh`
  - `GET /api/me`
  - `POST /api/logout`
  - `GET /api/security-policy`
  - `GET /api/live-sources`
  - `GET /api/platform-status`
  - `GET /api/rbac-policy`
  - `GET /api/observability`
  - `GET /api/admin/audit`
  - `GET /api/ports`
  - `GET /api/origins`
  - `GET /api/shipments`
  - `GET /api/signals`
  - `POST /api/predict-risk`
  - `POST /api/prediction-jobs`
  - `GET /api/prediction-jobs/{job_id}`
  - `POST /api/google-login`
  - `GET /metrics`
- Error logging: console and file logs are written to `logs/app.log`.

## Yellow: Security And Observability

- MFA / OTP: implemented with `/api/verify-mfa`. Local demo mode can display the OTP for judging; production should deliver OTP by email/SMS.
- Refresh/access token split: implemented with separate HttpOnly `shipsense_access` and `shipsense_refresh` cookies.
- Basic RBAC: implemented with admin/user separation. Admin-only endpoints include audit and observability views.
- Audit trail: implemented in SQLite with hashed IP metadata and no raw user identifiers.
- Observability: implemented with `/metrics`, `/api/observability`, `backend/observability.py`, and `observability/prometheus.yml`.
- Prometheus/Grafana stack: added under Docker Compose `observability` profile.

## Blue: Scale And Deployment

- Google login: implemented as `/api/google-login` demo adapter. Production path is Google OAuth/OIDC credentials.
- Queue-backed async worker architecture: implemented in `backend/task_queue.py`.
- Minimum two workers: app starts at least two async prediction workers through `SHIPSENSE_WORKERS`.
- Atomic task pickup: SQLite `BEGIN IMMEDIATE` locking prevents two workers from claiming the same job.
- Idempotency workflows: `POST /api/prediction-jobs` accepts the `Idempotency-Key` header and deduplicates repeated requests.
- Minikube deployment: `k8s/shipsense-minikube.yaml` defines namespace, secret, config map, deployment, probes, and NodePort service.
