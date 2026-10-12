import math


def haversine_km(lat1, lon1, lat2, lon2):
    """
    Calculate the great-circle distance between two GPS points.
    Returns distance in kilometers.
    """
    coordinates = (lat1, lon1, lat2, lon2)

    if not all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in coordinates
    ):
        raise ValueError("GPS coordinates must be finite numbers")

    if not (
        -90 <= lat1 <= 90
        and -90 <= lat2 <= 90
        and -180 <= lon1 <= 180
        and -180 <= lon2 <= 180
    ):
        raise ValueError("GPS coordinates are outside valid ranges")

    lat1, lon1, lat2, lon2 = map(math.radians, coordinates)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    a = min(1.0, max(0.0, a))

    return 6371.0088 * 2 * math.asin(math.sqrt(a))
