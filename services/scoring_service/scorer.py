"""
Scoring service — Phase 8.
6-dimensional confidence scoring + audit trail.
Weights and thresholds from config.yaml confidence_scoring section.

Classification ladder:
  HIGH_RISK       — confirmed anomaly, identity unresolved, or HIGH fraud alert
  SUSPICIOUS      — negative evidence present (AIS mismatch detected, medium fraud)
  REVIEW_REQUIRED — AIS unavailable / missing evidence, no confirmed negative signal
  VALID           — all checks passed above threshold

Key rule: missing evidence ≠ negative evidence.
  ais_unavailable → REVIEW_REQUIRED (not SUSPICIOUS)
  is_anomaly      → contributes to HIGH_RISK/SUSPICIOUS
"""

from __future__ import annotations

from typing import Any

from core.config_loader import get_config


def _weights() -> dict[str, float]:
    cfg = get_config().get("confidence_scoring", {}).get("weights", {})
    return {
        "ocr":               float(cfg.get("ocr", 0.20)),
        "extraction":        float(cfg.get("extraction", 0.20)),
        "vessel_verification": float(cfg.get("vessel_verification", 0.20)),
        "barge_verification":  float(cfg.get("barge_verification", 0.15)),
        "geolocation":       float(cfg.get("geolocation", 0.25)),
    }


def _thresholds() -> dict[str, float]:
    cfg = get_config().get("confidence_scoring", {}).get("thresholds", {})
    # Fall back to legacy scoring thresholds
    legacy = get_config().get("scoring", {}).get("thresholds", {})
    return {
        "valid":    float(cfg.get("valid", legacy.get("valid_min_confidence", 75))) / 100,
        "suspicious": float(cfg.get("review_required", legacy.get("suspicious_min_confidence", 50))) / 100,
    }


def _audit_step(step: str, result: str, threshold: str, passed: bool, method: str | None = None) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "step": step,
        "result": result,
        "threshold": threshold,
        "passed": passed,
    }
    if method:
        entry["method"] = method
    return entry


