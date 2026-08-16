"""
stub/mock_ais.py

Used by orchestrator.py when pipeline.mock_ais = true.
Returns a synthetic AIS validation result without hitting the data provider.
"""

from __future__ import annotations

from typing import Any

from app.stub.mock_pipeline import _mock_map_html


def get_mock_ais_validation(
    identity: dict[str, Any],
    extraction: dict[str, Any],
    *,
    scenario: str | None = None,
) -> dict[str, Any]:
    """
    Return a mock AIS validation result.
    scenario: "valid" | "ais_unavailable" | "barge_missing" | None (→ valid)
    """
    scenario = scenario or "valid"
    port_lat = 1.264
    port_lon = 103.840

    if scenario in ("ais_unavailable", "ais"):
        return {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["ais_unavailable"],
            "evidence": {
                "ais_unavailable": True,
                "timezone_normalized": False,
                "map_html": _mock_map_html(port_lat, port_lon, None, None, port_lat, port_lon, barge_missing=True),
            },
        }

    if scenario == "barge_missing":
        return {
            "ais_unavailable": False,
            "anomaly_score": 0.45,
            "is_anomaly": False,
            "anomaly_flags": ["barge_ais_missing", "synthetic_ais_demo"],
            "evidence": {
                "ais_unavailable": False,
                "barge_ais_missing": True,
                "synthetic_ais_fallback": True,
                "co_location_duration_h": 0.0,
                "overlap_percent": 0.0,
                "avg_distance_m": None,
                "port_coordinate_match": True,
                "quantity_feasible": True,
                "map_html": _mock_map_html(port_lat, port_lon, None, None, port_lat, port_lon, barge_missing=True),
            },
        }

    # Default: "valid" scenario — normal co-located bunkering
    return {
        "ais_unavailable": False,
        "anomaly_score": 0.12,
        "is_anomaly": False,
        "anomaly_flags": ["synthetic_ais_demo"],
        "evidence": {
            "ais_unavailable": False,
            "barge_ais_missing": False,
            "synthetic_ais_fallback": True,
            "co_location_duration_h": 4.0,
            "overlap_percent": 95.0,
            "avg_distance_m": 88.0,
            "port_coordinate_match": True,
            "quantity_feasible": True,
            "timezone_normalized": True,
            "ais_anomaly_score": 0.12,
            "ais_anomaly_detected": False,
            "map_html": _mock_map_html(port_lat, port_lon, None, None, port_lat, port_lon),
        },
        "feature_vector": {
            "avg_distance_m": 88.0,
            "max_distance_m": 120.0,
            "overlap_percent": 95.0,
            "avg_speed_knots": 0.2,
            "port_coordinate_match": 1.0,
            "quantity_feasible": 1.0,
        },
    }
