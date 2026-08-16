"""
AIS geolocation validation: fetch tracks, build features, score with Isolation Forest.
Never raises — returns ais result dict for orchestrator.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.core.config_loader import get_config
from app.services.ais_service.history import fetch_positions
from app.services.ais_service.lookup import vessel_details
from app.services.timezone_service.converter import delivery_window_utc
from app.services.validation_service.features import build_feature_vector, descriptive_flags
from app.services.validation_service.maps import render_track_map
from app.services.validation_service.model import model_loaded, score_feature_vector
from app.stub.mock_pipeline import _mock_map_html

# Re-use synthetic track builder for demo fallback
from app.services.validation_service import synthetic_data


def _synthetic_positions_from_bdn(
    extraction: dict[str, Any],
    window: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Demo fallback: plausible tracks at declared port when API unavailable."""
    import random

    cfg = get_config()
    syn = cfg["model"]["synthetic"]
    train = cfg["model"]["training"]
    rng = random.Random(int(cfg["model"]["isolation_forest"]["random_state"]))

    port_lat = float(window.get("port_lat") or 0)
    port_lon = float(window.get("port_lon") or 0)
    start = window.get("start_utc") or datetime.now(timezone.utc)
    end = window.get("end_utc") or start
    duration = max((end - start).total_seconds() / 3600.0, float(train["delivery_duration_hours_min"]))
    n_points = int(train["samples_per_track"])

    vessel = synthetic_data._generate_track(
        rng,
        center_lat=port_lat,
        center_lon=port_lon,
        n_points=n_points,
        duration_hours=duration,
        speed_mean=float(syn["normal_speed_mean_knots"]),
        speed_std=float(syn["normal_speed_std_knots"]),
        offset_m=float(syn["normal_drift_rate_max"]) * 1000,
        heading=90.0,
    )
    for i, p in enumerate(vessel):
        p["timestamp"] = start + (end - start) * (i / max(n_points - 1, 1))

    dist = float(syn["normal_distance_mean_m"])
    barge = synthetic_data._generate_track(
        rng,
        center_lat=port_lat + dist / 111_320,
        center_lon=port_lon,
        n_points=n_points,
        duration_hours=duration,
        speed_mean=float(syn["normal_speed_mean_knots"]),
        speed_std=float(syn["normal_speed_std_knots"]),
        offset_m=5.0,
        heading=92.0,
    )
    for i, p in enumerate(barge):
        p["timestamp"] = start + (end - start) * (i / max(n_points - 1, 1))

    return vessel, barge


def run_ais_validation(
    identity: dict[str, Any],
    extraction: dict[str, Any],
    *,
    dev_scenario: str | None = None,
) -> dict[str, Any]:
    if dev_scenario in ("ais_unavailable", "ais"):
        return {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["ais_unavailable"],
            "evidence": {
                "ais_unavailable": True,
                "timezone_normalized": False,
                "map_html": _mock_map_html(1.264, 103.84, None, None, 1.264, 103.84, barge_missing=True),
            },
        }

    if identity.get("vessel_identity_unresolved"):
        return {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["vessel_identity_unresolved"],
            "evidence": {"ais_unavailable": True, "timezone_normalized": False},
        }

    window = delivery_window_utc(extraction)
    pipe = get_config().get("pipeline", {})
    confirmed_mmsi = identity.get("confirmed_mmsi")
    vessel_meta = vessel_details(identity.get("confirmed_imo"), confirmed_mmsi)
    if vessel_meta and vessel_meta.get("mmsi"):
        confirmed_mmsi = str(vessel_meta["mmsi"])

    vessel_positions: list[dict[str, Any]] = []
    barge_positions: list[dict[str, Any]] | None = None
    fetch_error: str | None = None
    used_synthetic_fallback = False

    if confirmed_mmsi and window.get("start_utc") and window.get("end_utc"):
        vessel_positions, fetch_error = fetch_positions(
            confirmed_mmsi, window["start_utc"], window["end_utc"]
        )

    if fetch_error or not vessel_positions:
        if pipe.get("synthetic_ais_fallback", True):
            vessel_positions, barge_positions = _synthetic_positions_from_bdn(extraction, window)
            used_synthetic_fallback = True
            fetch_error = None
        else:
            return {
                "ais_unavailable": True,
                "anomaly_score": 0.5,
                "is_anomaly": False,
                "anomaly_flags": ["ais_unavailable"],
                "evidence": {
                    "ais_unavailable": True,
                    "timezone_normalized": window.get("timezone_normalized", False),
                    "map_html": _mock_map_html(
                        float(window.get("port_lat") or 0),
                        float(window.get("port_lon") or 0),
                        None,
                        None,
                        float(window.get("port_lat") or 0),
                        float(window.get("port_lon") or 0),
                        barge_missing=True,
                    ),
                },
            }

    barge_missing = dev_scenario == "barge_missing"
    if barge_missing:
        barge_positions = None
    elif barge_positions is None and not used_synthetic_fallback:
        barge_positions = []

    feature_result = build_feature_vector(
        vessel_positions=vessel_positions,
        barge_positions=barge_positions if not barge_missing else None,
        port_lat=window.get("port_lat"),
        port_lon=window.get("port_lon"),
        delivery_start=window.get("start_utc"),
        delivery_end=window.get("end_utc"),
        quantity_mt=extraction.get("quantity_mt"),
    )

    ml_result = score_feature_vector(feature_result["vector"])
    if not model_loaded() and pipe.get("use_ml_when_model_missing", True):
        ml_result = {
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "model_loaded": False,
        }

    flags = descriptive_flags(feature_result, barge_missing=barge_missing or not barge_positions)
    if used_synthetic_fallback:
        flags.append("synthetic_ais_demo")
    if fetch_error:
        flags.append("ais_unavailable")

    map_html = render_track_map(
        vessel_positions,
        barge_positions,
        window.get("port_lat"),
        window.get("port_lon"),
    )

    evidence = {
        "co_location_duration_h": feature_result["co_location_duration_h"],
        "overlap_percent": feature_result["overlap_percent"],
        "avg_distance_m": feature_result["avg_distance_m"],
        "port_coordinate_match": feature_result["port_coordinate_match"],
        "quantity_feasible": feature_result["quantity_feasible"],
        "timezone_normalized": window.get("timezone_normalized", False),
        "ais_anomaly_score": ml_result.get("anomaly_score"),
        "ais_anomaly_detected": ml_result.get("is_anomaly"),
        "ais_unavailable": False,
        "barge_ais_missing": barge_missing or (barge_positions is not None and len(barge_positions) == 0),
        "synthetic_ais_fallback": used_synthetic_fallback,
        "map_html": map_html,
    }

    return {
        "ais_unavailable": False,
        "anomaly_score": ml_result.get("anomaly_score", 0.5),
        "is_anomaly": ml_result.get("is_anomaly", False),
        "anomaly_flags": flags,
        "evidence": evidence,
        "feature_vector": feature_result["features"],
    }
