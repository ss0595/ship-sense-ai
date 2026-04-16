# ShipSense AI

Predictive Delay and Risk Intelligence Agent for DeepFrog Hackstorm'26 Track 2.

## R&D Positioning

ShipSense AI is designed as an explainable logistics risk agent. It predicts delay risk before a shipment arrives, explains the main causes, and recommends mitigation actions.

R&D documents:

- `docs/R_AND_D_REPORT.md` - company context, research, architecture, model design, roadmap, and sources
- `docs/PRESENTATION_NOTES.md` - judge-friendly demo script and Q&A answers

## What it does

ShipSense AI accepts a shipment query such as:

```text
Shipment arriving at Jebel Ali in 3 days - identify risks
```

It combines:

- Historical shipment outcomes from `data/historical_shipments.csv`
- Port congestion, weather, news, and route alert signals from `data/external_signals.json`
- OpenAI API, when configured, to write the final explanation and mitigation plan from the calculated evidence

The API returns a delay risk score, probability, explanation, contributing factors, reroute options, and mitigation steps.

The origin field is treated as an **origin port**. Inland non-port cities such as Delhi are excluded from the dropdown. If an invalid origin is sent directly to the API, ShipSense AI lowers confidence and returns a validation warning.

## Mandatory demo login

Default local demo users:

```text
admin / admin123
analyst / analyst123
```

New users can also be created from the **Sign up** button on the login page. New accounts are created with the `user` role.

MFA is enabled by default for login. In local demo mode the OTP appears on the login page so judges can verify the flow without an email provider. Production should set up email/SMS OTP delivery and disable visible demo codes.

Override these in production or Docker with:

```bash
SHIPSENSE_ADMIN_PASSWORD=...
SHIPSENSE_ANALYST_PASSWORD=...
SHIPSENSE_SECRET=...
SHIPSENSE_MFA_ENABLED=true
SHIPSENSE_MFA_DEMO_CODE=false
```

The auth database is auto-created at `data/shipsense_auth.sqlite3`. It is ignored by git.

## API key for OpenAI agent

The app works without API keys by using deterministic explanations. For your current setup, use only the OpenAI key. Copy the example file if needed and add the key locally:

```bash
cd /Users/rudrasahu/Documents/Playground/ship-sense-ai
cp .env.example .env
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

## Run

```bash
cd /Users/rudrasahu/Documents/Playground/ship-sense-ai
python3 app.py
```

Open:

```text
http://127.0.0.1:8000/index.html?v=10
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
  -d '{"query":"Shipment arriving at Jebel Ali in 3 days - identify risks"}'
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
- `GET /api/platform-status`
- `GET /api/rbac-policy`
- `GET /api/observability` admin only
- `GET /api/admin/audit` admin only
- `GET /api/ports`
- `GET /api/origins`
- `GET /api/shipments`
- `GET /api/signals`
- `POST /api/predict-risk`
- `POST /api/prediction-jobs`
- `GET /api/prediction-jobs/{job_id}`
- `POST /api/google-login`
- `GET /metrics`

## Yellow and Blue features

Security and observability:

- OTP-based MFA login flow
- Short-lived access cookie plus longer-lived refresh cookie
- Admin/user RBAC with admin-only audit and observability endpoints
- Audit events stored without raw user/IP identifiers
- Prometheus metrics endpoint at `/metrics`
- Optional Prometheus/Grafana Docker profile

Scale and deployment:

- Google SSO demo adapter through `/api/google-login`
- Async prediction queue through `/api/prediction-jobs`
- At least two background workers started by the app
- Atomic job pickup using SQLite locking
- Idempotency-key deduplication for repeated async requests
- Minikube manifest at `k8s/shipsense-minikube.yaml`

## Hackathon demo flow

1. Run the app.
2. Login as `admin / admin123`, then enter the displayed local OTP.
3. Keep the default Jebel Ali query and click **Analyze shipment**.
4. Show the risk score, factor explanation, data-source chips, and mitigation plan.
5. If the OpenAI key is valid, show the `OpenAI agent ready` / `OpenAI agent used` badge. If it shows `OpenAI fallback`, replace the key in `.env` with a fresh active key and restart the app.
6. Click **Queue async analysis** to show the two-worker queue and idempotency workflow.
7. Open the Platform section to show Green, Yellow, and Blue completion status.

## Professional upgrade path

- Replace demo JSON feeds with live weather, port, news, and carrier APIs.
- Store shipment history in PostgreSQL or a logistics data warehouse.
- Benchmark this transparent weighted model against logistic regression or gradient boosting.
- Keep factor-level explanations so operations teams can trust and audit predictions.
- Add alert subscriptions for high-risk shipments.
- Replace the Google demo adapter with production Google OAuth/OIDC.
- Replace local SQLite queue with Redis, PostgreSQL advisory locks, or a cloud task queue for higher throughput.

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
