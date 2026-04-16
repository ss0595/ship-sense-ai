"""Risk intelligence engine for ShipSense AI.

The model is intentionally transparent for a hackathon/R&D demo. Instead of
returning a black-box score, it computes named risk factors from historical
shipments and external signals, then returns the evidence behind each factor.
That makes the output easier for judges and logistics users to trust.
"""

from __future__ import annotations

import math
import re
from statistics import mean

from backend.reference import is_valid_origin_port


DEFAULT_REQUEST = {
    "origin": "Mumbai",
    "destination_port": "Jebel Ali",
    "arrival_days": 3,
    "carrier": "GulfLink",
    "cargo_type": "Electronics",
    "priority": "High",
    "route": "Mumbai-Jebel Ali",
}


PORT_ALIASES = {
    "jebel ali": "Jebel Ali",
    "dubai": "Jebel Ali",
    "uae": "Jebel Ali",
    "singapore": "Singapore",
    "rotterdam": "Rotterdam",
    "nhava sheva": "Nhava Sheva",
    "jnpt": "Nhava Sheva",
    "shanghai": "Shanghai",
    "colombo": "Colombo",
    "salalah": "Salalah",
    "khalifa": "Khalifa Port",
    "khalifa port": "Khalifa Port",
}


def clamp(value: float, low: float, high: float) -> float:
    """Keep a numeric value inside a fixed score range."""
    return max(low, min(high, value))


def risk_level(score: int) -> str:
    """Convert a 0-100 risk score into an operations-friendly label."""
    if score >= 85:
        return "Critical"
    if score >= 70:
        return "High"
    if score >= 50:
        return "Elevated"
    if score >= 30:
        return "Moderate"
    return "Low"


def parse_inquiry(text: str, signals: dict) -> dict:
    """Extract shipment fields from a short natural-language request.

    Example: "Shipment from Mumbai to Jebel Ali in 3 days, electronics".
    The UI also sends structured fields; this parser is a convenience layer for
    the problem statement's natural-language input requirement.
    """
    lower = (text or "").lower()
    parsed: dict = {}

    for alias, port in PORT_ALIASES.items():
        if alias in lower:
            parsed["destination_port"] = port
            break

    if "destination_port" not in parsed:
        for port in signals.get("ports", {}):
            if port.lower() in lower:
                parsed["destination_port"] = port
                break

    day_match = re.search(r"(?:in|within|eta|arriving in)\s+(\d{1,2})\s*(?:day|days|d)\b", lower)
    if day_match:
        parsed["arrival_days"] = int(day_match.group(1))

    route_match = re.search(r"from\s+([a-z\s]+?)\s+(?:to|towards|->)\s+([a-z\s]+?)(?:\s+in|\s+-|$)", lower)
    if route_match:
        origin = route_match.group(1).strip().title()
        destination = route_match.group(2).strip().title()
        parsed["origin"] = origin
        parsed["route"] = f"{origin}-{destination}"

    cargo_terms = {
        "pharma": "Pharma",
        "medicine": "Pharma",
        "electronics": "Electronics",
        "reefer": "Cold Chain",
        "cold": "Cold Chain",
        "apparel": "Apparel",
        "auto": "Automotive",
        "machinery": "Machinery",
    }
    for term, cargo in cargo_terms.items():
        if term in lower:
            parsed["cargo_type"] = cargo
            break

    if any(word in lower for word in ("urgent", "priority", "critical", "expedite")):
        parsed["priority"] = "High"

    return parsed


def _same(left, right) -> bool:
    return str(left).strip().lower() == str(right).strip().lower()


def _origin_known(origin: str, shipments: list[dict]) -> bool:
    """Return True only when origin is a valid port and exists in history."""
    return is_valid_origin_port(origin) and any(_same(row.get("origin"), origin) for row in shipments)


def _records_for(shipment: dict, shipments: list[dict]) -> dict[str, list[dict]]:
    """Group historical records that can explain the current shipment."""
    port = shipment["destination_port"]
    carrier = shipment["carrier"]
    route = shipment["route"]
    cargo = shipment["cargo_type"]
    return {
        "port": [row for row in shipments if _same(row.get("destination_port"), port)],
        "carrier": [row for row in shipments if _same(row.get("carrier"), carrier)],
        "route": [row for row in shipments if _same(row.get("route"), route)],
        "cargo": [row for row in shipments if _same(row.get("cargo_type"), cargo)],
    }


def _delay_rate(rows: list[dict]) -> float:
    """Calculate delay frequency; use a conservative fallback for no data."""
    if not rows:
        return 0.35
    return mean(1 if row.get("delayed") else 0 for row in rows)


def _average_delay(rows: list[dict]) -> float:
    """Average only delayed rows so the explanation reflects delay severity."""
    delayed_rows = [float(row.get("delay_hours", 0)) for row in rows if row.get("delayed")]
    return mean(delayed_rows) if delayed_rows else 0


