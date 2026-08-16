"""Haversine and track helpers — used as ML features only, not hard verdict rules."""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any

from app.core.config_loader import get_config


def earth_radius_km() -> float:
    return float(get_config().get("geospatial", {}).get("earth_radius_km", 6371.0))


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = earth_radius_km() * 1000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    return haversine_m(lat1, lon1, lat2, lon2) / 1000.0


def centroid(positions: list[dict[str, Any]]) -> tuple[float, float] | None:
    if not positions:
        return None
    lat = sum(p["lat"] for p in positions) / len(positions)
    lon = sum(p["lon"] for p in positions) / len(positions)
    return lat, lon


def heading_correlation(vessel: list[dict[str, Any]], barge: list[dict[str, Any]]) -> float:
    if len(vessel) < 2 or len(barge) < 2:
        return 0.0
    n = min(len(vessel), len(barge))
    v_h = [float(vessel[i].get("heading") or 0) for i in range(n)]
    b_h = [float(barge[i].get("heading") or 0) for i in range(n)]
    v_mean = sum(v_h) / n
    b_mean = sum(b_h) / n
    num = sum((v_h[i] - v_mean) * (b_h[i] - b_mean) for i in range(n))
    den_v = math.sqrt(sum((x - v_mean) ** 2 for x in v_h))
    den_b = math.sqrt(sum((x - b_mean) ** 2 for x in b_h))
    if den_v == 0 or den_b == 0:
        return 0.0
    return max(-1.0, min(1.0, num / (den_v * den_b)))
