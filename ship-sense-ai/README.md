# ShipSense AI

Predictive Delay and Risk Intelligence Agent for DeepFrog Hackstorm'26 Track 2.

## R&D Positioning

ShipSense AI is designed as an explainable logistics risk agent. It predicts delay risk before a movement arrives, explains the main causes, and recommends mitigation actions across air, road, rail, and waterways.

R&D documents:

- `docs/R_AND_D_REPORT.md` - company context, research, architecture, model design, roadmap, and sources
- `docs/PRESENTATION_NOTES.md` - judge-friendly demo script and Q&A answers

## What it does

ShipSense AI accepts a transport query such as:

```text
Cargo aircraft from Mumbai Air Cargo to Dubai International Cargo arriving in 2 days - identify risks
```

It combines:

- Historical transport outcomes from `data/historical_shipments.csv`
- Hub operations, weather, news, and route alert signals from `data/external_signals.json`
- OpenAI API, when configured, to write the final explanation and mitigation plan from the calculated evidence

The API returns a delay risk score, probability, explanation, contributing factors, reroute options, and mitigation steps.

The origin field is treated as an **origin hub** for the selected mode. If an invalid origin is sent directly to the API, ShipSense AI lowers confidence and returns a validation warning.

## Screenshots

![ShipSense AI Login](assets/login%20page.png)

![ShipSense AI Dashboard 1](assets/dashboard1.png)

![ShipSense AI Dashboard 2](assets/dashboard2.png)

![ShipSense AI Dashboard 3](assets/dashboard3.png)

## Mandatory demo login

Default local demo users:

```text
admin / admin123
analyst / analyst123
```

New users can also be created from the **Sign up** button on the login page. New accounts are created with the `user` role and must include an email address or phone number for OTP delivery.

MFA is enabled by default for login. OTP is no longer shown inside the UI. It is delivered by backend email or by a phone/SMS webhook channel if configured.

Override these in production or Docker with:

```bash
SHIPSENSE_ADMIN_PASSWORD=...
SHIPSENSE_ANALYST_PASSWORD=...
SHIPSENSE_SECRET=...
SHIPSENSE_MFA_ENABLED=true
SHIPSENSE_ADMIN_EMAIL=ops@example.com
SHIPSENSE_ANALYST_EMAIL=analyst@example.com
```

By default, the auth and async-job tables are auto-created in local SQLite files under `data/`. If `SHIPSENSE_DATABASE_URL` points at PostgreSQL, the same auth and queue tables are created there instead.

## Database backend

ShipSense AI is now database-independent for its relational state:

- default local mode: SQLite files in `data/`
- production-ready option: PostgreSQL through `SHIPSENSE_DATABASE_URL`

Example PostgreSQL connection string:

```text
SHIPSENSE_DATABASE_URL=postgresql://shipsense:shipsense@127.0.0.1:5432/shipsense
```

The app keeps the same tables and API behavior across both backends, so the live demo can stay lightweight on SQLite while deployment can move to PostgreSQL.

## Google sign-in setup

ShipSense AI now supports a real Google OAuth redirect flow from the login page. To enable it, add these backend variables to `.env`:

```text
SHIPSENSE_GOOGLE_CLIENT_ID=your_google_web_client_id
SHIPSENSE_GOOGLE_CLIENT_SECRET=your_google_web_client_secret
SHIPSENSE_GOOGLE_REDIRECT_URI=http://127.0.0.1:8015/auth/google/callback
```