def _port_signal(port: str, signals: dict) -> dict:
    """Return the weather/news/congestion signal pack for a destination port."""
    ports = signals.get("ports", {})
    if port in ports:
        return ports[port]
    for known_port, signal in ports.items():
        if known_port.lower() == port.lower():
            return signal
    return {
        "country": "Unknown",
        "region": "Unknown",
        "weather": {"condition": "No specific weather alert", "severity": 30, "wind_kph": 18, "rain_mm": 0},
        "port": {"congestion_index": 35, "berth_wait_hours": 6, "customs_backlog": "Unknown"},
        "news": [{"headline": "No port-specific alert in demo feed", "severity": 25, "source": "Demo feed"}],
        "route_alerts": [],
        "alternate_ports": ["Nearest feasible alternate port"],
        "mitigations": ["Keep six-hourly check-ins with carrier operations"],
    }


def _route_alert_for(route: str, port_signal: dict) -> dict:
    """Find a route-specific alert if the external feed contains one."""
    alerts = port_signal.get("route_alerts", [])
    for alert in alerts:
        if str(alert.get("route", "")).lower() == route.lower():
            return alert
    return {"route": route, "risk": 25, "message": "No route-specific disruption found in the demo feed"}


def _priority_impact(priority: str, cargo_type: str, arrival_days: int) -> float:
    """Add risk pressure for urgent, sensitive, or near-arrival shipments."""
    impact = 0
    if priority.lower() == "high":
        impact += 6
    if cargo_type.lower() in {"pharma", "cold chain", "electronics"}:
        impact += 5
    if arrival_days <= 1:
        impact += 8
    elif arrival_days <= 3:
        impact += 5
    return impact


def _recommendations(score: int, factors: list[dict], port_signal: dict, shipment: dict) -> list[str]:
    """Convert risk factors into concrete mitigation actions."""
    factor_names = {factor["key"] for factor in factors if factor["contribution"] >= 8}
    alternates = port_signal.get("alternate_ports", [])
    first_alternate = alternates[0] if alternates else "an alternate port"

    recommendations = []
    if "congestion" in factor_names:
        recommendations.append("Request carrier confirmation on berth window and pre-clear gate-in documents.")
    if "weather" in factor_names:
        recommendations.append("Add a 12-24 hour arrival buffer and monitor marine weather every 6 hours.")
    if "news" in factor_names or "route" in factor_names:
        recommendations.append(f"Keep a reroute option open via {first_alternate} until the risk drops below 50%.")
    if shipment["priority"].lower() == "high":
        recommendations.append("Notify receiver, customs broker, and warehouse team now with a high-priority ETA watch.")
    if score >= 70:
        recommendations.append("Trigger an exception workflow: daily ops review, alternate slot check, and customer alert.")
    if not recommendations:
        recommendations.append("Continue normal tracking, but refresh signals once per day until arrival.")

    recommendations.extend(port_signal.get("mitigations", [])[:2])
    return list(dict.fromkeys(recommendations))[:6]


def _timeline(score: int, shipment: dict) -> list[dict]:
    """Create a simple operations timeline for proactive follow-up."""
    cadence = "every 6 hours" if score >= 70 else "daily"
    return [
        {"stage": "T-72h", "task": "Validate berth slot, documents, and consignee readiness."},
        {"stage": "T-48h", "task": f"Refresh weather, news, and port congestion signals {cadence}."},
        {"stage": "T-24h", "task": "Lock trucking plan and prepare exception message if ETA slips."},
        {"stage": "Arrival", "task": f"Prioritize {shipment['cargo_type']} handoff and capture actual delay outcome."},
    ]


def _merge_request(payload: dict, signals: dict) -> dict:
    """Merge structured form fields with values parsed from natural language."""
    parsed = parse_inquiry(payload.get("query", ""), signals)
    merged = {**DEFAULT_REQUEST, **parsed}
    for key in DEFAULT_REQUEST:
        value = payload.get(key)
        if value not in (None, ""):
            merged[key] = value
    merged["arrival_days"] = int(merged.get("arrival_days") or DEFAULT_REQUEST["arrival_days"])
    if not merged.get("route"):
        merged["route"] = f"{merged['origin']}-{merged['destination_port']}"
    return merged


