"""Reference lists used for data validation."""

VALID_ORIGIN_PORTS = {
    "Chennai",
    "Cochin",
    "Colombo",
    "Mumbai",
    "Mundra",
    "Nhava Sheva",
    "Rotterdam",
    "Shanghai",
    "Singapore",
}

_VALID_ORIGIN_LOOKUP = {port.lower() for port in VALID_ORIGIN_PORTS}

PORT_COORDINATES = {
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
    "Cochin": {"lat": 9.9312, "lon": 76.2673},
    "Colombo": {"lat": 6.9271, "lon": 79.8612},
    "Jebel Ali": {"lat": 25.0118, "lon": 55.0613},
    "Khalifa Port": {"lat": 24.8019, "lon": 54.6450},
    "Mumbai": {"lat": 18.9480, "lon": 72.8446},
    "Mundra": {"lat": 22.8396, "lon": 69.7219},
    "Nhava Sheva": {"lat": 18.9490, "lon": 72.9512},
    "Rotterdam": {"lat": 51.9480, "lon": 4.1420},
    "Salalah": {"lat": 16.9560, "lon": 54.0080},
    "Shanghai": {"lat": 31.2304, "lon": 121.4737},
    "Singapore": {"lat": 1.2644, "lon": 103.8223},
}


def is_valid_origin_port(origin: str) -> bool:
    """Check whether a value is a real origin port in this demo scope."""
    return str(origin).strip().lower() in _VALID_ORIGIN_LOOKUP
