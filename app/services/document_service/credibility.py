import re
from datetime import datetime

from app.core.config_loader import get_config


def _cred_config() -> dict:
    return get_config()["credibility"]


def check_credibility(fields: dict) -> dict:
    """
    Credibility score (0–100) using spec weights from config.credibility.score_weights.
    """
    cred = _cred_config()
    ocr_cfg = get_config()["ocr"]
    weights = cred["score_weights"]
    flags: list[str] = []

    ocr_conf = float(fields.get("ocr_confidence") or 0.0)
    ocr_threshold = float(ocr_cfg["confidence_threshold"])
    if ocr_conf < ocr_threshold:
        flags.append("low_ocr_confidence")
    ocr_score = min(ocr_conf / ocr_threshold, 1.0) * 100 if ocr_threshold else 0.0

    required = [
        "vessel_name",
        "imo",
        "barge_name",
        "delivery_date",
        "start_time",
        "end_time",
        "port",
    ]
    min_required = int(ocr_cfg.get("min_required_fields", len(required)))
    present = sum(1 for f in required if fields.get(f))
    if present < min_required:
        flags.append("missing_required_fields")
    field_score = (present / len(required)) * 100

    format_score = 100.0
    imo = str(fields.get("imo") or "")
    if not re.fullmatch(r"\d{7}", imo):
        flags.append("invalid_imo_format")
        format_score -= float(cred["invalid_imo_penalty"])

    format_score = max(format_score, 0.0)

    timestamp_score = 100.0
    start = fields.get("start_time") or ""
    end = fields.get("end_time") or ""
    if start and end and start >= end:
        flags.append("reversed_timestamps")
        timestamp_score -= float(cred["reversed_timestamp_penalty"])

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

    raw_text = (fields.get("raw_text") or "").lower()
    for kw in cred["correction_keywords"]:
        if kw in raw_text:
            flags.append("contains_correction_keywords")
            format_score = max(format_score - float(cred["correction_keyword_penalty"]), 0)
            break

    marpol = cred.get("marpol", {})
    marpol_penalty = float(cred.get("marpol_violation_penalty", 40))
    density = fields.get("density")
    if density is not None and not (marpol["density_min"] <= density <= marpol["density_max"]):
        flags.append("marpol_density_violation")
        format_score = max(format_score - marpol_penalty, 0)

    sulphur = fields.get("sulphur_content")
    if sulphur is not None and sulphur > marpol.get("sulphur_max", 0.5):
        flags.append("marpol_sulphur_violation")
        format_score = max(format_score - marpol_penalty, 0)

    flashpoint = fields.get("flashpoint")
    if flashpoint is not None and flashpoint < marpol.get("flashpoint_min", 60):
        flags.append("marpol_flashpoint_violation")
        format_score = max(format_score - marpol_penalty, 0)
    viscosity = fields.get("viscosity")
    if viscosity is not None and viscosity > marpol.get("viscosity_max_50c", 700.0):
        flags.append("marpol_viscosity_violation")
        format_score = max(format_score - marpol_penalty, 0)
    water = fields.get("water_content")
    if water is not None and water > marpol.get("water_content_max", 0.5):
        flags.append("marpol_water_content_violation")
        format_score = max(format_score - marpol_penalty, 0)

    breakdown = {
        "ocr_confidence": round(ocr_score, 1),
        "field_completeness": round(field_score, 1),
        "format_validity": round(format_score, 1),
        "timestamp_integrity": round(timestamp_score, 1),
        "font_consistency": round(font_score, 1),
    }

    final_score = round(
        sum(breakdown[key] * float(weights[key]) for key in weights),
        1,
    )

    return {
        "credibility_score": final_score,
        "credibility_flags": flags,
        "breakdown": breakdown,
    }
