"""
stub/mock_pipeline.py

Mock pipeline used in three places:
  1. main.py          — seed_transactions() for demo data on startup
                        run_mock_validation() as last-resort error fallback
  2. orchestrator.py  — run_mock_validation() when pipeline.use_mock=true
  3. ais/validate.py  — _mock_map_html() for the static fallback map
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tx_id() -> str:
    year = datetime.now(timezone.utc).year
    return f"BDN-{year}-{uuid.uuid4().hex[:6].upper()}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Map HTML ───────────────────────────────────────────────────────────────────

def _mock_map_html(
    vessel_lat: float | None,
    vessel_lon: float | None,
    vessel_track: Any,
    barge_track: Any,
    barge_lat: float | None,
    barge_lon: float | None,
    *,
    barge_missing: bool = False,
) -> str:
    """Return a minimal static HTML map placeholder (no external dependencies)."""
    v_lat = round(vessel_lat or 1.264, 5)
    v_lon = round(vessel_lon or 103.840, 5)
    b_lat = round(barge_lat or v_lat, 5)
    b_lon = round(barge_lon or v_lon, 5)
    barge_label = "Barge AIS unavailable" if barge_missing else f"Barge ({b_lat}, {b_lon})"

    return f"""
<div style="background:#1a1a2e;color:#a0aec0;padding:16px;border-radius:8px;font-family:monospace;font-size:12px;">
  <div style="color:#63b3ed;font-weight:bold;margin-bottom:8px;">AIS Track Map (stub)</div>
  <div>Vessel: {v_lat}, {v_lon}</div>
  <div style="color:{'#fc8181' if barge_missing else '#68d391'}">{barge_label}</div>
  <div style="margin-top:8px;color:#718096;">Live map unavailable — AIS data is synthetic or missing.</div>
</div>
""".strip()


# ── Single mock verdict ────────────────────────────────────────────────────────

def run_mock_validation(
    filename: str | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    """
    Return a plausible mock verdict dict.
    scenario: "valid" | "unresolved" | "ais_unavailable" | None (→ valid)
    """
    scenario = scenario or "valid"
    tx_id = _tx_id()
    now = _now()

    base_extraction = {
        "vessel_name": "STUB VESSEL",
        "imo": "9000001",
        "barge_name": "STUB BARGE 001",
        "port": "Singapore",
        "quantity_mt": 500.0,
        "density": 0.991,
        "sulphur_content": 0.49,
        "flashpoint": 62.0,
        "fuel_type": "VLSFO",
        "delivery_date": "2026-01-15",
        "start_time": "08:00",
        "end_time": "12:00",
        "supplier": "Stub Bunker Co",
        "doc_type": "DIGITAL",
        "ocr_confidence": 0.88,
        "extraction_confidence": 0.75,
    }

    if scenario == "unresolved":
        classification = "HIGH_RISK"
        confidence = 0.22
        identity = {
            "vessel_identity_unresolved": True,
            "identity_confidence": 0.0,
            "resolution_method": "unresolved",
            "flags": ["VESSEL_NOT_FOUND"],
        }
        fraud_alerts = [{"type": "VESSEL_NOT_FOUND", "severity": "HIGH",
                         "detail": "Vessel could not be resolved in registry."}]
        ais = {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["vessel_identity_unresolved"],
            "evidence": {"ais_unavailable": True},
        }
    elif scenario in ("ais_unavailable", "ais"):
        classification = "REVIEW_REQUIRED"
        confidence = 0.55
        identity = {
            "vessel_identity_unresolved": False,
            "confirmed_imo": "9000001",
            "confirmed_name": "STUB VESSEL",
            "confirmed_mmsi": "123456789",
            "identity_confidence": 0.75,
            "resolution_method": "stub",
            "flags": [],
        }
        fraud_alerts = []
        ais = {
            "ais_unavailable": True,
            "anomaly_score": 0.5,
            "is_anomaly": False,
            "anomaly_flags": ["ais_unavailable"],
            "evidence": {
                "ais_unavailable": True,
                "map_html": _mock_map_html(1.264, 103.84, None, None, 1.264, 103.84, barge_missing=True),
            },
        }
    else:  # "valid"
        classification = "VALID"
        confidence = 0.87
        identity = {
            "vessel_identity_unresolved": False,
            "confirmed_imo": "9000001",
            "confirmed_name": "STUB VESSEL",
            "confirmed_mmsi": "123456789",
            "identity_confidence": 0.90,
            "resolution_method": "stub",
            "flags": [],
        }
        fraud_alerts = []
        ais = {
            "ais_unavailable": False,
            "anomaly_score": 0.12,
            "is_anomaly": False,
            "anomaly_flags": ["synthetic_ais_demo"],
            "evidence": {
                "ais_unavailable": False,
                "co_location_duration_h": 4.0,
                "overlap_percent": 95.0,
                "avg_distance_m": 88.0,
                "port_coordinate_match": True,
                "quantity_feasible": True,
                "barge_ais_missing": False,
                "synthetic_ais_fallback": True,
                "map_html": _mock_map_html(1.264, 103.84, None, None, 1.264, 103.84),
            },
        }

    return {
        "transaction_id": tx_id,
        "classification": classification,
        "confidence": confidence,
        "human_review_required": classification in ("HIGH_RISK", "SUSPICIOUS", "REVIEW_REQUIRED"),
        "verdict_reason": f"Mock validation — scenario: {scenario}",
        "validated_at": now,
        "upload_filename": filename,
        "source": "mock",
        "extraction": base_extraction,
        "credibility": {
            "credibility_score": 80,
            "credibility_flags": [],
            "marpol_violations": [],
        },
        "identity_resolution": identity,
        "barge_resolution": {
            "barge_confirmed_name": "STUB BARGE 001",
            "barge_confidence": 0.70,
            "barge_ais_missing": scenario in ("ais_unavailable", "unresolved"),
            "barge_identity_conflict": False,
        },
        "ais_validation": ais,
        "fraud_alerts": fraud_alerts,
        "confidence_scores": {
            "ocr": 0.88,
            "extraction": 0.75,
            "vessel_verification": identity.get("identity_confidence", 0),
            "barge_verification": 0.70,
            "geolocation": 0.0 if ais.get("ais_unavailable") else 0.88,
            "overall": confidence,
        },
        "audit_trail": [
            {"timestamp": now, "action": "mock_validation", "detail": f"scenario={scenario}"},
        ],
        "anomaly_flags": ais.get("anomaly_flags", []),
    }


# ── Seed data ──────────────────────────────────────────────────────────────────

def seed_transactions() -> list[dict[str, Any]]:
    """Return a small set of demo transactions for the dashboard on startup."""
    return [
        run_mock_validation(filename="sample_valid.pdf", scenario="valid"),
        run_mock_validation(filename="sample_review.pdf", scenario="ais_unavailable"),
        run_mock_validation(filename="sample_highrisk.pdf", scenario="unresolved"),
    ]
