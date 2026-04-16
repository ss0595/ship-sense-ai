"""Risk intelligence engine for ShipSense AI.

The model is intentionally transparent for a hackathon/R&D demo. Instead of
returning a black-box score, it computes named risk factors from historical
movements and external signals, then returns the evidence behind each factor.
That makes the output easier for judges and operations teams to trust.
"""

from __future__ import annotations

import math
import re
from statistics import mean

from backend.reference import (
    HUB_CATALOG,
    canonical_hub_name,
    hubs_for_mode,
    is_valid_origin_hub,
    normalize_mode,
    vehicle_types_for_mode,
)


DEFAULT_REQUEST = {
    "transport_mode": "waterways",
    "vehicle_type": "Cargo Vessel",
    "origin": "Mumbai Cruise Terminal",
    "destination_hub": "Jebel Ali Port",
    "arrival_days": 3,
    "carrier": "GulfLink",
    "cargo_type": "Electronics",
    "priority": "High",
    "route": "Mumbai Cruise Terminal-Jebel Ali Port",
}

MODE_KEYWORDS = {
    "airways": ("air", "airway", "airways", "flight", "air cargo", "airport", "aircraft"),
    "roadways": ("road", "roadway", "roadways", "truck", "van", "bus", "highway"),
    "railways": ("rail", "railway", "railways", "train", "terminal", "wagon"),
    "waterways": ("water", "waterway", "waterways", "ship", "vessel", "cruise", "port"),
}

VEHICLE_KEYWORDS = {
    "bus": "Bus",
    "cargo aircraft": "Cargo Aircraft",
    "charter": "Charter Flight",
    "cruise": "Cruise",
    "express rail": "Express Rail",
    "freight train": "Freight Train",
    "ship": "Cargo Vessel",
    "train": "Freight Train",
    "truck": "Truck",
    "van": "Van",
    "vessel": "Cargo Vessel",
}

