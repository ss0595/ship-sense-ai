"""Data loading helpers for ShipSense AI."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from backend.reference import is_valid_origin_port


def _coerce(value: str):
    """Convert CSV strings into booleans or numbers where possible."""
    value = value.strip()
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_shipments(data_dir: Path) -> list[dict]:
    """Load historical shipment outcomes from CSV."""
    path = data_dir / "historical_shipments.csv"
    with path.open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        return [{key: _coerce(value) for key, value in row.items()} for row in reader]


def load_signals(data_dir: Path) -> dict:
    """Load demo external signals such as weather, news, and congestion."""
    path = data_dir / "external_signals.json"
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def available_ports(signals: dict) -> list[str]:
    """Return destination ports present in the external signal feed."""
    return sorted(signals.get("ports", {}).keys())


def available_origins(shipments: list[dict]) -> list[str]:
    """Return valid origin ports; inland non-port cities are excluded."""
    return sorted(
        {
            str(row.get("origin", "")).strip()
            for row in shipments
            if row.get("origin") and is_valid_origin_port(str(row.get("origin", "")))
        }
    )


def recent_shipments(shipments: list[dict], limit: int = 8) -> list[dict]:
    """Return recent shipment rows for the dashboard watchlist."""
    rows = sorted(shipments, key=lambda row: str(row.get("shipment_id", "")), reverse=True)
    return rows[:limit]
