"""Reference data used for multimodal hub validation and lookup."""

from __future__ import annotations

TRANSPORT_LABELS = {
    "airways": "Airways",
    "roadways": "Roadways",
    "railways": "Railways",
    "waterways": "Waterways",
}

MODE_VEHICLE_TYPES = {
    "airways": ["Cargo Aircraft", "Charter Flight"],
    "roadways": ["Truck", "Van", "Bus"],
    "railways": ["Freight Train", "Express Rail"],
    "waterways": ["Cargo Vessel", "Cruise"],
}

MODE_CARRIERS = {
    "airways": ["AirLift Express", "Emirates SkyCargo", "Falcon Wings", "SkyBridge Cargo"],
    "roadways": ["HighwayGo", "MetroBus", "RoadPulse", "SwiftVan"],
    "railways": ["CorridorExpress", "FreightRail", "InlandLink", "RailBridge"],
    "waterways": ["BlueWave", "GulfLink", "HarborOne", "OceanPeak"],
}

HUB_CATALOG = {
    "Ahmedabad Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "West India",
        "lat": 23.0225,
        "lon": 72.5714,
    },
    "Ahmedabad Road Freight Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "West India",
        "lat": 23.0300,
        "lon": 72.5800,
    },
    "Abu Dhabi Air Cargo": {
        "mode": "airways",
        "country": "UAE",
        "region": "Gulf",
        "lat": 24.4330,
        "lon": 54.6511,
    },
    "Abu Dhabi Cruise Terminal": {
        "mode": "waterways",
        "country": "UAE",
        "region": "Gulf",
        "lat": 24.5361,
        "lon": 54.3950,
    },
    "Amsterdam Air Cargo": {
        "mode": "airways",
        "country": "Netherlands",
        "region": "Europe",
        "lat": 52.3105,
        "lon": 4.7683,
    },
    "Barcelona Cruise Port": {
        "mode": "waterways",
        "country": "Spain",
        "region": "Europe",
        "lat": 41.3521,
        "lon": 2.1686,
    },
    "Bengaluru Distribution Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 12.9716,
        "lon": 77.5946,
    },
    "Bengaluru Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "South India",
        "lat": 13.1986,
        "lon": 77.7066,
    },
    "Bengaluru Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "South India",
        "lat": 13.0276,
        "lon": 77.5520,
    },
    "Bhopal Rail Freight Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "Central India",
        "lat": 23.2599,
        "lon": 77.4126,
    },
    "Busan Port": {
        "mode": "waterways",
        "country": "South Korea",
        "region": "East Asia",
        "lat": 35.1028,
        "lon": 129.0403,
    },
    "Cape Town Port": {
        "mode": "waterways",
        "country": "South Africa",
        "region": "Africa",
        "lat": -33.9180,
        "lon": 18.4350,
    },
    "Changi Air Cargo": {
        "mode": "airways",
        "country": "Singapore",
        "region": "Southeast Asia",
        "lat": 1.3644,
        "lon": 103.9915,
    },
    "Chennai Bus Terminal": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 13.0827,
        "lon": 80.2707,
    },
    "Chennai Inland Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "South India",
        "lat": 13.1067,
        "lon": 80.1742,
    },
    "Chennai Port": {
        "mode": "waterways",
        "country": "India",
        "region": "South India",
        "lat": 13.0881,
        "lon": 80.2892,
    },
    "Chennai Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "South India",
        "lat": 12.9941,
        "lon": 80.1709,
    },
    "Coimbatore Truck Terminal": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 11.0168,
        "lon": 76.9558,
    },
    "Colombo Port": {
        "mode": "waterways",
        "country": "Sri Lanka",
        "region": "South Asia",
        "lat": 6.9497,
        "lon": 79.8428,
    },
    "Dadri Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "North India",
        "lat": 28.5520,
        "lon": 77.5540,
    },
    "Dubai Harbour Cruise Terminal": {
        "mode": "waterways",
        "country": "UAE",
        "region": "Gulf",
        "lat": 25.0949,
        "lon": 55.1387,
    },
    "Dubai International Cargo": {
        "mode": "airways",
        "country": "UAE",
        "region": "Gulf",
        "lat": 25.2532,
        "lon": 55.3657,
    },
    "Delhi Freight Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "North India",
        "lat": 28.6139,
        "lon": 77.2090,
    },
    "Delhi Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "North India",
        "lat": 28.5562,
        "lon": 77.1000,
    },
    "Delhi Rail Freight Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "North India",
        "lat": 28.7041,
        "lon": 77.1025,
    },
    "Doha Air Cargo": {
        "mode": "airways",
        "country": "Qatar",
        "region": "Gulf",
        "lat": 25.2731,
        "lon": 51.6081,
    },
    "Doha Port": {
        "mode": "waterways",
        "country": "Qatar",
        "region": "Gulf",
        "lat": 25.2948,
        "lon": 51.5465,
    },
    "Frankfurt Air Cargo": {
        "mode": "airways",
        "country": "Germany",
        "region": "Europe",
        "lat": 50.0379,
        "lon": 8.5622,
    },
    "Hamburg Port": {
        "mode": "waterways",
        "country": "Germany",
        "region": "Europe",
        "lat": 53.5461,
        "lon": 9.9661,
    },
    "Hong Kong Air Cargo": {
        "mode": "airways",
        "country": "Hong Kong",
        "region": "East Asia",
        "lat": 22.3080,
        "lon": 113.9185,
    },
    "Hyderabad Van Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 17.3850,
        "lon": 78.4867,
    },
    "Hyderabad Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "South India",
        "lat": 17.2403,
        "lon": 78.4294,
    },
    "Hyderabad Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "South India",
        "lat": 17.4399,
        "lon": 78.4983,
    },
    "Indore Freight Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "Central India",
        "lat": 22.7196,
        "lon": 75.8577,
    },
    "Istanbul Air Cargo": {
        "mode": "airways",
        "country": "Turkey",
        "region": "Europe",
        "lat": 41.2753,
        "lon": 28.7519,
    },
    "Jaipur Bus Terminal": {
        "mode": "roadways",
        "country": "India",
        "region": "North India",
        "lat": 26.9124,
        "lon": 75.7873,
    },
    "Jaipur Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "North India",
        "lat": 26.9196,
        "lon": 75.7880,
    },
    "Jebel Ali Port": {
        "mode": "waterways",
        "country": "UAE",
        "region": "Gulf",
        "lat": 25.0118,
        "lon": 55.0613,
    },
    "Kanpur Inland Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "North India",
        "lat": 26.4499,
        "lon": 80.3319,
    },
    "Kandla Port": {
        "mode": "waterways",
        "country": "India",
        "region": "West India",
        "lat": 23.0333,
        "lon": 70.2167,
    },
    "Kochi Logistics Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 9.9312,
        "lon": 76.2673,
    },
    "Kochi Port": {
        "mode": "waterways",
        "country": "India",
        "region": "South India",
        "lat": 9.9667,
        "lon": 76.2717,
    },
    "Kolkata Inland Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "East India",
        "lat": 22.5726,
        "lon": 88.3639,
    },
    "Kolkata Distribution Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "East India",
        "lat": 22.5726,
        "lon": 88.4000,
    },
    "Kolkata Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "East India",
        "lat": 22.6547,
        "lon": 88.4467,
    },
    "Kuala Lumpur Air Cargo": {
        "mode": "airways",
        "country": "Malaysia",
        "region": "Southeast Asia",
        "lat": 2.7456,
        "lon": 101.7072,
    },
    "Lucknow Freight Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "North India",
        "lat": 26.8467,
        "lon": 80.9462,
    },
    "Ludhiana Rail Freight Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "North India",
        "lat": 30.9010,
        "lon": 75.8573,
    },
    "London Heathrow Cargo": {
        "mode": "airways",
        "country": "United Kingdom",
        "region": "Europe",
        "lat": 51.4700,
        "lon": -0.4543,
    },
    "Mumbai Air Cargo": {
        "mode": "airways",
        "country": "India",
        "region": "West India",
        "lat": 19.0896,
        "lon": 72.8656,
    },
    "Mumbai Cruise Terminal": {
        "mode": "waterways",
        "country": "India",
        "region": "West India",
        "lat": 18.9474,
        "lon": 72.8400,
    },
    "Mumbai Logistics Park": {
        "mode": "roadways",
        "country": "India",
        "region": "West India",
        "lat": 19.0760,
        "lon": 72.8777,
    },
    "Mumbai Rail Freight Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "West India",
        "lat": 19.0748,
        "lon": 72.8856,
    },
    "Nagpur Freight Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "Central India",
        "lat": 21.1458,
        "lon": 79.0882,
    },
    "Nagpur Road Logistics Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "Central India",
        "lat": 21.1458,
        "lon": 79.0990,
    },
    "Nhava Sheva Port": {
        "mode": "waterways",
        "country": "India",
        "region": "West India",
        "lat": 18.9498,
        "lon": 72.9523,
    },
    "Paris Air Cargo": {
        "mode": "airways",
        "country": "France",
        "region": "Europe",
        "lat": 49.0097,
        "lon": 2.5479,
    },
    "Port Klang": {
        "mode": "waterways",
        "country": "Malaysia",
        "region": "Southeast Asia",
        "lat": 3.0019,
        "lon": 101.3928,
    },
    "Pune Truck Terminal": {
        "mode": "roadways",
        "country": "India",
        "region": "West India",
        "lat": 18.5204,
        "lon": 73.8567,
    },
    "Pune Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "West India",
        "lat": 18.5286,
        "lon": 73.8740,
    },
    "Rotterdam Port": {
        "mode": "waterways",
        "country": "Netherlands",
        "region": "Europe",
        "lat": 51.9244,
        "lon": 4.4777,
    },
    "Singapore Cruise Centre": {
        "mode": "waterways",
        "country": "Singapore",
        "region": "Southeast Asia",
        "lat": 1.2644,
        "lon": 103.8223,
    },
    "Surat Logistics Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "West India",
        "lat": 21.1702,
        "lon": 72.8311,
    },
    "Surat Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "West India",
        "lat": 21.1959,
        "lon": 72.8302,
    },
    "Sydney Cruise Terminal": {
        "mode": "waterways",
        "country": "Australia",
        "region": "Oceania",
        "lat": -33.8587,
        "lon": 151.2100,
    },
    "Visakhapatnam Port": {
        "mode": "waterways",
        "country": "India",
        "region": "East India",
        "lat": 17.6868,
        "lon": 83.2185,
    },
    "Visakhapatnam Road Hub": {
        "mode": "roadways",
        "country": "India",
        "region": "East India",
        "lat": 17.6868,
        "lon": 83.2400,
    },
    "Visakhapatnam Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "East India",
        "lat": 17.7210,
        "lon": 83.3040,
    },
    "Vijayawada Bus Terminal": {
        "mode": "roadways",
        "country": "India",
        "region": "South India",
        "lat": 16.5062,
        "lon": 80.6480,
    },
    "Vijayawada Rail Terminal": {
        "mode": "railways",
        "country": "India",
        "region": "South India",
        "lat": 16.5167,
        "lon": 80.6167,
    },
}