def compute_score(
    *,
    ocr_confidence: float,
    extraction_confidence: float,
    identity: dict[str, Any],
    barge: dict[str, Any],
    ais: dict[str, Any],
    credibility_flags: list[str],
    fraud_result: dict[str, Any],
) -> dict[str, Any]:
    """
    Compute 6-dimensional scores, overall confidence, classification, and audit trail.
    """
    weights = _weights()
    thresholds = _thresholds()
    cfg = get_config().get("confidence_scoring", {}).get("thresholds", {})

    # Dimension scores (0–1)
    ocr_score = float(ocr_confidence)
    ext_score = float(extraction_confidence)
    vessel_score = float(identity.get("identity_confidence") or 0.0)
    barge_score = float(barge.get("barge_confidence") or 0.5)  # 0.5 if unknown

    # ── Geolocation score: distinguish missing vs negative evidence ──
    ais_unavailable = ais.get("ais_unavailable", False)
    is_anomaly = ais.get("is_anomaly", False)
    if ais_unavailable:
        # Missing evidence: small penalty (0.1) only — not a fraud signal
        geo_score = 0.9
    else:
        # Real AIS data: score based on anomaly result
        geo_score = max(0.0, 1.0 - float(ais.get("anomaly_score") or 0.5))

    overall = round(
        ocr_score * weights["ocr"]
        + ext_score * weights["extraction"]
        + vessel_score * weights["vessel_verification"]
        + barge_score * weights["barge_verification"]
        + geo_score * weights["geolocation"],
        3,
    )

    # Classification — missing evidence vs negative evidence
    unresolved = identity.get("vessel_identity_unresolved", False)
    high_fraud = fraud_result.get("overall_fraud_risk") == "HIGH"
    med_fraud = fraud_result.get("overall_fraud_risk") == "MEDIUM"

    # Missing-evidence-only flags: these do NOT constitute fraud/anomaly
    _missing_evidence_flags = {"ais_unavailable", "barge_ais_missing", "synthetic_ais_demo"}
    anomaly_flags = set(ais.get("anomaly_flags") or [])
    has_only_missing_evidence = (
        ais_unavailable
        and not is_anomaly
        and anomaly_flags.issubset(_missing_evidence_flags)
    )

    if unresolved or high_fraud or is_anomaly:
        classification = "HIGH_RISK"
    elif has_only_missing_evidence and not med_fraud and not unresolved:
        # AIS unavailable, no fraud, no anomaly → REVIEW_REQUIRED not SUSPICIOUS
        classification = "REVIEW_REQUIRED"
    elif overall >= thresholds["valid"]:
        classification = "VALID"
    elif overall >= thresholds["suspicious"]:
        classification = "SUSPICIOUS"
    else:
        classification = "HIGH_RISK"

    human_review = (
        fraud_result.get("requires_human_review", False)
        or unresolved
        or classification in ("HIGH_RISK", "REVIEW_REQUIRED")
    )

    # ── Audit trail ─────────────────────────────────────────────────
    ocr_thr = get_config().get("ocr", {}).get("confidence_threshold", 0.85)
    audit_trail: list[dict[str, Any]] = [
        _audit_step(
            "OCR",
            f"confidence {ocr_score:.2f}",
            f"{ocr_thr:.2f}",
            ocr_score >= float(ocr_thr),
        ),
        _audit_step(
            "EXTRACTION",
            f"confidence {ext_score:.2f}",
            "0.50",
            ext_score >= 0.50,
        ),
        _audit_step(
            "VESSEL_IDENTITY",
            f"{identity.get('resolution_method', 'unresolved')} match {vessel_score:.2f}",
            f"{get_config().get('identity', {}).get('fuzzy_match_threshold', 0.80):.2f}",
            not unresolved,
            method=identity.get("resolution_method"),
        ),
        _audit_step(
            "BARGE_IDENTITY",
            f"{barge.get('resolution_method', 'unresolved')} confidence {barge_score:.2f}",
            "0.70",
            barge_score >= 0.70,
            method=barge.get("resolution_method"),
        ),
        _audit_step(
            "GEOLOCATION_ML",
            "ais_unavailable" if ais_unavailable else f"anomaly_score {ais.get('anomaly_score', 0.5):.2f}",
            f"{get_config().get('model', {}).get('isolation_forest', {}).get('anomaly_score_threshold', 0.55):.2f}",
            not is_anomaly and not ais_unavailable,
            method=None if ais_unavailable else "IsolationForest",
        ),
    ]

    # Trim audit trail to configured max
    max_entries = int(get_config().get("reporting", {}).get("audit_trail_max_entries", 50))
    audit_trail = audit_trail[:max_entries]

    # Verdict reason (plain English)
    reason_parts: list[str] = []
    if classification == "VALID":
        reason_parts.append("All validation checks passed.")
        reason_parts.append(f"Vessel identity confirmed via {identity.get('resolution_method', 'registry')}.")
        if not ais_unavailable:
            reason_parts.append("AIS confirms co-location at declared port during delivery window.")
    elif classification == "REVIEW_REQUIRED":
        reason_parts.append("AIS evidence unavailable during delivery window.")
        reason_parts.append("Document and identity checks passed. No anomaly detected — geolocation could not be verified.")
    elif classification == "SUSPICIOUS":
        if is_anomaly:
            reason_parts.append("AIS mismatch detected.")
        else:
            reason_parts.append("Overall confidence below threshold. Some checks require attention.")
        if med_fraud:
            reason_parts.append(f"Medium-severity alerts: {len([a for a in fraud_result.get('fraud_alerts', []) if a.get('severity') == 'MEDIUM'])}.")
    else:  # HIGH_RISK
        if unresolved:
            reason_parts.append("Vessel identity conflict detected — BDN IMO and name resolve to different registrations.")
        if is_anomaly:
            reason_parts.append("AIS behaviour during delivery matches an anomalous pattern (ML).")
        if high_fraud:
            n_high = len([a for a in fraud_result.get('fraud_alerts', []) if a.get('severity') == 'HIGH'])
            reason_parts.append(f"High-severity fraud alert{'s' if n_high > 1 else ''}: {n_high} detected.")

    if credibility_flags:
        key_flags = [f for f in credibility_flags if f not in ("handwritten_document", "sb_number_absent")][:3]
        if key_flags:
            reason_parts.append(f"Document flags: {', '.join(key_flags)}.")

    return {
        "classification": classification,
        "confidence": overall,
        "confidence_scores": {
            "ocr": round(ocr_score, 3),
            "extraction": round(ext_score, 3),
            "vessel": round(vessel_score, 3),
            "barge": round(barge_score, 3),
            "geolocation": round(geo_score, 3),
            "overall": overall,
        },
        "human_review_required": human_review,
        "verdict_reason": " ".join(reason_parts),
        "audit_trail": audit_trail,
        # Explicit evidence-status field for dashboard/API consumers
        "ais_evidence_status": (
            "unavailable" if ais_unavailable
            else "anomaly_detected" if is_anomaly
            else "confirmed"
        ),
    }
