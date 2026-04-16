# ShipSense AI R&D Report

## Executive Summary

ShipSense AI is a predictive delay and risk intelligence agent for container shipments. It accepts a natural-language or structured shipment request, combines historical shipment performance with external risk signals, and returns a transparent risk score, explanation, and mitigation plan.

The solution is designed for DeepFrog Hackstorm'26 Track 2: Predictive Delay and Risk Intelligence Agent. It is intentionally explainable, API-first, and easy to extend into a production-grade logistics platform.

## DeepFrog AI Context

Publicly available information about DeepFrog AI is limited, so this section uses only verifiable public sources and avoids assuming internal company history.

- The official domain is `deepfrog.ai`, which publicly positions the brand around exploring AI.
- A public F6S profile for DeepFrog AI F.Z.C describes the company as a Dubai-based AI product development company focused on logistics, freight, supply chains, and mission-critical industries. The same profile lists products such as Pangents and Frognosis and states the profile was founded in 2025.
- Public Indian company-registration/profile pages list Deepfrog AI Solutions Private Limited with CIN `U62013TN2024PTC172463`, incorporated on 05 August 2024 in Tamil Nadu, India.

R&D interpretation: DeepFrog's public footprint points toward AI platforms for logistics and enterprise operations. ShipSense AI aligns with that direction by converting logistics data into proactive, agentic decisions rather than passive tracking.

## Problem Research

Shipment delay prediction is valuable because logistics teams usually discover risk after the delay has already started. The R&D goal is to shift from reactive shipment tracking to proactive exception management.

Key risk sources:

- Historical route and carrier performance
- Destination-port congestion
- Weather severity around port approach
- News and operations alerts
- Route-specific disruptions
- Time-to-arrival pressure and cargo sensitivity

Industry fit:

- BCG reported in March 2026 that more than 40% of shippers now factor AI capabilities into logistics provider selection, while scaled adoption remains limited. This supports a hackathon opportunity: a focused, explainable agent that can move from prototype to operational pilot.
- DHL's Logistics Trend Radar 7.0 highlights AI trends including Generative AI, AI Ethics, Computer Vision, and Advanced Analytics as important logistics drivers. ShipSense AI fits the Advanced Analytics and AI Ethics angle because it explains its decision instead of only producing a score.

## Solution Objective

Build an agent that answers:

```text
Shipment arriving at Jebel Ali in 3 days - identify risks
```

with:

- Delay risk score from 0 to 100
- Delay probability
- Confidence score
- Ranked risk factors
- Evidence for each factor
- Mitigation recommendations
- Alternate port options
- Validation warnings for weak input data

## Current MVP Architecture

```text
Browser Dashboard
    |
    | POST /api/predict-risk
    v
Python API Server
    |
    | loads
    v
Historical CSV + External Signals JSON
    |
    v
Transparent Risk Agent
    |
    v
Risk Score + Explanation + Mitigation Plan
    |
    +--> Optional OpenAI Explanation Agent
    |
    +--> Optional Async Prediction Queue + Worker Pool
```

## Data Sources

Current demo sources:

- `data/historical_shipments.csv`: route, carrier, cargo, delay status, delay hours, weather severity, congestion index, news level
- `data/external_signals.json`: weather, port congestion, news alerts, route alerts, alternate ports, mitigation notes

OpenAI agent layer when `OPENAI_API_KEY` is configured:

- OpenAI Responses API converts the calculated score, factors, and mitigations into a professional explanation
- The backend sends only non-secret shipment evidence and never exposes the API key to the browser

Optional live sources if the project is expanded later:

- OpenWeather Current Weather API for destination-port weather
- NewsAPI Everything endpoint for recent destination-port logistics news

Production replacements:

- Shipment TMS/ERP history
- Real weather API
- Port congestion API or AIS-derived vessel/berth data
- News API or port advisory feed
- Carrier schedule API
- Customs and documentation status

## Risk Model Design

ShipSense AI uses a transparent weighted model:

