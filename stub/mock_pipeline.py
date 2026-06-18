"""
Phase 0 mock validation pipeline.
Returns a complete verdict JSON without external APIs or ML.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from core.config_loader import get_config


def _mock_map_html(
    vessel_lat: float,
    vessel_lon: float,
    barge_lat: float | None,
    barge_lon: float | None,
    port_lat: float,
    port_lon: float,
    barge_missing: bool = False,
) -> str:
    """Lightweight map placeholder (Phase 3+ will use Folium)."""
    barge_note = (
        "<p class='map-note'>Barge AIS unavailable — track not shown.</p>"
        if barge_missing
        else f"<p class='map-note'>Barge track (orange) near {barge_lat:.4f}, {barge_lon:.4f}</p>"
    )
    return f"""<div class="mock-map">
  <h4>AIS Track Preview (mock)</h4>
  <svg viewBox="0 0 400 220" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="AIS track map">
    <rect width="400" height="220" fill="#0d2137"/>
    <circle cx="200" cy="110" r="6" fill="#38bdf8"/>
    <text x="210" y="114" fill="#94a3b8" font-size="10">Vessel</text>
    {"<circle cx='230' cy='95' r='5' fill='#fb923c'/><text x='240' y='99' fill='#94a3b8' font-size='10'>Barge</text>" if not barge_missing else ""}
    <polygon points="120,160 125,150 130,160" fill="#22c55e"/>
    <text x="135" y="165" fill="#86efac" font-size="10">Port</text>
    <line x1="80" y1="180" x2="320" y2="40" stroke="#38bdf8" stroke-width="2" opacity="0.7"/>
    {"<line x1='200' y1='110' x2='230' y2='95' stroke='#fb923c' stroke-width='1.5' stroke-dasharray='4'/>" if not barge_missing else ""}
  </svg>
  <p class="map-note">Vessel centroid: {vessel_lat:.4f}, {vessel_lon:.4f}</p>
  {barge_note}
  <p class="map-note">Port anchor: {port_lat:.4f}, {port_lon:.4f}</p>
