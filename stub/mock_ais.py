"""
Mock AIS validation (Phase 3 replaces with Datalastic history + ML features).
"""

from __future__ import annotations

from typing import Any

from core.config_loader import get_config
from stub.mock_pipeline import _mock_map_html


def get_mock_ais_validation(
    identity: dict[str, Any],
    extraction: dict[str, Any],
    *,
    scenario: str | None = None,
) -> dict[str, Any]:
    """
    Return AIS evidence block and anomaly flags for orchestrator scoring.
    scenario: None | ais_unavailable | barge_missing
    """
    config = get_config()
    default_class = config["ais"]["missing_barge_default_classification"]

    if scenario in ("ais_unavailable", "ais"):
        return {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["ais_unavailable"],
            "evidence": {
                "ais_unavailable": True,
                "ais_anomaly_score": None,
                "ais_anomaly_detected": None,
                "barge_ais_missing": False,
                "timezone_normalized": False,
                "map_html": _mock_map_html(1.264, 103.84, None, None, 1.264, 103.84, barge_missing=True),
            },
            "default_classification_hint": default_class,
        }

    if scenario == "barge_missing":
        return {
            "ais_unavailable": False,
            "anomaly_score": 0.35,
            "is_anomaly": False,
            "anomaly_flags": ["barge_ais_missing"],
            "evidence": {
                "co_location_duration_h": 2.1,
                "overlap_percent": 45,
                "avg_distance_m": 150,
                "port_coordinate_match": True,
                "quantity_feasible": True,
                "timezone_normalized": True,
                "ais_anomaly_score": 0.35,
                "ais_anomaly_detected": False,
                "ais_unavailable": False,
                "barge_ais_missing": True,
                "map_html": _mock_map_html(1.264, 103.84, None, None, 1.264, 103.84, barge_missing=True),
            },
            "default_classification_hint": default_class,
        }

    if identity.get("vessel_identity_unresolved"):
        return {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": [],
            "evidence": {
                "ais_unavailable": True,
                "timezone_normalized": False,
                "map_html": _mock_map_html(1.1, 103.5, None, None, 1.264, 103.84, barge_missing=True),
            },
            "default_classification_hint": "HIGH_RISK",
        }

    return {
        "ais_unavailable": False,
        "anomaly_score": 0.12,
        "is_anomaly": False,
        "anomaly_flags": [],
        "evidence": {
            "co_location_duration_h": 3.2,
            "overlap_percent": 87,
            "avg_distance_m": 82,
            "port_coordinate_match": True,
            "quantity_feasible": True,
            "timezone_normalized": True,
            "ais_anomaly_score": 0.12,
            "ais_anomaly_detected": False,
            "ais_unavailable": False,
            "barge_ais_missing": False,
            "map_html": _mock_map_html(1.264, 103.84, 1.265, 103.841, 1.264, 103.84),
        },
        "default_classification_hint": None,
    }