CARGO_TERMS = {
    "apparel": "Apparel",
    "automotive": "Automotive",
    "baggage": "Guest Baggage",
    "cold": "Cold Chain",
    "electronics": "Electronics",
    "hospitality": "Hospitality Supplies",
    "machinery": "Machinery",
    "medicine": "Pharma",
    "parcel": "Retail Parcels",
    "pharma": "Pharma",
    "reefer": "Cold Chain",
    "retail": "Retail Parcels",
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
    """Extract movement fields from a short natural-language request."""
    lower = (text or "").lower()
    parsed: dict = {}

    for mode, keywords in MODE_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            parsed["transport_mode"] = mode
            break

    for keyword, vehicle_type in VEHICLE_KEYWORDS.items():
        if keyword in lower:
            parsed["vehicle_type"] = vehicle_type
            break

    day_match = re.search(r"(?:in|within|eta|arriving in)\s+(\d{1,2})\s*(?:day|days|d)\b", lower)
    if day_match:
        parsed["arrival_days"] = int(day_match.group(1))

    route_match = re.search(r"from\s+([a-z\s]+?)\s+(?:to|towards|->)\s+([a-z\s]+?)(?:\s+in|\s+-|$)", lower)
    if route_match:
        mode = parsed.get("transport_mode")
        origin_text = route_match.group(1).strip()
        destination_text = route_match.group(2).strip()
        origin = canonical_hub_name(origin_text, mode) or origin_text.title()
        destination = canonical_hub_name(destination_text, mode) or destination_text.title()
        parsed["origin"] = origin
        parsed["destination_hub"] = destination
        parsed["route"] = f"{origin}-{destination}"

    if "destination_hub" not in parsed:
        for hub in sorted({*signals.get("hubs", {}).keys(), *HUB_CATALOG.keys()}):
            if hub.lower() in lower:
                parsed["destination_hub"] = hub
                break

    for term, cargo in CARGO_TERMS.items():
        if term in lower:
            parsed["cargo_type"] = cargo
            break

    if any(word in lower for word in ("urgent", "priority", "critical", "expedite")):
        parsed["priority"] = "High"

    if "vehicle_type" not in parsed and parsed.get("transport_mode"):
        defaults = vehicle_types_for_mode(parsed["transport_mode"])
        if defaults:
            parsed["vehicle_type"] = defaults[0]

    return parsed


def _same(left, right) -> bool:
    return str(left).strip().lower() == str(right).strip().lower()


def _mode_records(shipments: list[dict], mode: str) -> list[dict]:
    return [row for row in shipments if normalize_mode(str(row.get("transport_mode", ""))) == mode]


def _origin_known(origin: str, mode: str, shipments: list[dict]) -> bool:
    """Treat catalogued hubs as valid origins even when history is sparse."""
    return is_valid_origin_hub(origin, mode)


def _records_for(movement: dict, shipments: list[dict]) -> dict[str, list[dict]]:
    """Group historical records that can explain the current movement."""
    mode = movement["transport_mode"]
    destination = movement["destination_hub"]
    carrier = movement["carrier"]
    route = movement["route"]
    cargo = movement["cargo_type"]
    vehicle_type = movement["vehicle_type"]
    scoped = _mode_records(shipments, mode)
    return {
        "mode": scoped,
        "hub": [row for row in scoped if _same(row.get("destination_hub"), destination)],
        "carrier": [row for row in scoped if _same(row.get("carrier"), carrier)],
        "route": [row for row in scoped if _same(row.get("route"), route)],
        "cargo": [row for row in scoped if _same(row.get("cargo_type"), cargo)],
        "vehicle": [row for row in scoped if _same(row.get("vehicle_type"), vehicle_type)],
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


def _hub_signal(destination_hub: str, signals: dict, mode: str) -> dict:
    """Return the weather/news/capacity signal pack for a destination hub."""
    hubs = signals.get("hubs", {})
    canonical = canonical_hub_name(destination_hub, mode) or destination_hub
    if canonical in hubs:
        return hubs[canonical]
    for known_hub, signal in hubs.items():
        if known_hub.lower() == canonical.lower():
            return signal
    hub_meta = HUB_CATALOG.get(canonical, {})
    country = hub_meta.get("country", "Unknown")
    region = hub_meta.get("region", "Unknown")
    return {
        "mode": mode,
        "country": country,
        "region": region,
        "weather": {"condition": "No specific weather alert", "severity": 30, "wind_kph": 18, "rain_mm": 0},
        "operations": {
            "capacity_index": 35,
            "wait_hours": 6,
            "backlog": "Unknown",
            "metric_label": "hub pressure",
            "wait_label": "handling",
        },
        "news": [{"headline": "No hub-specific alert in demo feed", "severity": 25, "source": "Demo feed"}],
        "route_alerts": [],
        "alternate_hubs": ["Nearest feasible alternate hub"],
        "mitigations": ["Keep six-hourly check-ins with operations control."],
    }


def _route_alert_for(route: str, hub_signal: dict) -> dict:
    """Find a route-specific alert if the external feed contains one."""
    alerts = hub_signal.get("route_alerts", [])
    for alert in alerts:
        if str(alert.get("route", "")).lower() == route.lower():
            return alert
    return {"route": route, "risk": 25, "message": "No route-specific disruption found in the demo feed"}


def _distance_km(left: str, right: str) -> float:
    """Estimate distance between two hubs so alternates can stay geographically plausible."""
    left_meta = HUB_CATALOG.get(left, {})
    right_meta = HUB_CATALOG.get(right, {})
    if not left_meta or not right_meta:
        return 9999.0
    lat_1 = math.radians(float(left_meta.get("lat", 0)))
    lon_1 = math.radians(float(left_meta.get("lon", 0)))
    lat_2 = math.radians(float(right_meta.get("lat", 0)))
    lon_2 = math.radians(float(right_meta.get("lon", 0)))
    delta_lat = lat_2 - lat_1
    delta_lon = lon_2 - lon_1
    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat_1) * math.cos(lat_2) * math.sin(delta_lon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _hub_pressure_score(hub: str, signals: dict, mode: str) -> float:
    """Build one comparable pressure score from ops, weather, news, and corridor risk."""
    signal = _hub_signal(hub, signals, mode)
    operations = signal.get("operations", {})
    weather = signal.get("weather", {})
    news_risk = max((float(item.get("severity", 0)) for item in signal.get("news", [])), default=0)
    route_risk = max((float(item.get("risk", 0)) for item in signal.get("route_alerts", [])), default=0)
    return (
        float(operations.get("capacity_index", 0)) * 0.45
        + float(weather.get("severity", 0)) * 0.25
        + news_risk * 0.20
        + route_risk * 0.10
    )


def _alternate_candidates(destination_hub: str, signals: dict, mode: str) -> list[str]:
    """Choose alternate hubs that are mode-compatible and operationally distinct."""
    canonical_destination = canonical_hub_name(destination_hub, mode) or destination_hub
    destination_meta = HUB_CATALOG.get(canonical_destination, {})
    seed_alternates = [
        canonical_hub_name(hub, mode) or str(hub)
        for hub in _hub_signal(canonical_destination, signals, mode).get("alternate_hubs", [])
        if (canonical_hub_name(hub, mode) or str(hub)) != canonical_destination
    ]
    all_candidates = list(dict.fromkeys(seed_alternates + hubs_for_mode(mode)))
    scored: list[tuple[float, str]] = []
    destination_pressure = _hub_pressure_score(canonical_destination, signals, mode)

    for candidate in all_candidates:
        if candidate == canonical_destination or candidate not in HUB_CATALOG:
            continue
        candidate_meta = HUB_CATALOG[candidate]
        same_region = candidate_meta.get("region") == destination_meta.get("region")
        same_country = candidate_meta.get("country") == destination_meta.get("country")
        pressure_gap = destination_pressure - _hub_pressure_score(candidate, signals, mode)
        distance = _distance_km(canonical_destination, candidate)
        score = pressure_gap - distance * 0.01 + (18 if same_region else 0) + (8 if same_country else 0)
        scored.append((score, candidate))

    ranked = [candidate for _, candidate in sorted(scored, key=lambda item: item[0], reverse=True)]
    return ranked[:3]


def _alternate_plan(destination_hub: str, signals: dict, movement: dict, route_alert: dict) -> list[dict]:
    """Explain reroute options with destination-aware reasons and tradeoffs."""
    mode = movement["transport_mode"]
    canonical_destination = canonical_hub_name(destination_hub, mode) or destination_hub
    destination_meta = HUB_CATALOG.get(canonical_destination, {})
    destination_pressure = _hub_pressure_score(canonical_destination, signals, mode)
    plans = []

    for hub in _alternate_candidates(canonical_destination, signals, mode):
        candidate_meta = HUB_CATALOG.get(hub, {})
        candidate_signal = _hub_signal(hub, signals, mode)
        candidate_pressure = _hub_pressure_score(hub, signals, mode)
        capacity = candidate_signal.get("operations", {}).get("capacity_index", 0)
        wait_hours = candidate_signal.get("operations", {}).get("wait_hours", 0)
        distance = round(_distance_km(canonical_destination, hub))
        same_region = candidate_meta.get("region") == destination_meta.get("region")
        pressure_delta = round(max(destination_pressure - candidate_pressure, 1))
        route_issue = str(route_alert.get("message", "")).strip()
        reason = (
            f"{hub} is a lower-pressure {mode[:-1]} option with about {pressure_delta} points less operational stress "
            f"and an expected handling wait of {wait_hours}h."
        )
        if route_issue and float(route_alert.get("risk", 0)) >= 45:
            reason += f" It also keeps you clear of the current corridor issue: {route_issue}"
        tradeoff = (
            f"{'Same-region' if same_region else 'Cross-region'} handoff adds roughly {distance} km of recovery planning, "
            f"but current capacity is {capacity}/100 so the ETA buffer is stronger."
        )
        plans.append({"hub": hub, "port": hub, "reason": reason, "tradeoff": tradeoff})

    return plans


def _priority_impact(priority: str, cargo_type: str, arrival_days: int) -> float:
    """Add risk pressure for urgent, sensitive, or near-arrival movements."""
    impact = 0
    if priority.lower() == "high":
        impact += 6
    if cargo_type.lower() in {"pharma", "cold chain", "electronics", "guest baggage"}:
        impact += 5
    if arrival_days <= 1:
        impact += 8
    elif arrival_days <= 3:
        impact += 5
    return impact


def _mode_copy(mode: str, vehicle_type: str) -> dict[str, str]:
    if mode == "airways":
        return {
            "location": "airport hub",
            "metric": "airside congestion",
            "wait": "ground handling",
            "slot_action": "Confirm ramp slot, ULD readiness, and customs release window.",
            "weather_action": "Add a 6-12 hour flight buffer and track runway weather every 3 hours.",
            "ops_action": "Notify consignee, broker, and ground handling team of the elevated ETA watch.",
            "timeline_a": "Validate uplift capacity, airway bill, and receiving team readiness.",
            "timeline_b": "Refresh runway weather, cargo apron pressure, and latest airline notices",
            "timeline_c": "Lock truck connection and cross-dock window for the arrival bank.",
        }
    if mode == "roadways":
        return {
            "location": "road hub",
            "metric": "traffic pressure",
            "wait": "checkpoint",
            "slot_action": "Confirm loading slot, driver readiness, and checkpoint documentation.",
            "weather_action": "Add a 4-8 hour road buffer and review route weather every 4 hours.",
            "ops_action": "Notify receiver and field ops team to hold dock flexibility for the vehicle.",
            "timeline_a": "Validate dispatch slot, permits, and driver briefing.",
            "timeline_b": "Refresh traffic, weather, and checkpoint signals",
            "timeline_c": "Lock unloading bay and alternate highway plan before final departure.",
        }
    if mode == "railways":
        return {
            "location": "rail terminal",
            "metric": "terminal congestion",
            "wait": "path allocation",
            "slot_action": "Confirm rake placement, terminal handoff, and path allocation.",
            "weather_action": "Add a 6-10 hour rail buffer and monitor corridor weather twice daily.",
            "ops_action": "Notify destination terminal and drayage partner to hold handoff capacity.",
            "timeline_a": "Validate rake plan, terminal documentation, and last-mile readiness.",
            "timeline_b": "Refresh corridor weather, terminal pressure, and network bulletins",
            "timeline_c": "Lock drayage connection and contingency siding plan.",
        }
    return {
        "location": "marine hub",
        "metric": "berth congestion",
        "wait": "berth assignment",
        "slot_action": (
            "Confirm berth window and shore support plan."
            if vehicle_type == "Cruise"
            else "Confirm berth window, discharge plan, and customs readiness."
        ),
        "weather_action": "Add a 12-24 hour marine buffer and monitor coastal weather every 6 hours.",
        "ops_action": "Notify terminal, consignee, and operations control of the elevated ETA watch.",
        "timeline_a": (
            "Validate berth slot, guest service readiness, and terminal access."
            if vehicle_type == "Cruise"
            else "Validate berth slot, documents, and consignee readiness."
        ),
        "timeline_b": "Refresh marine weather, berth pressure, and latest terminal advisories",
        "timeline_c": (
            "Lock landside support and guest transfer contingency for arrival."
            if vehicle_type == "Cruise"
            else "Lock trucking plan and prepare exception messaging if ETA slips."
        ),
    }


def _recommendations(score: int, factors: list[dict], hub_signal: dict, movement: dict, alternatives: list[dict]) -> list[str]:
    """Convert risk factors into concrete mitigation actions."""
    factor_names = {factor["key"] for factor in factors if factor["contribution"] >= 8}
    copy = _mode_copy(movement["transport_mode"], movement["vehicle_type"])
    first_alternate = alternatives[0]["hub"] if alternatives else "an alternate hub"

    recommendations = []
    if "congestion" in factor_names:
        recommendations.append(copy["slot_action"])
    if "weather" in factor_names:
        recommendations.append(copy["weather_action"])
    if "news" in factor_names or "route" in factor_names:
        recommendations.append(f"Keep a reroute option open via {first_alternate} until the risk drops below 50%.")
    if movement["priority"].lower() == "high":
        recommendations.append(copy["ops_action"])
    if score >= 70:
        recommendations.append("Trigger an exception workflow: ops review, alternate capacity check, and customer alert.")
    if not recommendations:
        recommendations.append("Continue normal tracking, but refresh signals once per day until arrival.")

    recommendations.extend(hub_signal.get("mitigations", [])[:2])
    return list(dict.fromkeys(recommendations))[:6]


def _timeline(score: int, movement: dict) -> list[dict]:
    """Create a simple operations timeline for proactive follow-up."""
    cadence = "every 6 hours" if score >= 70 else "daily"
    copy = _mode_copy(movement["transport_mode"], movement["vehicle_type"])
    return [
        {"stage": "T-72h", "task": copy["timeline_a"]},
        {"stage": "T-48h", "task": f"{copy['timeline_b']} {cadence}."},
        {"stage": "T-24h", "task": copy["timeline_c"]},
        {"stage": "Arrival", "task": f"Prioritize {movement['cargo_type']} handoff and capture actual delay outcome."},
    ]


def _merge_request(payload: dict, signals: dict) -> dict:
    """Merge structured form fields with values parsed from natural language."""
    parsed = parse_inquiry(payload.get("query", ""), signals)
    merged = {**DEFAULT_REQUEST, **parsed}

    destination = payload.get("destination_hub") or payload.get("destination_port")
    if destination not in (None, ""):
        merged["destination_hub"] = str(destination)

    for key in ("transport_mode", "vehicle_type", "origin", "arrival_days", "carrier", "cargo_type", "priority"):
        value = payload.get(key)
        if value not in (None, ""):
            merged[key] = value

    merged["transport_mode"] = normalize_mode(str(merged.get("transport_mode", ""))) or DEFAULT_REQUEST["transport_mode"]
    if not merged.get("vehicle_type"):
        vehicle_defaults = vehicle_types_for_mode(merged["transport_mode"])
        merged["vehicle_type"] = vehicle_defaults[0] if vehicle_defaults else DEFAULT_REQUEST["vehicle_type"]

    merged["origin"] = canonical_hub_name(str(merged.get("origin", "")), merged["transport_mode"]) or str(merged.get("origin", ""))
    merged["destination_hub"] = (
        canonical_hub_name(str(merged.get("destination_hub", "")), merged["transport_mode"])
        or str(merged.get("destination_hub", ""))
    )
    merged["destination_port"] = merged["destination_hub"]
    merged["arrival_days"] = int(merged.get("arrival_days") or DEFAULT_REQUEST["arrival_days"])
    merged["route"] = f"{merged['origin']}-{merged['destination_hub']}"
    return merged


def predict_risk(payload: dict, shipments: list[dict], signals: dict) -> dict:
    """Return the full delay-risk assessment for one movement."""
    movement = _merge_request(payload, signals)
    mode = movement["transport_mode"]
    hub_signal = _hub_signal(movement["destination_hub"], signals, mode)
    grouped = _records_for(movement, shipments)
    origin_known = _origin_known(movement["origin"], mode, shipments)
    route_records = grouped["route"] if origin_known else []
    match_pool = route_records or grouped["hub"] or grouped["mode"] or shipments
    history_basis = "similar-route" if route_records else "destination-hub" if grouped["hub"] else "same-mode dataset"

    hub_delay_rate = _delay_rate(grouped["hub"])
    route_delay_rate = _delay_rate(route_records or grouped["hub"])
    carrier_delay_rate = _delay_rate(grouped["carrier"])
    historical_delay_hours = _average_delay(match_pool)

    weather = hub_signal.get("weather", {})
    hub_ops = hub_signal.get("operations", {})
    news_items = hub_signal.get("news", [])
    news_risk = max((float(item.get("severity", 0)) for item in news_items), default=0)
    route_alert = (
        _route_alert_for(movement["route"], hub_signal)
        if origin_known
        else {
            "route": movement["route"],
            "risk": 25,
            "message": f"Origin is not available as a valid {mode[:-1]} origin hub in the demo dataset",
        }
    )

    metric_label = hub_ops.get("metric_label", "hub pressure")
    wait_label = hub_ops.get("wait_label", "handling")
    factors = [
        {
            "key": "history",
            "name": "Historical delay pattern",
            "contribution": round(route_delay_rate * 24 + carrier_delay_rate * 8, 1),
            "evidence": f"{round(route_delay_rate * 100)}% {history_basis} delay rate; avg delay {round(historical_delay_hours)}h.",
        },
        {
            "key": "congestion",
            "name": "Hub capacity pressure",
            "contribution": round(float(hub_ops.get("capacity_index", 0)) * 0.23, 1),
            "evidence": f"{hub_ops.get('capacity_index', 0)}/100 {metric_label}; {wait_label} wait {hub_ops.get('wait_hours', 0)}h.",
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
            "name": "Corridor disruption signal",
            "contribution": round(float(route_alert.get("risk", 0)) * 0.13, 1),
            "evidence": route_alert.get("message", "No route-specific alert"),
        },
        {
            "key": "time",
            "name": "Time-to-arrival pressure",
            "contribution": _priority_impact(movement["priority"], movement["cargo_type"], movement["arrival_days"]),
            "evidence": (
                f"{movement['arrival_days']} days to arrival; priority {movement['priority']}; "
                f"cargo {movement['cargo_type']}; vehicle {movement['vehicle_type']}."
            ),
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
            f"Origin '{movement['origin']}' is not available as a valid {mode[:-1]} origin hub in the demo dataset; "
            "the score uses destination and external signals with reduced confidence."
        )

    explanation = (
        f"{movement['destination_hub']} is currently {level.lower()} risk because "
        f"{top_factors[0]['name'].lower()}, {top_factors[1]['name'].lower()}, and "
        f"{top_factors[2]['name'].lower()} are all adding measurable delay pressure."
    )
    alternatives = _alternate_plan(movement["destination_hub"], signals, movement, route_alert)

    return {
        "shipment": movement,
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
        "recommendations": _recommendations(score, top_factors, hub_signal, movement, alternatives),
        "timeline": _timeline(score, movement),
        "alternatives": alternatives,
        "signals": {
            "last_updated": signals.get("last_updated", "Demo feed"),
            "weather": weather,
            "hub": hub_ops,
            "news": news_items,
            "route_alert": route_alert,
            "historical_matches": matched_records,
            "hub_delay_rate": round(hub_delay_rate, 2),
        },
        "data_sources": [
            "Historical transport CSV",
            "Hub operations signal feed",
            "Weather risk feed",
            "News and operations alert feed",
        ],
    }
