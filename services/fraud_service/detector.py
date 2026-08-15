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
    # Barge-specific alerts — distinct types for distinct failure modes
    # BARGE_MISSING = barge name absent from BDN, or present but unmatched in any
    # registry — unavailable data (often an OCR misread), not fraud evidence, so
    # it drives SUSPICIOUS rather than HIGH_RISK (see scoring_service/scorer.py).
    "BARGE_MISSING":              "MEDIUM",
    "BARGE_NAME_MISMATCH":        "MEDIUM",  # SB# found but registered name conflicts
    "BARGE_UNVERIFIED":           "MEDIUM",  # resolved with low confidence
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
    # Each flag maps to a distinct alert type so operators can immediately
    # tell whether the barge is simply unresolved (BARGE_MISSING — unavailable
    # data), name-conflicting, or resolved with low confidence — rather than
    # everything showing as BARGE_UNVERIFIED.
    barge_flags = barge.get("barge_flags") or []
    bdn_barge_name = extraction.get("barge_name")
    sb_number = extraction.get("barge_sb_number")

    if "barge_name_missing" in barge_flags:
        # No barge name field on the BDN at all — unavailable data, not a fraud
        # signal: treated the same as barge_not_found below (see BARGE_MISSING).
        alerts.append(_make_alert(
            "BARGE_MISSING",
            "No barge name was found on the BDN. The delivering vessel cannot be identified.",
            evidence={"barge_name": bdn_barge_name, "sb_number": sb_number},
        ))
    elif "barge_not_found" in barge_flags:
        # Name present on BDN but unmatched across all registries (MPA, Datalastic,
        # inradius). In practice this is usually an OCR misread of the barge name
        # rather than evidence of a fabricated delivery, so it's treated the same
        # as barge_name_missing: unavailable data (BARGE_MISSING), not a HIGH-severity
        # fraud signal like a genuine identity conflict (BARGE_NAME_MISMATCH below).
        alerts.append(_make_alert(
            "BARGE_MISSING",
            f"Barge '{bdn_barge_name}' was not found in the MPA registry or vessel databases. "
            "The delivering vessel cannot be confirmed.",
            evidence={"barge_name": bdn_barge_name, "sb_number": sb_number},
        ))
    elif "barge_name_mismatch" in barge_flags:
        # SB number resolves in registry but name on BDN conflicts with the registered name
        registry_name = barge.get("barge_confirmed_name")
        alerts.append(_make_alert(
            "BARGE_NAME_MISMATCH",
            f"SB number '{sb_number}' matches a registry record but the name on the BDN "
            f"('{bdn_barge_name}') conflicts with the registered name ('{registry_name}'). "
            "Possible vessel substitution or documentation error.",
            evidence={
                "bdn_barge_name": bdn_barge_name,
                "registry_name": registry_name,
                "sb_number": sb_number,
                "match_score": barge.get("resolution_evidence", {}).get("match_score"),
            },
        ))
    elif "barge_low_confidence" in barge_flags:
        # Resolved but fuzzy match score was borderline — treat as unverified
        conf = barge.get("barge_confidence", 0)
        alerts.append(_make_alert(
            "BARGE_UNVERIFIED",
            f"Barge '{bdn_barge_name}' was matched with low confidence ({conf:.0%}). "
            "The registry match may be a different vessel with a similar name.",
            evidence={"barge_name": bdn_barge_name, "confidence": conf},
        ))
    elif barge.get("barge_ais_missing"):
        # Barge positively identified in registry but no AIS track for the delivery window
        # — missing evidence, not a fraud signal in itself
        alerts.append(_make_alert(
            "BARGE_AIS_MISSING",
            f"Barge '{barge.get('barge_confirmed_name') or bdn_barge_name}' was identified in the registry "
            "but no AIS track is available for the delivery window. Physical co-location cannot be confirmed.",
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
