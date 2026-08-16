"""
Build AIS feature vector for Isolation Forest scoring.
Haversine values are features only — anomaly verdict comes from the model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.core.config_loader import get_config
from app.services.validation_service.feature_names import FEATURE_NAMES
from app.services.validation_service.geospatial import (
    centroid,
    haversine_km,
    haversine_m,
    heading_correlation,
)


def _variance(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return sum((x - mean) ** 2 for x in values) / len(values)


def quantity_feasibility_score(quantity_mt: float | None, duration_hours: float | None) -> float:
    """1.0 = feasible, 0.0 = impossible, 0.5 = unknown."""
    if quantity_mt is None or duration_hours is None or duration_hours <= 0:
        return 0.5
    cfg = get_config()["validation"]["quantity_feasibility"]
    min_rate = float(cfg["min_pump_rate_mt_per_hour"])
    max_rate = float(cfg["max_pump_rate_mt_per_hour"])
    implied = quantity_mt / duration_hours
    if min_rate <= implied <= max_rate:
        return 1.0
    if implied < min_rate:
        return max(0.0, implied / min_rate)
    return max(0.0, max_rate / implied)


def build_feature_vector(
    *,
    vessel_positions: list[dict[str, Any]],
    barge_positions: list[dict[str, Any]] | None,
    port_lat: float | None,
    port_lon: float | None,
    delivery_start: datetime | None,
    delivery_end: datetime | None,
    quantity_mt: float | None = None,
) -> dict[str, Any]:
    """
    Compute feature dict aligned with FEATURE_NAMES.
    Positions: {lat, lon, speed, heading, timestamp}
    """
    val_cfg = get_config()["validation"]
    max_dist_m = float(val_cfg["max_distance_m"])

    distances: list[float] = []
    overlap_samples = 0
    total_samples = 0

    if vessel_positions and barge_positions:
        n = min(len(vessel_positions), len(barge_positions))
        for i in range(n):
            v, b = vessel_positions[i], barge_positions[i]
            d = haversine_m(v["lat"], v["lon"], b["lat"], b["lon"])
            distances.append(d)
            total_samples += 1
            if d <= max_dist_m:
                overlap_samples += 1
    elif vessel_positions:
        total_samples = len(vessel_positions)

    speeds = [float(p.get("speed") or 0) for p in vessel_positions]

    duration_hours = None
    if delivery_start and delivery_end:
        duration_hours = max((delivery_end - delivery_start).total_seconds() / 3600.0, 0.0)

    claimed_hours = duration_hours or 0.0
    colocation_ratio = (
        (overlap_samples / total_samples) if total_samples and barge_positions else 0.0
    )
    if duration_hours and duration_hours > 0:
        colocation_ratio = min(colocation_ratio, 1.0)

    drift_rate = 0.0
    if len(vessel_positions) >= 2:
        first, last = vessel_positions[0], vessel_positions[-1]
        span_h = max(
            (last["timestamp"] - first["timestamp"]).total_seconds() / 3600.0,
            1e-6,
        )
        drift_km = haversine_km(first["lat"], first["lon"], last["lat"], last["lon"])
        drift_rate = drift_km / span_h

    port_distance_km = 0.0
    v_centroid = centroid(vessel_positions)
    if v_centroid and port_lat is not None and port_lon is not None:
        port_distance_km = haversine_km(v_centroid[0], v_centroid[1], port_lat, port_lon)

    features = {
        "mean_vessel_barge_distance_m": sum(distances) / len(distances) if distances else 0.0,
        "var_vessel_barge_distance_m": _variance(distances),
        "vessel_speed_mean": sum(speeds) / len(speeds) if speeds else 0.0,
        "vessel_speed_var": _variance(speeds),
        "heading_correlation": heading_correlation(vessel_positions, barge_positions or []),
        "colocation_ratio": colocation_ratio,
        "position_drift_rate": drift_rate,
        "port_distance_km": port_distance_km,
        "quantity_feasibility": quantity_feasibility_score(quantity_mt, duration_hours),
    }

    return {
        "features": features,
        "vector": [features[name] for name in FEATURE_NAMES],
        "overlap_percent": round(colocation_ratio * 100, 1),
        "avg_distance_m": round(features["mean_vessel_barge_distance_m"], 1),
        "co_location_duration_h": round((colocation_ratio * claimed_hours), 2) if claimed_hours else 0.0,
        "port_coordinate_match": port_distance_km <= float(val_cfg["port_coordinate_tolerance_km"]),
        "quantity_feasible": features["quantity_feasibility"] >= 0.99,
    }


def descriptive_flags(feature_result: dict[str, Any], *, barge_missing: bool) -> list[str]:
    """Operator-facing flags derived from features (ML still decides is_anomaly)."""
    val_cfg = get_config()["validation"]
    flags: list[str] = []
    f = feature_result["features"]

    if barge_missing:
        flags.append("barge_ais_missing")
    if f["vessel_speed_mean"] > float(val_cfg["max_speed_during_delivery"]):
        flags.append("vessel_speed_anomaly")
    if f["colocation_ratio"] * 100 < float(val_cfg["min_overlap_percent"]):
        flags.append("co_location_duration_mismatch")
    if not feature_result.get("port_coordinate_match", True):
        flags.append("port_coordinate_mismatch")
    if f["quantity_feasibility"] < 0.5:
        flags.append("quantity_infeasible")

    return flags
