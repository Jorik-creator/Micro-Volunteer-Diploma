import math


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


def offset_coordinates(lat: float, lon: float, offset_meters: float = 100) -> tuple[float, float]:
    """
    Offset coordinates by approximately the given distance in a random direction.
    Used for privacy — hides exact location until volunteer is confirmed.

    Args:
        lat, lon: Original coordinates.
        offset_meters: Approximate offset distance in meters.

    Returns:
        Tuple of (offset_lat, offset_lon).
    """
    import random

    # Approximate degrees per meter
    lat_offset = offset_meters / 111_320
    lon_offset = offset_meters / (111_320 * math.cos(math.radians(lat)))

    new_lat = lat + random.uniform(-lat_offset, lat_offset)
    new_lon = lon + random.uniform(-lon_offset, lon_offset)

    return new_lat, new_lon
