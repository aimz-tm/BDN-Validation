"""
Build operator-facing validation logistics — what checked out and what did not.
"""

from __future__ import annotations

from typing import Any

from core.config_loader import get_config


def _status(ok: bool | None) -> str:
    if ok is True:
        return "correct"
    if ok is False:
        return "incorrect"
    return "unknown"


def build_validation_logistics(verdict: dict[str, Any]) -> list[dict[str, Any]]:
    config = get_config()
    ocr_threshold = config["ocr"]["confidence_threshold"]
    identity_fuzzy = config["identity"]["fuzzy_match_threshold"]

    ext = verdict.get("extraction") or {}
    identity = verdict.get("identity_resolution") or {}
    evidence = verdict.get("evidence") or {}
    credibility_flags = set(verdict.get("credibility_flags") or [])
    anomaly_flags = set(verdict.get("anomaly_flags") or [])

    ocr_conf = ext.get("ocr_confidence") or evidence.get("ocr_confidence") or 0
    cred_score = evidence.get("credibility_score")

    logistics: list[dict[str, Any]] = []

    # ── Document extraction ───────────────────────────────────────────
    required = [
        ("vessel_name", "Vessel name on BDN"),
        ("imo", "IMO number"),
        ("barge_name", "Barge name"),
        ("delivery_date", "Delivery date"),
        ("start_time", "Pumping start time"),
        ("end_time", "Pumping end time"),
        ("port", "Port of delivery"),
    ]
    for key, label in required:
        val = ext.get(key)
        logistics.append(
            {
                "category": "Document",
                "check": label,
                "status": _status(bool(val)),
                "detail": f"Extracted: {val}" if val else "Could not extract from document",
            }
        )

    logistics.append(
        {
            "category": "Document",
            "check": "OCR readability",
            "status": _status(ocr_conf >= ocr_threshold and "low_ocr_confidence" not in credibility_flags),
            "detail": f"OCR confidence {ocr_conf:.0%} (threshold {ocr_threshold:.0%})",
        }
    )

    if cred_score is not None:
        logistics.append(
            {
                "category": "Document",
                "check": "Document credibility score",
                "status": _status(cred_score >= 70 and not credibility_flags),
                "detail": f"Score {cred_score}/100"
                + (f"; flags: {', '.join(sorted(credibility_flags))}" if credibility_flags else ""),
            }
        )

    qty = ext.get("quantity_mt")
    if qty is not None:
        qf = evidence.get("quantity_feasible")
        if qf is True:
            qty_detail = f"{qty} MT — within feasible pump rate for stated duration"
        elif qf is False:
            qty_detail = f"{qty} MT — not feasible for stated duration"
        else:
            qty_detail = f"{qty} MT — feasibility not verified"
        logistics.append(
            {
                "category": "Document",
                "check": "Delivered quantity (MT)",
                "status": _status("quantity_infeasible" not in anomaly_flags),
                "detail": qty_detail,
            }
        )

    highlights = (verdict.get("document") or {}).get("field_highlights") or verdict.get("field_highlights")
    if highlights and highlights.get("highlights"):
        found = sum(1 for h in highlights["highlights"] if h.get("found_on_document"))
        total = len(highlights["highlights"])
        logistics.append(
            {
                "category": "Document",
                "check": "Fields located on scanned image",
                "status": _status(found >= total - 2),
                "detail": f"{found} of {total} extracted fields highlighted on document",
            }
        )

    # ── Vessel identity ───────────────────────────────────────────────
    unresolved = identity.get("vessel_identity_unresolved") or "vessel_identity_unresolved" in anomaly_flags
    logistics.append(
        {
            "category": "Identity",
            "check": "IMO matches registered vessel name",
            "status": _status(not unresolved),
            "detail": (
                f"BDN '{identity.get('bdn_name')}' / IMO {identity.get('bdn_imo')} → "
                f"confirmed '{identity.get('confirmed_name')}' / IMO {identity.get('confirmed_imo')}"
                if not unresolved
                else "IMO and name resolve to different vessels — human review required"
            ),
        }
    )

    id_conf = identity.get("identity_confidence")
    if id_conf is not None:
        logistics.append(
            {
                "category": "Identity",
                "check": "Identity confidence",
                "status": _status(id_conf >= identity_fuzzy and not unresolved),
                "detail": f"{id_conf:.0%} via {identity.get('resolution_method', 'unknown')}",
            }
        )

    # ── AIS / geolocation ───────────────────────────────────────────────
    if evidence.get("ais_unavailable"):
        logistics.append(
            {
                "category": "AIS",
                "check": "AIS telemetry available",
                "status": "incorrect",
                "detail": "Datalastic AIS could not be retrieved for this delivery window",
            }
        )
    else:
        logistics.append(
            {
                "category": "AIS",
                "check": "Vessel AIS during delivery window",
                "status": _status("vessel_speed_anomaly" not in anomaly_flags),
                "detail": "Vessel track present"
                if evidence.get("ais_anomaly_detected") is False
                else "Speed or movement anomaly during bunkering"
                if "vessel_speed_anomaly" in anomaly_flags
                else "AIS reviewed",
            }
        )

        logistics.append(
            {
                "category": "AIS",
                "check": "Barge co-location",
                "status": _status(
                    "barge_ais_missing" not in anomaly_flags
                    and evidence.get("overlap_percent", 0) >= config["validation"]["min_overlap_percent"]
                ),
                "detail": (
                    "Barge AIS missing — cannot confirm alongside delivery"
                    if "barge_ais_missing" in anomaly_flags
                    else f"{evidence.get('overlap_percent', '—')}% overlap, "
                    f"avg distance {evidence.get('avg_distance_m', '—')} m, "
                    f"{evidence.get('co_location_duration_h', '—')} h co-located"
                ),
            }
        )

        logistics.append(
            {
                "category": "AIS",
                "check": "Position vs declared port",
                "status": _status(evidence.get("port_coordinate_match") is True),
                "detail": "AIS centroid matches declared port"
                if evidence.get("port_coordinate_match")
                else "Port coordinate mismatch or not verified",
            }
        )

        if evidence.get("ais_anomaly_score") is not None:
            logistics.append(
                {
                    "category": "AIS",
                    "check": "ML anomaly score (Isolation Forest)",
                    "status": _status(not evidence.get("ais_anomaly_detected")),
                    "detail": f"Score {evidence.get('ais_anomaly_score'):.2f} — "
                    + ("normal pattern" if not evidence.get("ais_anomaly_detected") else "anomalous pattern"),
                }
            )

    if evidence.get("timezone_normalized"):
        logistics.append(
            {
                "category": "AIS",
                "check": "Delivery times (timezone)",
                "status": "correct",
                "detail": "BDN local times normalized to UTC for AIS window",
            }
        )

    return logistics
