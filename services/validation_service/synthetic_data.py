"""
Synthetic AIS tracks and feature vectors for training without real telemetry.

Normal class = typical bunkering (anchored vessel, barge alongside, near port).
Anomaly class = injected fraud patterns (far from barge, moving fast, wrong port, etc.).

Sample BDN files do NOT train this model directly — they only help calibrate
quantity/duration via scripts/calibrate_from_bdns.py.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from core.config_loader import get_config
from services.validation_service.features import build_feature_vector


def _rng() -> random.Random:
    cfg = get_config()["model"]["isolation_forest"]
    return random.Random(int(cfg["random_state"]))


def _normal_noise(rng: random.Random, mean: float, std: float) -> float:
    return rng.gauss(mean, std)


def _generate_track(
    rng: random.Random,
    *,
    center_lat: float,
    center_lon: float,
    n_points: int,
    duration_hours: float,
    speed_mean: float,
    speed_std: float,
    offset_m: float,
    heading: float,
) -> list[dict[str, Any]]:
    """Generate AIS points around a center with small drift."""
    start = datetime.now(timezone.utc) - timedelta(hours=duration_hours)
    interval_h = duration_hours / max(n_points - 1, 1)
    lat_deg_per_m = 1.0 / 111_320.0
    lon_deg_per_m = 1.0 / (111_320.0 * max(np.cos(np.radians(center_lat)), 1e-6))

    positions: list[dict[str, Any]] = []
    for i in range(n_points):
        ts = start + timedelta(hours=i * interval_h)
        drift = offset_m + _normal_noise(rng, 0, offset_m * 0.1)
        dlat = drift * lat_deg_per_m * (1 if i % 2 == 0 else -1) * 0.3
        dlon = drift * lon_deg_per_m * (1 if i % 3 == 0 else -1) * 0.3
        positions.append(
            {
                "timestamp": ts,
                "lat": center_lat + dlat,
                "lon": center_lon + dlon,
                "speed": max(0.0, _normal_noise(rng, speed_mean, speed_std)),
                "heading": heading + _normal_noise(rng, 0, 5),
            }
        )
    return positions


def generate_synthetic_feature_row(*, anomaly: bool) -> list[float]:
    """One training row (feature vector only)."""
    cfg = get_config()
    syn = cfg["model"]["synthetic"]
    train = cfg["model"]["training"]
    rng = _rng()

    port_lat = 1.264 + _normal_noise(rng, 0, 0.01)
    port_lon = 103.84 + _normal_noise(rng, 0, 0.01)
    duration = rng.uniform(
        float(train["delivery_duration_hours_min"]),
        float(train["delivery_duration_hours_max"]),
    )
    n_points = int(train["samples_per_track"])
    start = datetime.now(timezone.utc) - timedelta(hours=duration)
    end = start + timedelta(hours=duration)

    if not anomaly:
        dist = max(10.0, _normal_noise(rng, float(syn["normal_distance_mean_m"]), float(syn["normal_distance_std_m"])))
        v_speed = max(0.0, _normal_noise(rng, float(syn["normal_speed_mean_knots"]), float(syn["normal_speed_std_knots"])))
        barge_offset_m = dist
        vessel = _generate_track(
            rng,
            center_lat=port_lat,
            center_lon=port_lon,
            n_points=n_points,
            duration_hours=duration,
            speed_mean=v_speed,
            speed_std=float(syn["normal_speed_std_knots"]),
            offset_m=float(syn["normal_drift_rate_max"]) * 1000,
            heading=90.0,
        )
        barge = _generate_track(
            rng,
            center_lat=port_lat + barge_offset_m / 111_320,
            center_lon=port_lon,
            n_points=n_points,
            duration_hours=duration,
            speed_mean=v_speed,
            speed_std=float(syn["normal_speed_std_knots"]),
            offset_m=5.0,
            heading=92.0,
        )
        qty = rng.uniform(200, 600)
    else:
        dist = max(50.0, _normal_noise(rng, float(syn["anomaly_distance_mean_m"]), 80))
        v_speed = max(0.0, _normal_noise(rng, float(syn["anomaly_speed_mean_knots"]), 1.5))
        vessel = _generate_track(
            rng,
            center_lat=port_lat + float(syn["anomaly_port_distance_km_min"]) / 111.0,
            center_lon=port_lon + 0.5,
            n_points=n_points,
            duration_hours=duration,
            speed_mean=v_speed,
            speed_std=1.0,
            offset_m=500.0,
            heading=180.0,
        )
        barge = _generate_track(
            rng,
            center_lat=port_lat,
            center_lon=port_lon,
            n_points=n_points,
            duration_hours=duration,
            speed_mean=0.2,
            speed_std=0.2,
            offset_m=5.0,
            heading=90.0,
        )
        qty = rng.uniform(800, 2000)

    result = build_feature_vector(
        vessel_positions=vessel,
        barge_positions=barge,
        port_lat=port_lat,
        port_lon=port_lon,
        delivery_start=start,
        delivery_end=end,
        quantity_mt=qty,
    )
    return result["vector"]


def generate_training_matrix() -> tuple[np.ndarray, np.ndarray]:
    """
    Returns X (n_samples, n_features) and y (0=normal, 1=anomaly) for evaluation only.
    Isolation Forest is unsupervised — y is not used for fit.
    """
    cfg = get_config()["model"]["training"]
    n_normal = int(cfg["n_normal_samples"])
    n_anomaly = int(cfg["n_anomaly_samples"])

    rows: list[list[float]] = []
    labels: list[int] = []

    for _ in range(n_normal):
        rows.append(generate_synthetic_feature_row(anomaly=False))
        labels.append(0)

    for _ in range(n_anomaly):
        rows.append(generate_synthetic_feature_row(anomaly=True))
        labels.append(1)

    return np.array(rows, dtype=np.float64), np.array(labels, dtype=np.int32)