In Google Cloud Console, create a **Web application** OAuth client and add the same redirect URI there. Google’s web-server OAuth guidance recommends using the authorization-code redirect flow and registering exact redirect URIs for local testing: [Google OAuth 2.0 for Web Server Applications](https://developers.google.com/identity/protocols/oauth2/web-server).

The login page button redirects the user to Google, fetches the Google profile after consent, and creates or resumes the ShipSense session using the verified account email and display name.

## OTP delivery setup

To use email OTP delivery, add these backend variables to `.env`:

```text
SHIPSENSE_SMTP_HOST=smtp.your-provider.com
SHIPSENSE_SMTP_PORT=587
SHIPSENSE_SMTP_USERNAME=your_smtp_username
SHIPSENSE_SMTP_PASSWORD=your_smtp_password
SHIPSENSE_SMTP_FROM=your_verified_sender@example.com
SHIPSENSE_SMTP_TLS=true
SHIPSENSE_ADMIN_EMAIL=ops@example.com
SHIPSENSE_ANALYST_EMAIL=analyst@example.com
```

This build now uses SMTP email as the OTP delivery channel for signup and login verification.

## API key for OpenAI agent

The app works without API keys by using deterministic explanations. For your current setup, use only the OpenAI key. Keep the key on the backend in `.env`; it is not exposed in frontend JavaScript or browser API calls. Create a `.env` file in the project root and add the key locally:

```bash
cd /Users/rudrasahu/Documents/Playground/ship-sense-ai
touch .env
```

Edit `.env`:

```text
OPENAI_API_KEY=your_new_openai_key_here
OPENAI_MODEL=gpt-5-mini
SHIPSENSE_SECRET=replace-this-local-secret
```

Do not paste API keys into frontend files. The backend reads keys from `.env` or environment variables, and the browser only sees whether live sources are configured.

Optional live signal providers are still supported later, but they are not required for the OpenAI-only demo:

- OpenWeather Current Weather API
- NewsAPI Everything endpoint

## Admin observability

Admin users now have an in-app observability console that shows:

- recent audit events
- recent request traces with trace IDs and latency
- live application log display from `logs/app.log`
- stack readiness for ShipSense API, OpenAI backend usage, queue backend, Fluent Bit, Elasticsearch, and Kibana

This keeps the OpenAI key on the backend while still letting judges see operations data in the admin UI.

## Fluent Bit, Elasticsearch, and Kibana

The repo now includes a Docker logging profile for a full log pipeline:

- `logging/fluent-bit/fluent-bit.conf`
- `logging/fluent-bit/parsers.conf`
- `docker-compose.yml` services for `fluent-bit`, `elasticsearch`, and `kibana`

Run it with:

```bash
docker compose --profile logging up --build
```

Then open:

- Elasticsearch: `http://127.0.0.1:9200`
- Kibana: `http://127.0.0.1:5601`

Fluent Bit tails `logs/app.log` and forwards ShipSense log lines into Elasticsearch so they can be searched in Kibana.

## Run

### Local queue backend

ShipSense AI now supports a Redis-backed async queue. The app chooses the queue backend like this:

- if `SHIPSENSE_QUEUE_BACKEND=redis` or `SHIPSENSE_REDIS_URL` is set, it uses Redis
- otherwise it falls back to the SQL queue stored in SQLite by default or PostgreSQL when `SHIPSENSE_DATABASE_URL` is configured

For a local Redis setup, add this to `.env`:

```text
SHIPSENSE_QUEUE_BACKEND=redis
SHIPSENSE_REDIS_URL=redis://127.0.0.1:6379/0
SHIPSENSE_REDIS_PREFIX=shipsense
```

If Redis is not running locally, the app can still run with the SQLite fallback.

### PostgreSQL mode

To move auth and queued jobs into PostgreSQL, add this to `.env`:

```text
SHIPSENSE_DATABASE_URL=postgresql://shipsense:shipsense@127.0.0.1:5432/shipsense
```

The app will still keep Redis optional for the async queue. If Redis is off, the queue uses the same PostgreSQL database with atomic row locking.

With Docker Compose, you can start PostgreSQL locally with:

```bash
docker compose --profile database up --build
```

Use this matching connection string from the app container:

```text
SHIPSENSE_DATABASE_URL=postgresql://shipsense:shipsense@postgres:5432/shipsense
```

```bash
cd /Users/rudrasahu/Documents/Playground/ship-sense-ai
python3 app.py
```

Open:

```text
http://127.0.0.1:8000/index.html?v=18
```

## Run on Windows

1. Install Python 3 from https://www.python.org/downloads/windows/ and tick **Add Python to PATH** during setup.
2. Copy the `ship-sense-ai` folder to the Windows system.
3. Open Command Prompt or PowerShell.
4. Go to the project folder:

```powershell
cd C:\path\to\ship-sense-ai
```

5. Start the app:

```powershell
py -B app.py --port 8000
```

6. Open this in the same Windows system:

```text
http://127.0.0.1:8000
```

To let other systems on the same Wi-Fi open it, run:

```powershell
py -B app.py --host 0.0.0.0 --port 8000
```

Then find the Windows laptop IPv4 address:

```powershell
ipconfig
```

Other devices on the same Wi-Fi can open:

```text
http://YOUR-WINDOWS-IP:8000
```

## API

```bash
curl -X POST http://127.0.0.1:8000/api/predict-risk \
  -H "Content-Type: application/json" \
  -d '{"query":"Truck from Mumbai Logistics Park to Bengaluru Distribution Hub arriving in 3 days - identify risks"}'
```

Useful endpoints:

- `GET /api/health`
- `POST /api/login`
- `POST /api/signup`
- `POST /api/verify-mfa`
- `POST /api/refresh`
- `GET /api/me`
- `POST /api/logout`
- `GET /api/security-policy`
- `GET /api/live-sources`
- `GET /api/auth-providers`
- `GET /api/platform-status`
- `GET /api/rbac-policy`
- `GET /api/observability` admin only
- `GET /api/admin/audit` admin only
- `GET /api/admin/logs` admin only
- `GET /api/admin/traces` admin only
- `GET /api/admin/overview` admin only
- `GET /api/ports`
- `GET /api/origins`
- `GET /api/shipments`
- `GET /api/signals`
- `GET /api/network`
- `POST /api/predict-risk`
- `POST /api/prediction-jobs`
- `GET /api/prediction-jobs/{job_id}`
- `POST /api/google-login`
- `GET /auth/google/start`
- `GET /auth/google/callback`
- `GET /metrics`

## Yellow and Blue features

Security and observability:

- OTP-based MFA login flow with backend email or phone delivery
- Short-lived access cookie plus longer-lived refresh cookie
- Admin/user RBAC with admin-only audit and observability endpoints
- Audit events stored without raw user/IP identifiers
- In-app admin log display and request-trace panel for judge demos
- Prometheus metrics endpoint at `/metrics`
- Optional Prometheus/Grafana Docker profile
- Optional Fluent Bit, Elasticsearch, and Kibana logging profile

Scale and deployment:

- Google OAuth redirect flow through `/auth/google/start` and `/auth/google/callback`
- Redis-backed async prediction queue through `/api/prediction-jobs` when configured
- At least two background workers started by the app
- Job lock recovery and idempotency support across Redis or SQL fallback
- Idempotency-key deduplication for repeated async requests
- Minikube manifest at `k8s/shipsense-minikube.yaml`

## Hackathon demo flow

1. Run the app.
2. Configure backend email delivery, then login as `admin / admin123` or create a new account with **Sign up**.
3. Enter the OTP delivered to the configured email or phone channel.
4. Choose a transport mode and route, then click **Analyze shipment**.
5. Show the risk score, factor explanation, data-source chips, and mitigation plan.
6. If the OpenAI key is valid, show the `OpenAI agent ready` / `OpenAI agent used` badge. If it shows `OpenAI fallback`, replace the key in `.env` with a fresh active key and restart the app.
7. Click **Queue async analysis** to show the two-worker queue and idempotency workflow.
8. Open the Platform section to show Green, Yellow, and Blue completion status.

## Professional upgrade path

- Replace demo JSON feeds with live weather, port, news, and carrier APIs.
- Store shipment history in PostgreSQL or a logistics data warehouse.
- Benchmark this transparent weighted model against logistic regression or gradient boosting.
- Keep factor-level explanations so operations teams can trust and audit predictions.
- Add alert subscriptions for high-risk shipments.
- Replace the Google demo adapter with production Google OAuth/OIDC.
- Scale beyond the built-in SQL queue by adding Redis Streams, a cloud task queue, or partitioned PostgreSQL workers for higher throughput.

## Public DeepFrog context

Public information about DeepFrog AI is limited, so this project only uses verifiable external references in the R&D report. Public profiles point toward AI platforms for logistics, freight, supply chains, and mission-critical industries, which is why this solution focuses on agentic logistics risk intelligence.

## Docker Compose

Run the mandatory Docker setup:

```bash
cd /Users/rudrasahu/Documents/Playground/ship-sense-ai
docker compose up --build
```

Open:

```text
http://127.0.0.1:8000/index.html?v=10
```

The stack runs in one Docker network named `shipsense-net`.

Run with observability:

```bash
docker compose --profile observability up --build
```

Prometheus opens at:

```text
http://127.0.0.1:9090
```

Grafana opens at:

```text
http://127.0.0.1:3000
```

## Minikube

Build and load the local image:

```bash
minikube start
minikube image build -t shipsense-ai:local .
kubectl apply -f k8s/shipsense-minikube.yaml
```

Open the service:

```bash
minikube service shipsense-api -n shipsense
```
