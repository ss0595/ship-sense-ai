"""Data loading helpers for ShipSense AI."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from backend.reference import (
    TRANSPORT_LABELS,
    carriers_for_mode,
    hubs_for_mode,
    is_valid_origin_hub,
    normalize_mode,
    transport_modes,
    vehicle_types_for_mode,
)


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


def available_hubs(signals: dict, mode: str | None = None) -> list[str]:
    """Return destination hubs present in the external signal feed."""
    return hubs_for_mode(mode)


def available_ports(signals: dict) -> list[str]:
    """Backward-compatible alias for older UI code."""
    return available_hubs(signals)


def available_origins(shipments: list[dict], mode: str | None = None) -> list[str]:
    """Return valid origin hubs, optionally filtered by transport mode."""
    normalized_mode = normalize_mode(mode)
    rows = set(hubs_for_mode(normalized_mode))
    for row in shipments:
        origin = str(row.get("origin", "")).strip()
        row_mode = normalize_mode(str(row.get("transport_mode", "")))
        if not origin:
            continue
        if normalized_mode and row_mode != normalized_mode:
            continue
        if is_valid_origin_hub(origin, row_mode or normalized_mode):
            rows.add(origin)
    return sorted(rows)


def transport_reference(shipments: list[dict], signals: dict) -> dict:
    """Return mode-aware dropdown data for the dashboard."""
    modes = []
    for mode in transport_modes():
        modes.append(
            {
                "id": mode,
                "label": TRANSPORT_LABELS[mode],
                "vehicle_types": vehicle_types_for_mode(mode),
                "carriers": carriers_for_mode(mode),
                "destinations": available_hubs(signals, mode),
                "origins": available_origins(shipments, mode),
            }
        )
    return {"modes": modes}


def recent_shipments(shipments: list[dict], limit: int = 8) -> list[dict]:
    """Return a mode-balanced watchlist for the dashboard."""
    rows = sorted(shipments, key=lambda row: str(row.get("shipment_id", "")), reverse=True)
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[normalize_mode(str(row.get("transport_mode", "")))].append(row)

    watchlist: list[dict] = []
    while len(watchlist) < limit and any(buckets.values()):
        for mode in transport_modes():
            if buckets[mode]:
                watchlist.append(buckets[mode].pop(0))
                if len(watchlist) >= limit:
                    break
    return watchlist
