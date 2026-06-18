"""
Fraud detector — Phase 7.
Aggregates all flags from all verification services into human-readable fraud alerts.
Alert types and severities from config.yaml fraud_detection.alert_severities.
"""

from __future__ import annotations

from typing import Any

from core.config_loader import get_config

# Default severities — overridable from config
_DEFAULT_SEVERITIES: dict[str, str] = {
    "VESSEL_NOT_FOUND":           "HIGH",
    "IMO_MISMATCH":               "HIGH",
    "VESSEL_IDENTITY_UNRESOLVED": "HIGH",
    "BARGE_IDENTITY_CONFLICT":    "HIGH",
    "EXCESSIVE_DISTANCE":         "HIGH",
    "DUPLICATE_BDN":              "HIGH",
    "BARGE_UNVERIFIED":           "MEDIUM",
    "INVALID_TIMESTAMPS":         "MEDIUM",
    "QUANTITY_INFEASIBLE":        "MEDIUM",
    "SUSPICIOUS_CORRECTIONS":     "MEDIUM",
    "MISSING_SEAL_NUMBERS":       "LOW",
    # INFO = missing evidence, not fraud — excluded from fraud risk score
    "BARGE_AIS_MISSING":          "INFO",
    "VESSEL_AIS_MISSING":         "INFO",
    "AIS_UNAVAILABLE":            "INFO",
}


def _severities() -> dict[str, str]:
    cfg = get_config().get("fraud_detection", {})
    return {**_DEFAULT_SEVERITIES, **cfg.get("alert_severities", {})}


def _make_alert(alert_type: str, explanation: str, evidence: dict | None = None) -> dict[str, Any]:
    sevs = _severities()
    return {
        "alert_type": alert_type,
        "severity": sevs.get(alert_type, "MEDIUM"),
        "explanation": explanation,
        "evidence": evidence or {},
    }


