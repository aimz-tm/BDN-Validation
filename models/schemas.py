from pydantic import BaseModel
from typing import Optional, List

# ── STEP 1: Document Classification ─────────────────────────────────────
class DocumentClassification(BaseModel):
    doc_type: str                    # DIGITAL / SCANNED / HANDWRITTEN
    ocr_confidence: float            # 0.0 to 1.0

# ── STEP 2: Rule Engine + MARPOL Credibility Check ──────────────────────
class DocumentCredibility(BaseModel):
    credibility_score: float         # 0 to 100
    credibility_flags: List[str]
    # Rule engine flags:
    # "low_ocr_confidence", "missing_fields", "invalid_imo_format",
    # "reversed_timestamps", "font_inconsistency",
    # "contains_correction_keywords", "suspicious_pumping_duration"
    # MARPOL flags:
    # "marpol_density_violation", "marpol_sulphur_violation",
    # "marpol_flashpoint_violation"

# ── STEP 3: Extracted BDN Fields ────────────────────────────────────────
class BDNExtraction(BaseModel):
    vessel_name: str
    imo: str
    barge_name: str
    delivery_date: str
    start_time: str
    end_time: str
    port: str
    quantity_mt: Optional[float] = None
    density: Optional[float] = None        # kg/m³
    sulphur_content: Optional[float] = None  # %
    flashpoint: Optional[float] = None     # °C
    supplier: Optional[str] = None

# ── STEP 4: AIS Geolocation Result ──────────────────────────────────────
class AISValidation(BaseModel):
    vessel_found: bool
    barge_found: bool
    avg_distance_m: Optional[float] = None
    max_distance_m: Optional[float] = None
    co_location_duration_h: Optional[float] = None
    overlap_percent: Optional[float] = None
    anchorage_match: Optional[bool] = None
    ais_gap_count: Optional[int] = None
    timezone_normalized: bool
    anomaly_flags: List[str]
    # "barge_ais_missing", "vessel_speed_too_high",
    # "ais_gap_detected", "location_mismatch"

# ── STEP 5: Final Combined Verdict ──────────────────────────────────────
class ValidationResult(BaseModel):
    transaction_id: str
    classification: str              # VALID / SUSPICIOUS / HIGH_RISK
    confidence: float                # 0.0 to 1.0
    doc_classification: DocumentClassification
    credibility: DocumentCredibility
    extraction: BDNExtraction
    ais: AISValidation
    verdict_reason: str