def predict_risk(payload: dict, shipments: list[dict], signals: dict) -> dict:
    """Return the full delay-risk assessment for one shipment.

    Output includes:
    - score and probability for fast decision making
    - factor-level evidence for explainability
    - validation warnings for weak or unknown inputs
    - mitigation and alternate-port recommendations for actionability
    """
    shipment = _merge_request(payload, signals)
    port_signal = _port_signal(shipment["destination_port"], signals)
    grouped = _records_for(shipment, shipments)
    origin_known = _origin_known(shipment["origin"], shipments)
    route_records = grouped["route"] if origin_known else []
    match_pool = route_records or grouped["port"] or shipments
    history_basis = "similar-route" if route_records else "destination-port" if grouped["port"] else "overall dataset"

    port_delay_rate = _delay_rate(grouped["port"])
    route_delay_rate = _delay_rate(route_records or grouped["port"])
    carrier_delay_rate = _delay_rate(grouped["carrier"])
    historical_delay_hours = _average_delay(match_pool)

    weather = port_signal.get("weather", {})
    port_ops = port_signal.get("port", {})
    news_items = port_signal.get("news", [])
    news_risk = max((float(item.get("severity", 0)) for item in news_items), default=0)
    route_alert = (
        _route_alert_for(shipment["route"], port_signal)
        if origin_known
        else {"route": shipment["route"], "risk": 25, "message": "Origin is not a valid port in the demo dataset"}
    )

    factors = [
        {
            "key": "history",
            "name": "Historical delay pattern",
            "contribution": round(route_delay_rate * 24 + carrier_delay_rate * 8, 1),
            "evidence": f"{round(route_delay_rate * 100)}% {history_basis} delay rate; avg delay {round(historical_delay_hours)}h.",
        },
        {
            "key": "congestion",
            "name": "Port congestion",
            "contribution": round(float(port_ops.get("congestion_index", 0)) * 0.23, 1),
            "evidence": f"{port_ops.get('congestion_index', 0)}/100 congestion; berth wait {port_ops.get('berth_wait_hours', 0)}h.",
        },
        {
            "key": "weather",
            "name": "Weather exposure",
            "contribution": round(float(weather.get("severity", 0)) * 0.20, 1),
            "evidence": f"{weather.get('condition', 'No weather alert')} with severity {weather.get('severity', 0)}/100.",
        },
        {
            "key": "news",
            "name": "News and operations alerts",
            "contribution": round(news_risk * 0.15, 1),
            "evidence": news_items[0].get("headline", "No major alert") if news_items else "No major alert",
        },
        {
            "key": "route",
            "name": "Route disruption signal",
            "contribution": round(float(route_alert.get("risk", 0)) * 0.13, 1),
            "evidence": route_alert.get("message", "No route-specific alert"),
        },
        {
            "key": "time",
            "name": "Time-to-arrival pressure",
            "contribution": _priority_impact(shipment["priority"], shipment["cargo_type"], shipment["arrival_days"]),
            "evidence": f"{shipment['arrival_days']} days to arrival; priority {shipment['priority']}; cargo {shipment['cargo_type']}.",
        },
    ]

    raw_score = 8 + sum(factor["contribution"] for factor in factors)
    score = int(round(clamp(raw_score, 3, 96)))
    level = risk_level(score)
    top_factors = sorted(factors, key=lambda factor: factor["contribution"], reverse=True)
    matched_records = len(match_pool)
    source_count = 4
    confidence_penalty = 18 if not origin_known else 0
    confidence = int(clamp(48 + min(matched_records, 14) * 3 + source_count * 4 - confidence_penalty, 35, 94))
    if not grouped["route"]:
        confidence = min(confidence, 68)
    if not origin_known:
        confidence = min(confidence, 55)
    warnings = []
    if not origin_known:
        warnings.append(
            f"Origin '{shipment['origin']}' is not available as a valid origin port in the demo dataset; "
            "the score uses destination and external signals with reduced confidence."
        )

    explanation = (
        f"{shipment['destination_port']} is currently {level.lower()} risk because "
        f"{top_factors[0]['name'].lower()}, {top_factors[1]['name'].lower()}, and "
        f"{top_factors[2]['name'].lower()} are all adding measurable delay pressure."
    )

    return {
        "shipment": shipment,
        "score": score,
        "level": level,
        "probability": round(1 / (1 + math.exp(-(score - 50) / 12)), 2),
        "confidence": confidence,
        "validation": {
            "origin_known": origin_known,
            "warnings": warnings,
        },
        "explanation": explanation,
        "factors": top_factors,
        "recommendations": _recommendations(score, top_factors, port_signal, shipment),
        "timeline": _timeline(score, shipment),
        "alternatives": [
            {
                "port": port,
                "reason": "Use as mitigation if congestion or weather signals remain elevated.",
                "tradeoff": "Adds operational coordination but protects customer ETA visibility.",
            }
            for port in port_signal.get("alternate_ports", [])
        ],
        "signals": {
            "last_updated": signals.get("last_updated", "Demo feed"),
            "weather": weather,
            "port": port_ops,
            "news": news_items,
            "route_alert": route_alert,
            "historical_matches": matched_records,
            "port_delay_rate": round(port_delay_rate, 2),
        },
        "data_sources": [
            "Historical shipment CSV",
            "Port congestion signal feed",
            "Weather risk feed",
            "News and operations alert feed",
        ],
    }
