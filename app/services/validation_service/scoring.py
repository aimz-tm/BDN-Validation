"""
Combined risk scoring and final verdict classification.
"""

from __future__ import annotations

from typing import Any

from app.core.config_loader import get_config


def _combined_confidence(
    credibility_score: float,
    identity_confidence: float,
    anomaly_score: float,
) -> float:
    weights = get_config()["scoring"]["weights"]
    cred_norm = credibility_score / 100.0
    ais_component = 1.0 - anomaly_score
    return round(
        cred_norm * float(weights["document_credibility"])
        + identity_confidence * float(weights["identity_confidence"])
        + ais_component * float(weights["ais_anomaly_score"]),
        3,
    )


def _credibility_tier(score: float) -> str:
    if score >= 70:
        return "high"
    if score >= 45:
        return "low"
    return "very_low"


def compute_verdict(
    *,
    credibility_score: float,
    credibility_flags: list[str],
    identity: dict[str, Any],
    ais: dict[str, Any],
) -> dict[str, Any]:
    """
    Apply spec verdict matrix; return classification, confidence, reason, human_review_required.
    """
    thresholds = get_config()["scoring"]["thresholds"]
    identity_conf = float(identity.get("identity_confidence") or 0.0)
    anomaly_score = float(ais.get("anomaly_score") or 0.5)
    combined = _combined_confidence(credibility_score, identity_conf, anomaly_score)

    unresolved = identity.get("vessel_identity_unresolved", False)
    ais_unavailable = ais.get("ais_unavailable", False)
    is_anomaly = bool(ais.get("is_anomaly", False))
    cred_tier = _credibility_tier(credibility_score)
    identity_confirmed = not unresolved and identity.get("confirmed_imo")

    human_review = unresolved
    classification = "SUSPICIOUS"
    reason_parts: list[str] = []

    if unresolved:
        classification = "HIGH_RISK"
        human_review = True
        reason_parts.append(
            "Vessel identity could not be resolved — BDN IMO and name indicate different registrations."
        )
    elif is_anomaly:
        classification = "HIGH_RISK"
        reason_parts.append("AIS behaviour during delivery matches an anomalous pattern (ML).")
    elif ais_unavailable:
        if cred_tier == "high" and identity_confirmed:
            classification = "SUSPICIOUS"
            reason_parts.append(
                "Document and identity appear credible, but AIS data was unavailable for verification."
            )
        else:
            classification = "HIGH_RISK"
            reason_parts.append("AIS unavailable and document or identity confidence is insufficient.")
    elif combined >= float(thresholds["valid_min_confidence"]) and cred_tier == "high" and identity_confirmed:
        classification = "VALID"
        reason_parts.append("Document credible.")
        method = identity.get("resolution_method", "unknown")
        reason_parts.append(f"Vessel identity confirmed via {method} match.")
        reason_parts.append("AIS supports co-location at declared port for the delivery window.")
    elif combined >= float(thresholds["suspicious_min_confidence"]):
        classification = "SUSPICIOUS"
        reason_parts.append("Some checks passed but overall confidence is below VALID threshold.")
    else:
        classification = "HIGH_RISK"
        reason_parts.append("Low combined confidence across document, identity, and AIS signals.")

    if credibility_flags:
        reason_parts.append(f"Document flags: {', '.join(credibility_flags)}.")

    if classification == "HIGH_RISK":
        human_review = human_review or unresolved

    return {
        "classification": classification,
        "confidence": combined,
        "human_review_required": human_review,
        "verdict_reason": " ".join(reason_parts),
    }