GLOBAL_HUB_ALIASES = {
    "ahmedabad rail": "Ahmedabad Rail Terminal",
    "ahmedabad rail terminal": "Ahmedabad Rail Terminal",
    "ahmedabad road freight hub": "Ahmedabad Road Freight Hub",
    "abu dhabi air cargo": "Abu Dhabi Air Cargo",
    "abu dhabi cruise terminal": "Abu Dhabi Cruise Terminal",
    "amsterdam air cargo": "Amsterdam Air Cargo",
    "barcelona cruise port": "Barcelona Cruise Port",
    "bengaluru air cargo": "Bengaluru Air Cargo",
    "bengaluru distribution": "Bengaluru Distribution Hub",
    "bengaluru distribution hub": "Bengaluru Distribution Hub",
    "bengaluru rail terminal": "Bengaluru Rail Terminal",
    "bhopal rail freight terminal": "Bhopal Rail Freight Terminal",
    "busan port": "Busan Port",
    "cape town port": "Cape Town Port",
    "changi": "Changi Air Cargo",
    "changi air cargo": "Changi Air Cargo",
    "chennai air cargo": "Chennai Air Cargo",
    "chennai bus terminal": "Chennai Bus Terminal",
    "chennai inland rail": "Chennai Inland Rail Terminal",
    "chennai inland rail terminal": "Chennai Inland Rail Terminal",
    "chennai port": "Chennai Port",
    "coimbatore truck terminal": "Coimbatore Truck Terminal",
    "colombo port": "Colombo Port",
    "dadri": "Dadri Rail Terminal",
    "dadri rail": "Dadri Rail Terminal",
    "dadri rail terminal": "Dadri Rail Terminal",
    "delhi air cargo": "Delhi Air Cargo",
    "delhi rail freight terminal": "Delhi Rail Freight Terminal",
    "delhi freight hub": "Delhi Freight Hub",
    "doha air cargo": "Doha Air Cargo",
    "doha port": "Doha Port",
    "dubai harbour": "Dubai Harbour Cruise Terminal",
    "dubai harbour cruise terminal": "Dubai Harbour Cruise Terminal",
    "dubai international cargo": "Dubai International Cargo",
    "frankfurt air cargo": "Frankfurt Air Cargo",
    "hamburg port": "Hamburg Port",
    "hong kong air cargo": "Hong Kong Air Cargo",
    "hyderabad air cargo": "Hyderabad Air Cargo",
    "hyderabad rail terminal": "Hyderabad Rail Terminal",
    "hyderabad van hub": "Hyderabad Van Hub",
    "indore freight hub": "Indore Freight Hub",
    "istanbul air cargo": "Istanbul Air Cargo",
    "jaipur bus terminal": "Jaipur Bus Terminal",
    "jaipur rail terminal": "Jaipur Rail Terminal",
    "jebel ali": "Jebel Ali Port",
    "jebel ali port": "Jebel Ali Port",
    "kandla port": "Kandla Port",
    "kanpur inland rail terminal": "Kanpur Inland Rail Terminal",
    "kochi logistics hub": "Kochi Logistics Hub",
    "kochi port": "Kochi Port",
    "kolkata air cargo": "Kolkata Air Cargo",
    "kolkata distribution hub": "Kolkata Distribution Hub",
    "kolkata inland rail terminal": "Kolkata Inland Rail Terminal",
    "kuala lumpur air cargo": "Kuala Lumpur Air Cargo",
    "lucknow freight hub": "Lucknow Freight Hub",
    "ludhiana rail freight terminal": "Ludhiana Rail Freight Terminal",
    "london heathrow cargo": "London Heathrow Cargo",
    "mumbai air cargo": "Mumbai Air Cargo",
    "mumbai cruise terminal": "Mumbai Cruise Terminal",
    "mumbai logistics park": "Mumbai Logistics Park",
    "mumbai rail freight terminal": "Mumbai Rail Freight Terminal",
    "nagpur freight terminal": "Nagpur Freight Terminal",
    "nagpur road logistics hub": "Nagpur Road Logistics Hub",
    "nhava sheva port": "Nhava Sheva Port",
    "paris air cargo": "Paris Air Cargo",
    "port klang": "Port Klang",
    "pune truck terminal": "Pune Truck Terminal",
    "pune rail terminal": "Pune Rail Terminal",
    "rotterdam port": "Rotterdam Port",
    "singapore cruise centre": "Singapore Cruise Centre",
    "surat logistics hub": "Surat Logistics Hub",
    "surat rail terminal": "Surat Rail Terminal",
    "sydney cruise terminal": "Sydney Cruise Terminal",
    "visakhapatnam port": "Visakhapatnam Port",
    "visakhapatnam road hub": "Visakhapatnam Road Hub",
    "visakhapatnam rail terminal": "Visakhapatnam Rail Terminal",
    "vijayawada bus terminal": "Vijayawada Bus Terminal",
    "vijayawada rail terminal": "Vijayawada Rail Terminal",
}

