import math
import random


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points
    on Earth using the Haversine formula.

    Args:
        lat1, lon1: Latitude and longitude of point 1 (in degrees).
        lat2, lon2: Latitude and longitude of point 2 (in degrees).

    Returns:
        Distance in kilometers.
    """
    R = 6371  # Earth's radius in kilometers

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def offset_coordinates(
    lat: float,
    lon: float,
    offset_meters: float = 100,
    seed: object = None,
) -> tuple[float, float]:
    """
    Offset coordinates by approximately the given distance in a pseudo-random
    direction. Used for privacy — hides exact location until a volunteer is
    confirmed.

    When ``seed`` is provided the offset is deterministic for that seed. The
    map endpoint passes the request's primary key as the seed so the same
    request always maps to the same offset point. This prevents an attacker
    from repeatedly polling ``/requests/map/data/`` and averaging multiple
    random offsets to recover the exact coordinates.

    Args:
        lat, lon: Original coordinates.
        offset_meters: Approximate offset distance in meters.
        seed: Optional deterministic seed (e.g. the request pk). When ``None``,
            a fresh random offset is produced on each call.

    Returns:
        Tuple of (offset_lat, offset_lon).
    """
    rng = random.Random(seed) if seed is not None else random

    # Approximate degrees per meter
    lat_offset = offset_meters / 111_320
    lon_offset = offset_meters / (111_320 * math.cos(math.radians(lat)))

    new_lat = lat + rng.uniform(-lat_offset, lat_offset)
    new_lon = lon + rng.uniform(-lon_offset, lon_offset)

    return new_lat, new_lon
