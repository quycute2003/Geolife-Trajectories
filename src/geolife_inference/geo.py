"""Spherical distances in meters; coordinate order is latitude, longitude."""
import numpy as np
from numpy.typing import ArrayLike

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: ArrayLike, lon1: ArrayLike, lat2: ArrayLike, lon2: ArrayLike) -> np.ndarray | np.float64:
    a1, o1, a2, o2 = (np.radians(value) for value in (lat1, lon1, lat2, lon2))
    a = np.sin((a2 - a1) / 2) ** 2 + np.cos(a1) * np.cos(a2) * np.sin((o2 - o1) / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def representative(coords: np.ndarray) -> tuple[float, float]:
    """Coordinate median with circular longitude unwrapping (handles date line)."""
    longitude = np.degrees(np.median(np.unwrap(np.radians(coords[:, 1]))))
    return float(np.median(coords[:, 0])), float((longitude + 180) % 360 - 180)