def detect_fraud(
    *,
    credibility_flags: list[str],
    identity: dict[str, Any],
    barge: dict[str, Any],
    ais: dict[str, Any],
    extraction: dict[str, Any],
) -> dict[str, Any]:
    """
    Produce fraud_alerts[], overall_fraud_risk, requires_human_review.
    """
    alerts: list[dict[str, Any]] = []

    # ── Vessel identity ─────────────────────────────────────────────
    id_flags = identity.get("flags") or []

    if "missing_vessel_identity" in id_flags:
        alerts.append(_make_alert(
            "VESSEL_NOT_FOUND",
            "No vessel name or IMO was found on the BDN. Identity cannot be verified.",
        ))
    elif identity.get("vessel_identity_unresolved"):
        bdn_imo = identity.get("bdn_imo")
        bdn_name = identity.get("bdn_name")
        candidates = identity.get("candidates", [])
        cand_str = "; ".join(f"{c.get('name')} (IMO {c.get('imo')})" for c in candidates[:2]) if candidates else "—"
        alerts.append(_make_alert(
            "VESSEL_IDENTITY_UNRESOLVED",
            f"IMO {bdn_imo} and vessel name '{bdn_name}' resolve to different registrations. "
            f"Candidates: {cand_str}. Manual verification required.",
            evidence={"bdn_imo": bdn_imo, "bdn_name": bdn_name, "candidates": candidates},
        ))
    elif "vessel_name_mismatch" in id_flags:
        alerts.append(_make_alert(
            "IMO_MISMATCH",
            f"Vessel name on BDN ('{identity.get('bdn_name')}') does not match registry for IMO {identity.get('bdn_imo')} "
            f"('{identity.get('confirmed_name')}'). This is a severe identity conflict.",
            evidence={"bdn_name": identity.get("bdn_name"), "confirmed_name": identity.get("confirmed_name"),
                      "bdn_imo": identity.get("bdn_imo")},
        ))
    elif "vessel_name_fuzzy_match" in id_flags:
        alerts.append(_make_alert(
            "NAME_FUZZY_MATCH",
            f"Vessel name on BDN ('{identity.get('bdn_name')}') is a fuzzy match to registry "
            f"('{identity.get('confirmed_name')}', confidence {identity.get('identity_confidence', 0):.0%}). "
            "Possible OCR error or name variation.",
            evidence={"bdn_name": identity.get("bdn_name"), "confirmed_name": identity.get("confirmed_name"),
                      "match_score": identity.get("identity_confidence")},
        ))
        # Ensure NAME_FUZZY_MATCH is treated as INFO so it doesn't inflate fraud risk
        alerts[-1]["severity"] = "INFO"
    elif "vessel_not_in_registry" in id_flags:
        alerts.append(_make_alert(
            "VESSEL_NOT_FOUND",
            f"Vessel '{identity.get('bdn_name')}' (IMO: {identity.get('bdn_imo')}) was not found in Datalastic registry.",
            evidence={"bdn_name": identity.get("bdn_name"), "bdn_imo": identity.get("bdn_imo")},
        ))

    # ── Barge identity ──────────────────────────────────────────────
    barge_flags = barge.get("barge_flags") or []
    if "barge_name_missing" in barge_flags:
        alerts.append(_make_alert(
            "BARGE_UNVERIFIED",
            "No barge name was found on the BDN. Barge identity cannot be verified.",
        ))
    elif barge.get("barge_ais_missing") and barge.get("resolution_method") == "unresolved":
        alerts.append(_make_alert(
            "BARGE_UNVERIFIED",
            f"Barge '{extraction.get('barge_name')}' could not be resolved via MPA registry or Datalastic. AIS track unavailable.",
            evidence={"barge_name": extraction.get("barge_name"), "sb_number": extraction.get("barge_sb_number")},
        ))
    elif barge.get("barge_ais_missing"):
        # INFO: barge found in registry but AIS unavailable for window — missing evidence, not fraud
        alerts.append(_make_alert(
            "BARGE_AIS_MISSING",
            f"Barge '{barge.get('barge_confirmed_name')}' identified but AIS data unavailable for the delivery window. "
            "Cannot confirm physical co-location — not an anomaly flag.",
        ))

    # ── AIS / Geolocation ──────────────────────────────────
    anomaly_flags = ais.get("anomaly_flags") or []
    if ais.get("is_anomaly"):
        # Confirmed negative evidence — real fraud alert
        score = ais.get("anomaly_score", 0.5)
        alerts.append(_make_alert(
            "EXCESSIVE_DISTANCE",
            f"AIS behaviour during delivery is anomalous (ML score: {score:.2f}). "
            "Vessel and barge were not co-located at the declared port during the stated delivery window.",
            evidence={"anomaly_score": score, "feature_vector": ais.get("feature_vector")},
        ))
    elif ais.get("ais_unavailable"):
        # Missing evidence only — INFO, not a fraud signal
        alerts.append(_make_alert(
            "AIS_UNAVAILABLE",
            "AIS position data could not be retrieved for the delivery window. "
            "Geolocation verification is incomplete. This is missing evidence, not an anomaly.",
            evidence={"anomaly_flags": anomaly_flags},
        ))

    # ── Credibility flags ───────────────────────────────────────────
    if "reversed_timestamps" in credibility_flags:
        alerts.append(_make_alert(
            "INVALID_TIMESTAMPS",
            f"Delivery end time is earlier than start time. "
            f"Start: {extraction.get('start_time')}, End: {extraction.get('end_time')}.",
            evidence={"start_time": extraction.get('start_time'), "end_time": extraction.get('end_time')},
        ))

    if "quantity_physically_impossible" in credibility_flags:
        alerts.append(_make_alert(
            "QUANTITY_INFEASIBLE",
            f"Stated quantity ({extraction.get('quantity_mt')} MT) is outside physically possible pump rates "
            "for the given delivery duration.",
            evidence={"quantity_mt": extraction.get('quantity_mt')},
        ))

    if "contains_correction_keywords" in credibility_flags:
        alerts.append(_make_alert(
            "SUSPICIOUS_CORRECTIONS",
            "BDN document contains words suggesting post-hoc amendment (e.g., whiteout, correction, amended).",
        ))

    if "duplicate_bdn_detected" in credibility_flags:
        alerts.append(_make_alert(
            "DUPLICATE_BDN",
            f"A BDN for the same vessel ('{extraction.get('vessel_name')}'), port ('{extraction.get('port')}'), "
            f"and date ('{extraction.get('delivery_date')}') already exists in the system.",
        ))

    if "missing_seal_numbers" in credibility_flags:
        alerts.append(_make_alert(
            "MISSING_SEAL_NUMBERS",
            "No seal numbers (vessel, MARPOL, or barge) were found on the BDN. Seal integrity cannot be confirmed.",
        ))

    # ── Overall risk ────────────────────────────────────
    # INFO alerts (missing evidence) are excluded from risk calculation
    fraud_alerts = [a for a in alerts if a["severity"] != "INFO"]
    info_alerts  = [a for a in alerts if a["severity"] == "INFO"]

    high_count = sum(1 for a in fraud_alerts if a["severity"] == "HIGH")
    med_count  = sum(1 for a in fraud_alerts if a["severity"] == "MEDIUM")

    if high_count > 0:
        overall = "HIGH"
    elif med_count > 0:
        overall = "MEDIUM"
    elif fraud_alerts:
        overall = "LOW"
    else:
        overall = "NONE"

    requires_review = high_count > 0 or identity.get("vessel_identity_unresolved", False)

    return {
        "fraud_alerts": fraud_alerts,          # only actionable fraud signals
        "info_alerts": info_alerts,            # missing-evidence notices (yellow, not red)
        "ais_evidence_status": ais.get("status"),
        "ais_evidence_warnings": ais.get("warnings", []),
        "overall_fraud_risk": overall,
        "requires_human_review": requires_review,
    }
