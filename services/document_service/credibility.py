import re
import yaml

# Load config once at module level
with open("config/config.yaml", "r") as f:
    CONFIG = yaml.safe_load(f)

MARPOL   = CONFIG["marpol"]
SCORING  = CONFIG["scoring"]
OCR_THRESHOLD = CONFIG["ocr"]["confidence_threshold"]


def check_credibility(fields: dict) -> dict:
    """
    Run all credibility checks on extracted BDN fields.
    Returns credibility_score (0-100) and credibility_flags[].

    Scoring weights (from config):
      document_integrity : 40%  — OCR quality, doc type
      data_anomalies     : 35%  — field logic, plausibility
      compliance_gaps    : 25%  — MARPOL, missing fields
    """
    flags = []

    # ── DOCUMENT INTEGRITY (40%) ─────────────────────────────────────
    integrity_score = 100.0

    # OCR confidence
    ocr_conf = fields.get("ocr_confidence", 0.0)
    if ocr_conf < OCR_THRESHOLD:
        flags.append("low_ocr_confidence")
        integrity_score -= 30

    # Font/scan consistency — penalise SCANNED and HANDWRITTEN
    doc_type = fields.get("doc_type", "DIGITAL")
    if doc_type == "HANDWRITTEN":
        flags.append("handwritten_document")
        integrity_score -= 25
    elif doc_type == "SCANNED":
        integrity_score -= 5  # small penalty, not flagged

    integrity_score = max(integrity_score, 0)

    # ── DATA ANOMALIES (35%) ─────────────────────────────────────────
    anomaly_score = 100.0

    # Required fields present
    required = [
        "vessel_name", "imo", "barge_name",
        "delivery_date", "start_time", "end_time", "port"
    ]
    missing = [f for f in required if not fields.get(f)]
    if missing:
        flags.append("missing_fields")
        anomaly_score -= (len(missing) * 12)

    # IMO format — must be exactly 7 digits
    imo = fields.get("imo", "")
    if not re.fullmatch(r"\d{7}", str(imo)):
        flags.append("invalid_imo_format")
        anomaly_score -= 20

    # Timestamp logic — end must be after start
    start = fields.get("start_time", "")
    end   = fields.get("end_time", "")
    if start and end and start >= end:
        flags.append("reversed_timestamps")
        anomaly_score -= 25

    # Pumping duration plausibility
    # 500 MT takes minimum ~2 hours — flag if <1hr or >24hrs
    try:
        from datetime import datetime
        fmt = "%d %B %Y %H:%M"
        t1 = datetime.strptime(start, fmt)
        t2 = datetime.strptime(end, fmt)
        duration_h = (t2 - t1).seconds / 3600
        qty = fields.get("quantity_mt") or 0
        if duration_h < 1 and qty > 200:
            flags.append("suspicious_pumping_duration")
            anomaly_score -= 20
        if duration_h > 24:
            flags.append("suspicious_pumping_duration")
            anomaly_score -= 15
    except:
        pass  # timestamp parse failed — already caught above

    # Correction keywords in raw text
    raw_text = fields.get("raw_text", "")
    correction_keywords = [
        "corrected", "amended", "revised",
        "whiteout", "overwritten", "cancelled"
    ]
    if any(kw in raw_text.lower() for kw in correction_keywords):
        flags.append("contains_correction_keywords")
        anomaly_score -= 20

    anomaly_score = max(anomaly_score, 0)

    # ── COMPLIANCE GAPS (25%) ────────────────────────────────────────
    compliance_score = 100.0

    # MARPOL density check
    density = fields.get("density")
    if density is not None:
        if not (MARPOL["density_min"] <= density <= MARPOL["density_max"]):
            flags.append("marpol_density_violation")
            compliance_score -= 40

    # MARPOL sulphur check
    sulphur = fields.get("sulphur_content")
    if sulphur is not None:
        if sulphur > MARPOL["sulphur_max"]:
            flags.append("marpol_sulphur_violation")
            compliance_score -= 40

    # MARPOL flashpoint check
    flashpoint = fields.get("flashpoint")
    if flashpoint is not None:
        if flashpoint < MARPOL["flashpoint_min"]:
            flags.append("marpol_flashpoint_violation")
            compliance_score -= 40

    # Missing MARPOL fields — present on BDN but not extracted
    marpol_fields = ["density", "sulphur_content", "flashpoint"]
    missing_marpol = [f for f in marpol_fields if fields.get(f) is None]
    if missing_marpol:
        flags.append("missing_marpol_fields")
        compliance_score -= (len(missing_marpol) * 10)

    compliance_score = max(compliance_score, 0)

    # ── WEIGHTED FINAL SCORE ─────────────────────────────────────────
    weights = SCORING["weights"]
    final_score = round(
        (integrity_score   * weights["document_integrity"]) +
        (anomaly_score     * weights["data_anomalies"])     +
        (compliance_score  * weights["compliance_gaps"]),
        1
    )

    return {
        "credibility_score": final_score,
        "credibility_flags": flags,
        "breakdown": {
            "document_integrity": round(integrity_score, 1),
            "data_anomalies":     round(anomaly_score, 1),
            "compliance_gaps":    round(compliance_score, 1)
        }
    }