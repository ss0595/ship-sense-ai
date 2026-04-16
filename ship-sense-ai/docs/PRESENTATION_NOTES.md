# ShipSense AI Presentation Notes

## 30-Second Opening

ShipSense AI is a predictive delay and risk intelligence agent for shipments. It does not just track a shipment after a delay happens. It predicts delay risk in advance by combining historical shipment outcomes with port and route signals, then uses OpenAI to generate a clear explanation and mitigation plan from the calculated evidence.

## Why DeepFrog Fit

DeepFrog AI's public profile focuses on intelligent platforms for logistics, freight, supply chains, and mission-critical industries. ShipSense AI matches that direction because it turns logistics signals into proactive decisions.

## Problem

Most logistics systems are reactive. Teams often know a shipment is late only after the ETA has already slipped. This causes missed planning windows, warehouse disruption, customer dissatisfaction, and higher exception-management cost.

## Solution

ShipSense AI acts like a logistics control tower:

- It accepts a natural-language shipment query.
- It validates important fields like origin port.
- It checks historical route behavior.
- It checks operational conditions like port congestion, local signal feeds, and route alerts.
- If `OPENAI_API_KEY` is configured, OpenAI rewrites the evidence into a professional decision brief.
- It returns risk score, probability, confidence, reasons, and actions.

## Demo Input

```text
Shipment arriving at Jebel Ali in 3 days - identify risks
```

## Demo Output To Highlight

- Risk level: Critical
- Score: around 88
- Probability: around 96%
- Key causes: historical delay pattern, port congestion, time pressure, signal alerts, and route risk
- Mitigation: berth confirmation, document pre-clearance, receiver notification, ETA buffer, alternate port readiness

## Technical Highlights

- Backend API in Python
- Frontend dashboard in HTML/CSS/JavaScript
- Historical CSV dataset
- External signals JSON dataset
- Explainable weighted risk model
- Input validation and confidence adjustment
- OTP MFA with access/refresh cookie split
- RBAC, audit events, metrics, and Prometheus/Grafana configuration
- Async prediction queue with two workers, atomic pickup, and idempotency keys
- Google SSO demo adapter and Minikube deployment manifest
- No dependency installation required for demo

## Strong Answer If Judges Ask About Accuracy

The MVP uses demo data, a transparent weighted model, and an optional OpenAI explanation layer. For production, I would connect real shipment history, port congestion data, carrier schedules, weather, and advisory feeds. Then I would benchmark the current explainable model against logistic regression or gradient boosting, while keeping explanations for user trust.

## Strong Answer If Judges Ask About Security

The app uses MFA, HttpOnly access and refresh cookies, PBKDF2 password hashing, hashed tokens, HMAC-protected user identifiers, RBAC, and audit logging. API keys stay in the backend `.env` file and are never sent to frontend JavaScript.

## Strong Answer If Judges Ask About Scale

The synchronous prediction endpoint is available for demos, but the app also has a queue-backed async prediction path. Two workers atomically pick jobs from SQLite, and idempotency keys prevent duplicate processing when a client retries the same request.

## Strong Answer If Judges Ask About Delhi

Delhi is intentionally removed from the origin dropdown because this field represents an origin port, not an inland pickup city. If an invalid origin is sent directly to the API, the backend returns a validation warning and lowers confidence. This prevents the model from pretending uncertain data is fully accurate.

## Closing

ShipSense AI helps logistics teams move from reactive tracking to proactive risk mitigation. It is useful, explainable, and aligned with DeepFrog's AI-for-logistics direction.
