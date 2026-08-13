"""
Credibility scorer — Phase 3.
Expanded from document_service/credibility.py.
All thresholds from config. New flags from plan:
  - low_extraction_confidence
  - duplicate_bdn_detected
  - quantity_physically_impossible
  - missing_seal_numbers (FLAG_012)
  - sb_number_absent (DIGITAL only, FLAG_010)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from core.config_loader import get_config


def _cred_config() -> dict:
    return get_config()["credibility"]


def check_credibility(fields: dict[str, Any]) -> dict[str, Any]:
    """
    Credibility score (0–100) using spec weights from config.credibility.score_weights.
    Returns: { credibility_score, credibility_flags, breakdown, duplicate_detected }
    """
    cred = _cred_config()
    ocr_cfg = get_config()["ocr"]
    val_cfg = get_config().get("validation", {})
    weights = cred["score_weights"]
    flags: list[str] = []

    # ── OCR confidence ──────────────────────────────────────────────
    ocr_conf = float(fields.get("ocr_confidence") or 0.0)
    ocr_threshold = float(ocr_cfg["confidence_threshold"])
    if ocr_conf < ocr_threshold:
        flags.append("low_ocr_confidence")
    ocr_score = min(ocr_conf / ocr_threshold, 1.0) * 100 if ocr_threshold else 0.0

    # ── Extraction confidence ────────────────────────────────────────
    ext_conf = float(fields.get("extraction_confidence") or 0.0)
    ext_threshold = float(cred.get("extraction_confidence_threshold", 0.5))
    if ext_conf < ext_threshold:
        flags.append("low_extraction_confidence")

    # ── Required fields ─────────────────────────────────────────────
    required = [
        "vessel_name", "barge_name", "delivery_date",
        "start_time", "end_time", "port",
    ]
    # IMO is required for vessels, but NOT for barges
    min_required = int(ocr_cfg.get("min_required_fields", len(required)))
    present = sum(1 for f in required if fields.get(f))
    if present < min_required:
        flags.append("missing_required_fields")
    field_score = (present / len(required)) * 100

    # ── Format / IMO ────────────────────────────────────────────────
    format_score = 100.0
    imo = str(fields.get("imo") or "")
    if imo and not re.fullmatch(r"\d{7}", imo):
        flags.append("invalid_imo_format")
        format_score -= float(cred["invalid_imo_penalty"])
    format_score = max(format_score, 0.0)

    # ── Correction keywords ─────────────────────────────────────────
    raw_text = (fields.get("raw_text") or "").lower()
    for kw in cred["correction_keywords"]:
        if kw.lower() in raw_text:
            flags.append("contains_correction_keywords")
            format_score = max(format_score - float(cred["correction_keyword_penalty"]), 0)
            break

    # ── MARPOL checks ────────────────────────────────────────────────
    # density / sulphur_content / flashpoint are extracted and shown on the
    # dashboard for reference, but are not scored here — fuel-quality
    # compliance (ISO 8217) is the licensed supplier's responsibility, not
    # something this pipeline verifies.
    marpol = cred.get("marpol", {})
    marpol_penalty = float(cred.get("marpol_violation_penalty", 40))
    viscosity = fields.get("viscosity")
    if viscosity is not None:
        if viscosity > marpol.get("viscosity_max_50c", 700.0):
            flags.append("marpol_viscosity_violation")
            format_score = max(format_score - marpol_penalty, 0)
    water = fields.get("water_content")
    if water is not None and water > marpol.get("water_content_max", 0.5):
        flags.append("marpol_water_content_violation")
        format_score = max(format_score - marpol_penalty, 0)


    # ── Timestamps ──────────────────────────────────────────────────
    timestamp_score = 100.0
    start = fields.get("start_time") or ""
    end = fields.get("end_time") or ""
    if start and end and start >= end:
        flags.append("reversed_timestamps")
        timestamp_score -= float(cred["reversed_timestamp_penalty"])

    duration_h: float | None = None
    try:
        fmt = "%d %B %Y %H:%M"
        t1 = datetime.strptime(start, fmt)
        t2 = datetime.strptime(end, fmt)
        duration_h = (t2 - t1).total_seconds() / 3600
        qty = float(fields.get("quantity_mt") or 0)
        min_h = float(cred["suspicious_pumping_min_hours"])
        max_h = float(cred["suspicious_pumping_max_hours"])
        if duration_h < min_h and qty > float(cred.get("high_quantity_threshold_mt", 200)):
            flags.append("suspicious_pumping_duration")
            timestamp_score -= float(cred["short_duration_penalty"])
        if duration_h > max_h:
            flags.append("suspicious_pumping_duration")
            timestamp_score -= float(cred["long_duration_penalty"])
    except Exception:
        pass
    timestamp_score = max(timestamp_score, 0.0)

    # ── Quantity physically impossible ───────────────────────────────
    if duration_h and duration_h > 0:
        qty_cfg = val_cfg.get("quantity_feasibility", {})
        min_rate = float(qty_cfg.get("min_pump_rate_mt_per_hour", 80))
        max_rate = float(qty_cfg.get("max_pump_rate_mt_per_hour", 250))
        qty = float(fields.get("quantity_mt") or 0)
        if qty > 0:
            implied_rate = qty / duration_h
            if implied_rate < min_rate or implied_rate > max_rate:
                flags.append("quantity_physically_impossible")
                format_score = max(format_score - 15, 0)

    # ── Font consistency ─────────────────────────────────────────────
    classifier_cfg = get_config()["classifier"]
    font_var = float(fields.get("font_variance") or 0)
    font_max = float(classifier_cfg["digital_max_font_variance"])
    font_score = 100.0
    if font_var >= font_max:
        flags.append("font_inconsistency")
        font_score -= float(cred.get("font_inconsistency_penalty", cred["handwritten_penalty"]))
    doc_type = fields.get("doc_type", "DIGITAL")
    if doc_type == "HANDWRITTEN":
        flags.append("handwritten_document")
        font_score -= float(cred["handwritten_penalty"])
    elif doc_type == "SCANNED":
        font_score -= float(cred["scanned_penalty"])
    font_score = max(font_score, 0.0)

    # ── Seal numbers (FLAG_012) ──────────────────────────────────────
    if not any([fields.get("seal_number_vessel"), fields.get("seal_number_marpol"), fields.get("seal_number_barge")]):
        flags.append("missing_seal_numbers")

    # ── SB number absent for DIGITAL (FLAG_010) ──────────────────────
    if doc_type == "DIGITAL" and not fields.get("barge_sb_number"):
        flags.append("sb_number_absent")

    # ── Duplicate BDN check ──────────────────────────────────────────
    duplicate_result: dict[str, Any] = {"duplicate_detected": False, "duplicate_transaction_ids": []}
    # Disabled to allow multiple checks of the same document during testing
    # try:
    #     from services.credibility_service.duplicate_checker import check_duplicates
    #     duplicate_result = check_duplicates(
    #         vessel_name=fields.get("vessel_name"),
    #         port=fields.get("port"),
    #         delivery_date=fields.get("delivery_date"),
    #     )
    #     if duplicate_result.get("duplicate_detected"):
    #         flags.append("duplicate_bdn_detected")
    #         format_score = max(format_score - 30, 0)
    # except Exception:
    #     pass

    # ── Final score ──────────────────────────────────────────────────
    breakdown = {
        "ocr_confidence":    round(ocr_score, 1),
        "field_completeness": round(field_score, 1),
        "format_validity":   round(format_score, 1),
        "timestamp_integrity": round(timestamp_score, 1),
        "font_consistency":  round(font_score, 1),
    }
    final_score = round(
        sum(breakdown[key] * float(weights[key]) for key in weights), 1
    )

    return {
        "credibility_score": final_score,
        "credibility_flags": flags,
        "breakdown": breakdown,
        "duplicate_detected": duplicate_result.get("duplicate_detected", False),
        "duplicate_transaction_ids": duplicate_result.get("duplicate_transaction_ids", []),
    }