MODE_CITY_DEFAULTS = {
    "airways": {
        "abu dhabi": "Abu Dhabi Air Cargo",
        "amsterdam": "Amsterdam Air Cargo",
        "bengaluru": "Bengaluru Air Cargo",
        "chennai": "Chennai Air Cargo",
        "delhi": "Delhi Air Cargo",
        "dubai": "Dubai International Cargo",
        "doha": "Doha Air Cargo",
        "frankfurt": "Frankfurt Air Cargo",
        "hong kong": "Hong Kong Air Cargo",
        "hyderabad": "Hyderabad Air Cargo",
        "istanbul": "Istanbul Air Cargo",
        "kolkata": "Kolkata Air Cargo",
        "kuala lumpur": "Kuala Lumpur Air Cargo",
        "london": "London Heathrow Cargo",
        "mumbai": "Mumbai Air Cargo",
        "paris": "Paris Air Cargo",
        "singapore": "Changi Air Cargo",
    },
    "railways": {
        "ahmedabad": "Ahmedabad Rail Terminal",
        "bengaluru": "Bengaluru Rail Terminal",
        "bhopal": "Bhopal Rail Freight Terminal",
        "chennai": "Chennai Inland Rail Terminal",
        "dadri": "Dadri Rail Terminal",
        "delhi": "Delhi Rail Freight Terminal",
        "hyderabad": "Hyderabad Rail Terminal",
        "jaipur": "Jaipur Rail Terminal",
        "kanpur": "Kanpur Inland Rail Terminal",
        "kolkata": "Kolkata Inland Rail Terminal",
        "ludhiana": "Ludhiana Rail Freight Terminal",
        "mumbai": "Mumbai Rail Freight Terminal",
        "nagpur": "Nagpur Freight Terminal",
        "pune": "Pune Rail Terminal",
        "surat": "Surat Rail Terminal",
        "visakhapatnam": "Visakhapatnam Rail Terminal",
        "vijayawada": "Vijayawada Rail Terminal",
    },
    "roadways": {
        "ahmedabad": "Ahmedabad Road Freight Hub",
        "bengaluru": "Bengaluru Distribution Hub",
        "chennai": "Chennai Bus Terminal",
        "coimbatore": "Coimbatore Truck Terminal",
        "delhi": "Delhi Freight Hub",
        "hyderabad": "Hyderabad Van Hub",
        "indore": "Indore Freight Hub",
        "jaipur": "Jaipur Bus Terminal",
        "kochi": "Kochi Logistics Hub",
        "kolkata": "Kolkata Distribution Hub",
        "lucknow": "Lucknow Freight Hub",
        "mumbai": "Mumbai Logistics Park",
        "nagpur": "Nagpur Road Logistics Hub",
        "pune": "Pune Truck Terminal",
        "surat": "Surat Logistics Hub",
        "visakhapatnam": "Visakhapatnam Road Hub",
        "vijayawada": "Vijayawada Bus Terminal",
    },
    "waterways": {
        "abu dhabi": "Abu Dhabi Cruise Terminal",
        "barcelona": "Barcelona Cruise Port",
        "busan": "Busan Port",
        "cape town": "Cape Town Port",
        "chennai": "Chennai Port",
        "colombo": "Colombo Port",
        "dubai": "Dubai Harbour Cruise Terminal",
        "doha": "Doha Port",
        "hamburg": "Hamburg Port",
        "jebel ali": "Jebel Ali Port",
        "kandla": "Kandla Port",
        "kochi": "Kochi Port",
        "mumbai": "Mumbai Cruise Terminal",
        "nhava sheva": "Nhava Sheva Port",
        "port klang": "Port Klang",
        "rotterdam": "Rotterdam Port",
        "singapore": "Singapore Cruise Centre",
        "sydney": "Sydney Cruise Terminal",
        "visakhapatnam": "Visakhapatnam Port",
    },
}

