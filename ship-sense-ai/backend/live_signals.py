"""Optional live weather and news signal enrichment.

The app runs without API keys by using the demo JSON feed. If keys are present,
this module enriches the selected destination hub with live OpenWeather and
NewsAPI signals. API keys never leave the backend.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timedelta, timezone
from logging import Logger
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.agent import clamp, parse_inquiry
from backend.config import key_configured
from backend.reference import HUB_COORDINATES, normalize_mode


OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
NEWSAPI_URL = "https://newsapi.org/v2/everything"
RISK_TERMS = ("delay", "strike", "congestion", "storm", "disruption", "closure", "backlog", "reroute")
MODE_NEWS_TERMS = {
    "airways": "airport OR cargo OR airline OR runway OR ground handling",
    "railways": "rail OR train OR terminal OR corridor OR track",
    "roadways": "road OR highway OR terminal OR fleet OR traffic",
    "waterways": "port OR cruise OR vessel OR shipping OR berth",
}


def live_source_status() -> dict:
    """Return safe provider status without exposing keys."""
    return {
        "openweather": {
            "configured": key_configured("OPENWEATHER_API_KEY"),
            "provider": "OpenWeather Current Weather API",
        },
        "newsapi": {
            "configured": key_configured("NEWSAPI_API_KEY"),
            "provider": "NewsAPI Everything endpoint",
        },
    }


def enrich_signals_for_payload(base_signals: dict, payload: dict, logger: Logger) -> tuple[dict, dict]:
    """Return a copy of signals enriched for the requested destination hub."""
    signals = copy.deepcopy(base_signals)
    parsed = parse_inquiry(str(payload.get("query", "")), signals)
    destination = str(
        payload.get("destination_hub")
        or payload.get("destination_port")
        or parsed.get("destination_hub")
        or "Jebel Ali Port"
    )
    mode = normalize_mode(str(payload.get("transport_mode") or parsed.get("transport_mode") or ""))
    hub_signal = signals.get("hubs", {}).get(destination)
    status = live_source_status()

    if not hub_signal:
        status["destination"] = {"hub": destination, "live_enriched": False, "reason": "unknown destination"}
        return signals, status

    mode = mode or str(hub_signal.get("mode", ""))
    status["destination"] = {"hub": destination, "mode": mode, "live_enriched": False}
    weather = _fetch_openweather(destination, logger)
    if weather:
        hub_signal["weather"] = weather
        status["openweather"]["used"] = True
        status["destination"]["live_enriched"] = True
    else:
        status["openweather"]["used"] = False

    news_item = _fetch_news(destination, mode, logger)
    if news_item:
        existing = hub_signal.get("news", [])
        hub_signal["news"] = [news_item, *existing[:1]]
        status["newsapi"]["used"] = True
        status["destination"]["live_enriched"] = True
    else:
        status["newsapi"]["used"] = False

    return signals, status


def _fetch_openweather(hub: str, logger: Logger) -> dict | None:
    key = os.getenv("OPENWEATHER_API_KEY", "").strip()
    coords = HUB_COORDINATES.get(hub)
    if not key or not coords:
        return None
    try:
        params = urlencode(
            {
                "lat": coords["lat"],
                "lon": coords["lon"],
                "appid": key,
                "units": "metric",
            }
        )
        payload = _http_json(f"{OPENWEATHER_URL}?{params}", headers={})
        description = payload.get("weather", [{}])[0].get("description", "Live weather unavailable")
        wind_kph = round(float(payload.get("wind", {}).get("speed", 0)) * 3.6, 1)
        rain_mm = float(payload.get("rain", {}).get("1h", 0) or 0)
        visibility = float(payload.get("visibility", 10000) or 10000)
        severity = _weather_severity(description, wind_kph, rain_mm, visibility)
        return {
            "condition": f"Live: {description}",
            "severity": severity,
            "wind_kph": wind_kph,
            "rain_mm": rain_mm,
            "source": "OpenWeather live API",
        }
    except Exception as exc:
        logger.warning("OpenWeather enrichment failed for %s: %s", hub, exc)
        return None


def _fetch_news(hub: str, mode: str, logger: Logger) -> dict | None:
    key = os.getenv("NEWSAPI_API_KEY", "").strip()
    if not key:
        return None
    try:
        oldest = (datetime.now(timezone.utc) - timedelta(days=7)).date().isoformat()
        mode_terms = MODE_NEWS_TERMS.get(mode, "logistics OR operations OR delay")
        query = f'"{hub}" AND ({mode_terms})'
        params = urlencode(
            {
                "q": query,
                "from": oldest,
                "language": "en",
                "sortBy": "publishedAt",
                "pageSize": 5,
                "apiKey": key,
            }
        )
        payload = _http_json(f"{NEWSAPI_URL}?{params}", headers={})
        articles = payload.get("articles", [])
        if not articles:
            return None
        article = articles[0]
        title = str(article.get("title") or "Live logistics news signal")
        description = str(article.get("description") or "")
        severity = _news_severity(f"{title} {description}")
        return {
            "headline": f"Live: {title}",
            "severity": severity,
            "source": article.get("source", {}).get("name") or "NewsAPI live feed",
            "published_at": article.get("publishedAt"),
        }
    except Exception as exc:
        logger.warning("NewsAPI enrichment failed for %s: %s", hub, exc)
        return None


def _http_json(url: str, headers: dict[str, str]) -> dict:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=4) as response:
        return json.loads(response.read().decode("utf-8"))


def _weather_severity(description: str, wind_kph: float, rain_mm: float, visibility: float) -> int:
    condition = description.lower()
    condition_risk = 0
    if any(term in condition for term in ("storm", "thunder", "squall")):
        condition_risk = 35
    elif any(term in condition for term in ("rain", "fog", "haze", "dust")):
        condition_risk = 18
    visibility_risk = 18 if visibility < 3000 else 8 if visibility < 7000 else 0
    return int(clamp(condition_risk + wind_kph * 1.2 + rain_mm * 5 + visibility_risk, 10, 95))


def _news_severity(text: str) -> int:
    lower = text.lower()
    hits = sum(1 for term in RISK_TERMS if term in lower)
    return int(clamp(35 + hits * 10, 25, 85))