- Historical delay pattern: route and carrier delay behavior
- Port congestion: congestion index and berth wait hours
- Weather exposure: weather severity near destination
- News and operations alerts: maximum alert severity
- Route disruption signal: route-specific alert risk
- Time-to-arrival pressure: urgency, cargo type, and ETA window

The model intentionally returns factor-level evidence. This is better for R&D and judge evaluation than a black-box ML model, because the team can explain why a shipment was marked high risk.

## Data Quality Controls

The app now treats the origin field as an **origin port**, not just any city.

Valid origin ports in the demo:

- Chennai
- Cochin
- Colombo
- Mumbai
- Mundra
- Nhava Sheva
- Rotterdam
- Shanghai
- Singapore

Example: Delhi is excluded because it is an inland city and not a port in this demo scope. If someone calls the API directly with Delhi, the agent returns a warning and reduces confidence instead of pretending the result is fully reliable.

## Why This Is Professional

- API-first backend with clear endpoints
- Explainable risk score, not an opaque number
- Input validation for origin-port quality
- Multiple data sources as required by the problem statement
- Mitigation plan that can be acted on by operations teams
- Browser dashboard for judges and non-technical users
- MFA, access/refresh cookies, RBAC, and audit logging for platform security
- Metrics endpoint plus Prometheus/Grafana configuration for observability
- Async queue, two workers, atomic pickup, and idempotency for scalable processing
- Minikube manifest for container deployment demonstration
- Clear upgrade path to FastAPI, database storage, and real APIs

## Roadmap

Phase 1: Hackathon MVP

- Transparent scoring model
- Demo dataset
- Dashboard
- Recommendations
- Alternate ports
- Green, Yellow, and Blue checklist implementation

Phase 2: R&D Pilot

- Use OpenAI for explanation generation while replacing JSON feeds with enterprise logistics APIs over time
- Add database-backed shipment history
- Train a logistic regression or gradient boosting baseline
- Compare transparent score vs ML score
- Add audit logging for every prediction
- Replace demo Google SSO with production Google OAuth/OIDC
- Move async jobs from SQLite to Redis, PostgreSQL, or a cloud queue

Phase 3: Production

- Real-time carrier schedule integration
- AIS and berth-congestion ingestion
- User-specific alert preferences
- Human-in-the-loop approval for reroute actions
- SLA and cost impact estimates

## Judge Demo Script

1. Open the dashboard.
2. Keep the default query: `Shipment arriving at Jebel Ali in 3 days - identify risks`.
3. Show the risk score and delay probability.
4. Explain the top risk factors.
5. Show that multiple sources are used: historical data, local signal feeds, port congestion, route alerts, and OpenAI explanation.
6. Show mitigation recommendations and alternate ports.
7. Mention the origin-port validation: inland cities like Delhi are excluded from valid origin ports.
8. Show the Platform section: MFA, RBAC, audit, metrics, queue workers, idempotency, and Minikube readiness.
9. Explain how the demo can be upgraded with real APIs and ML.

## Sources

- DeepFrog official domain: https://deepfrog.ai/
- DeepFrog AI F.Z.C public F6S profile: https://www.f6s.com/company/deepfrog-ai-f.z.c
- Deepfrog AI Solutions Private Limited public profile: https://www.tofler.in/deepfrog-ai-solutions-private-limited/company/U62013TN2024PTC172463
- Deepfrog AI Solutions Private Limited public company check: https://www.thecompanycheck.com/company/deepfrog-ai-solutions-private-limited/U62013TN2024PTC172463
- BCG logistics AI adoption press release, March 2026: https://www.bcg.com/press/27march2026-ai-expectations-rise-in-logistics-scaled-adoption-remains-limited
- DHL Logistics Trend Radar 7.0 press release, September 2024: https://group.dhl.com/en/media-relations/press-releases/2024/dhl-logistics-trend-radar-unveils-emerging-ai-trends-and-sustainable-solutions.html