HUB_COORDINATES = {
    hub: {"lat": meta["lat"], "lon": meta["lon"]}
    for hub, meta in HUB_CATALOG.items()
}

PORT_COORDINATES = HUB_COORDINATES


def normalize_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value in TRANSPORT_LABELS:
        return value
    if value.endswith("way") and f"{value}s" in TRANSPORT_LABELS:
        return f"{value}s"
    return ""


def transport_modes() -> list[str]:
    return list(TRANSPORT_LABELS.keys())


def vehicle_types_for_mode(mode: str | None) -> list[str]:
    return MODE_VEHICLE_TYPES.get(normalize_mode(mode), [])


def carriers_for_mode(mode: str | None) -> list[str]:
    return MODE_CARRIERS.get(normalize_mode(mode), [])


def canonical_hub_name(name: str, mode: str | None = None) -> str | None:
    cleaned = str(name or "").strip().lower()
    if not cleaned:
        return None
    if cleaned in GLOBAL_HUB_ALIASES:
        return GLOBAL_HUB_ALIASES[cleaned]
    normalized_mode = normalize_mode(mode)
    if normalized_mode and cleaned in MODE_CITY_DEFAULTS.get(normalized_mode, {}):
        return MODE_CITY_DEFAULTS[normalized_mode][cleaned]
    for hub in HUB_CATALOG:
        if hub.lower() == cleaned:
            return hub
    return None


def hub_mode(hub: str) -> str:
    canonical = canonical_hub_name(hub) or str(hub)
    return str(HUB_CATALOG.get(canonical, {}).get("mode", ""))


def hubs_for_mode(mode: str | None = None) -> list[str]:
    normalized_mode = normalize_mode(mode)
    if not normalized_mode:
        return sorted(HUB_CATALOG.keys())
    return sorted(hub for hub, meta in HUB_CATALOG.items() if meta["mode"] == normalized_mode)


def is_valid_origin_hub(origin: str, mode: str | None = None) -> bool:
    canonical = canonical_hub_name(origin, mode)
    if not canonical:
        return False
    normalized_mode = normalize_mode(mode)
    if normalized_mode:
        return HUB_CATALOG[canonical]["mode"] == normalized_mode
    return canonical in HUB_CATALOG


def is_valid_origin_port(origin: str) -> bool:
    """Backward-compatible helper kept for older imports."""
    return is_valid_origin_hub(origin, "waterways")