</div>"""


def _verdict_valid(transaction_id: str, filename: str | None) -> dict[str, Any]:
    # Use BERGE MERU cache data
    vessel_lat = 1.2705
    vessel_lon = 103.9374
    port_lat = 1.264
    port_lon = 103.84
    return {
        "transaction_id": transaction_id,
        "classification": "VALID",
        "confidence": 0.91,
        "verdict_reason": (
            "Document credible. Vessel identity confirmed via embedding match. "
            "AIS confirms co-location at declared port for full delivery window. "
            "Quantity consistent with pump rate."
        ),
        "human_review_required": False,
        "source": "mock",
        "upload_filename": filename,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        # Identity
        "identity_resolution": {
            "confirmed_imo": "9855214",
            "confirmed_mmsi": "232024256",
            "confirmed_name": "BERGE MERU",
            "bdn_name": "BERG MERU",
            "bdn_imo": "9855214",
            "resolution_method": "embedding",
            "identity_confidence": 0.98,
            "vessel_identity_unresolved": False,
            "registered_flag": "GB",
            "vessel_type": "Bulk Carrier",
            "flags": ["vessel_name_fuzzy_match"],
            "candidates": [],
        },
        # Barge (Phase 5)
        "barge_resolution": {
            "barge_confirmed_name": "PACIFIC BUNKER VII",
            "barge_mmsi": "566123456",
            "barge_imo": None,
            "resolution_method": "mpa_registry_name",
            "barge_confidence": 0.88,
            "barge_ais_missing": False,
            "barge_flags": [],
        },
        # Extraction
        "extraction": {
            "vessel_name": "BERG MERU",
            "imo": "9855214",
            "barge_name": "PACIFIC BUNKER VII",
            "barge_sb_number": None,
            "delivery_date": "19 April 2026",
            "start_time": "19 April 2026 08:00",
            "end_time": "19 April 2026 11:12",
            "port": "Singapore",
            "quantity_mt": 485.5,
            "density": 0.985,
            "sulphur_content": 0.48,
            "flashpoint": 63.0,
            "fuel_type": "VLSFO",
            "supplier": "Ocean Fuels Pte Ltd",
            "seal_number_vessel": "SV-20240512",
            "seal_number_marpol": "MARPOL-789",
            "seal_number_barge": "SB-456",
            "ocr_confidence": 0.96,
            "extraction_confidence": 0.91,
            "doc_type": "DIGITAL",
        },
        # Fraud (Phase 7)
        "fraud_alerts": [],
        "overall_fraud_risk": "NONE",
        # Confidence scores (Phase 8)
        "confidence_scores": {
            "ocr": 0.96,
            "extraction": 0.91,
            "vessel": 0.98,
            "barge": 0.88,
            "geolocation": 0.95,
            "overall": 0.94,
        },
        # Audit trail (Phase 8)
        "audit_trail": [
            {"step": "OCR", "result": "confidence 0.96", "threshold": "0.85", "passed": True, "method": None},
            {"step": "EXTRACTION", "result": "confidence 0.91", "threshold": "0.50", "passed": True, "method": None},
            {"step": "VESSEL_IDENTITY", "result": "embedding match 0.98", "threshold": "0.80", "passed": True, "method": "embedding"},
            {"step": "BARGE_IDENTITY", "result": "mpa_registry_name confidence 0.88", "threshold": "0.70", "passed": True, "method": "mpa_registry_name"},
            {"step": "GEOLOCATION_ML", "result": "anomaly_score 0.12", "threshold": "0.55", "passed": True, "method": "IsolationForest"},
        ],
        # Evidence
        "evidence": {
            "credibility_score": 88,
            "ocr_confidence": 0.96,
            "extraction_confidence": 0.91,
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
            "duplicate_detected": False,
            "duplicate_transaction_ids": [],
            "map_html": _mock_map_html(vessel_lat, vessel_lon, vessel_lat + 0.001, vessel_lon + 0.001, port_lat, port_lon),
        },
        "anomaly_flags": [],
        "credibility_flags": [],
    }



def _verdict_unresolved(transaction_id: str, filename: str | None) -> dict[str, Any]:
    verdict = _verdict_valid(transaction_id, filename)
    verdict.update(
        {
            "classification": "HIGH_RISK",
            "confidence": 0.38,
            "human_review_required": True,
            "identity_resolution": {
                "confirmed_imo": None,
                "confirmed_mmsi": None,
                "confirmed_name": None,
                "bdn_name": "OCEAN STAR",
                "bdn_imo": "1234567",
                "resolution_method": "unresolved",
                "identity_confidence": 0.22,
                "vessel_identity_unresolved": True,
                "registered_flag": None,
                "vessel_type": None,
                "flags": ["vessel_identity_unresolved"],
                "candidates": [
                    {"imo": "1234567", "name": "OCEAN STAR", "source": "bdn_imo_lookup"},
                    {"imo": "7654321", "name": "OCEAN STAR TRADER", "source": "bdn_name_reverse_lookup"},
                ],
            },
            "barge_resolution": {
                "barge_confirmed_name": "PACIFIC BUNKER VII",
                "barge_mmsi": None,
                "barge_imo": None,
                "resolution_method": "unresolved",
                "barge_confidence": 0.0,
                "barge_ais_missing": True,
                "barge_flags": ["barge_ais_missing"],
            },
            "fraud_alerts": [
                {
                    "alert_type": "VESSEL_IDENTITY_UNRESOLVED",
                    "severity": "HIGH",
                    "explanation": "IMO 1234567 and vessel name 'OCEAN STAR' resolve to different registrations. Manual verification required.",
                    "evidence": {"bdn_imo": "1234567", "bdn_name": "OCEAN STAR"},
                },
                {
                    "alert_type": "BARGE_UNVERIFIED",
                    "severity": "MEDIUM",
                    "explanation": "Barge 'PACIFIC BUNKER VII' could not be resolved via MPA registry or Datalastic.",
                    "evidence": {},
                },
            ],
            "overall_fraud_risk": "HIGH",
            "confidence_scores": {
                "ocr": 0.96, "extraction": 0.91,
                "vessel": 0.22, "barge": 0.0,
                "geolocation": 0.5, "overall": 0.38,
            },
            "audit_trail": [
                {"step": "OCR", "result": "confidence 0.96", "threshold": "0.85", "passed": True, "method": None},
                {"step": "EXTRACTION", "result": "confidence 0.91", "threshold": "0.50", "passed": True, "method": None},
                {"step": "VESSEL_IDENTITY", "result": "unresolved match 0.22", "threshold": "0.80", "passed": False, "method": "unresolved"},
                {"step": "BARGE_IDENTITY", "result": "unresolved confidence 0.00", "threshold": "0.70", "passed": False, "method": "unresolved"},
                {"step": "GEOLOCATION_ML", "result": "anomaly_score 0.50", "threshold": "0.55", "passed": True, "method": "IsolationForest"},
            ],
            "anomaly_flags": ["vessel_identity_unresolved"],
            "verdict_reason": (
                "Vessel identity could not be resolved — BDN IMO and name indicate different registrations. "
                "High-severity fraud alerts: 1. Human review required."
            ),
        }
    )
    verdict["evidence"]["map_html"] = _mock_map_html(
        1.1, 103.5, None, None, 1.264, 103.84, barge_missing=True
    )
    verdict["evidence"]["barge_ais_missing"] = True
    return verdict


def _verdict_suspicious_ais(transaction_id: str, filename: str | None) -> dict[str, Any]:
    verdict = _verdict_valid(transaction_id, filename)
    verdict.update(
        {
            "classification": "SUSPICIOUS",
            "confidence": 0.58,
            "human_review_required": False,
            "evidence": {
                **verdict["evidence"],
                "ais_unavailable": True,
                "ais_anomaly_score": None,
                "ais_anomaly_detected": None,
            },
            "fraud_alerts": [
                {
                    "alert_type": "BARGE_AIS_MISSING",
                    "severity": "LOW",
                    "explanation": "Barge 'PACIFIC BUNKER VII' was identified but has no AIS data for the delivery window.",
                    "evidence": {},
                },
            ],
            "overall_fraud_risk": "LOW",
            "confidence_scores": {
                "ocr": 0.96, "extraction": 0.91,
                "vessel": 0.84, "barge": 0.88,
                "geolocation": 0.0, "overall": 0.58,
            },
            "audit_trail": [
                {"step": "OCR", "result": "confidence 0.96", "threshold": "0.85", "passed": True, "method": None},
                {"step": "EXTRACTION", "result": "confidence 0.91", "threshold": "0.50", "passed": True, "method": None},
                {"step": "VESSEL_IDENTITY", "result": "embedding match 0.84", "threshold": "0.80", "passed": True, "method": "embedding"},
                {"step": "BARGE_IDENTITY", "result": "mpa_registry_name confidence 0.88", "threshold": "0.70", "passed": True, "method": "mpa_registry_name"},
                {"step": "GEOLOCATION_ML", "result": "ais_unavailable", "threshold": "0.55", "passed": False, "method": None},
            ],
            "anomaly_flags": ["ais_unavailable"],
            "verdict_reason": (
                "Document and vessel identity appear credible, but AIS data "
                "could not be retrieved from Datalastic. Manual verification recommended."
            ),
        }
    )
    return verdict


def run_mock_validation(
    filename: str | None = None,
    scenario: str | None = None,
) -> dict[str, Any]:
    """
    Run mock validation and return full verdict JSON.

    scenario: None | 'valid' | 'unresolved' | 'ais_unavailable'
    """
    config = get_config()
    prefix = "BDN"
    year = datetime.now(timezone.utc).year
    short_id = uuid.uuid4().hex[:6].upper()
    transaction_id = f"{prefix}-{year}-{short_id}"

    scenario = scenario or "valid"
    if scenario == "unresolved":
        return _verdict_unresolved(transaction_id, filename)
    if scenario in ("ais_unavailable", "ais"):
        return _verdict_suspicious_ais(transaction_id, filename)
    return _verdict_valid(transaction_id, filename)


def seed_transactions() -> list[dict[str, Any]]:
    """Pre-load demo rows for transactions history."""
    return [
        {k: v for k, v in run_mock_validation("sample_valid.pdf", "valid").items()},
        {k: v for k, v in run_mock_validation("sample_unresolved.pdf", "unresolved").items()},
        {k: v for k, v in run_mock_validation("sample_ais.pdf", "ais_unavailable").items()},
    ]
