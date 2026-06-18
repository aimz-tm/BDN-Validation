# 129Knots — Implementation Plan
## New Prompt Integration (Conflict-Free)

Last Updated: 4 June 2026

---

## WHAT THE NEW PROMPT ADDS (that doesn't conflict)

These are the net-new requirements from the mentor's prompt that we
are implementing ON TOP of v3 architecture without touching:
- FLAG_005 (Isolation Forest ML — not Haversine verdict)
- FLAG_007 (DIGITAL/HANDWRITTEN — not three modes as separate services)
- Verdict terminology: VALID/SUSPICIOUS/HIGH_RISK (not APPROVED/REJECTED)
- Port coordinates from lookup table not OCR

---

## PHASE 0 — FOUNDATION (Do today, everything depends on this)

### 0A. config/settings.py  [CREATE]
Single source of truth for all config at runtime.
Loads config.yaml + injects secrets from .env.

```python
# config/settings.py
import os
import yaml
from dotenv import load_dotenv

load_dotenv()

def load_config() -> dict:
    with open("config/config.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["api"]["datalastic"]["api_key"] = os.getenv("DATALASTIC_API_KEY")
    cfg["database_url"] = os.getenv("DATABASE_URL")
    return cfg

config = load_config()
```

Every service imports: `from config.settings import config`
No service reads .env or yaml directly.

### 0B. config/config.yaml  [UPDATE to v3 full structure]
Use the complete config.yaml from master notes v3.
Add these new sections from the new prompt:

```yaml
confidence_scoring:
  weights:
    ocr: 0.20
    extraction: 0.20
    vessel_verification: 0.20
    barge_verification: 0.15
    geolocation: 0.25
  thresholds:
    valid: 75
    review_required: 50
    suspicious: 30

fraud_detection:
  duplicate_bdn_window_days: 90
  max_reuse_count: 1
  suspicious_correction_keywords:
    - "whiteout"
    - "correction"
    - "amended"
    - "revised"
    - "crossed out"

reporting:
  include_audit_trail: true
  audit_trail_max_entries: 50
```

### 0C. stub/mock_pipeline.py  [CREATE]
Wire the full stack before any real module exists.
POST /validate → runs stub → dashboard renders verdict.
Replace each stub section with real module as it is built.

---

## PHASE 1 — OCR SERVICE  [services/ocr_service/]

New prompt requires OCR as an independent modular service.
Currently OCR is inside document_service/. Split it out.

### Files to create:

**services/ocr_service/__init__.py**

**services/ocr_service/preprocessor.py**
- OpenCV pipeline: grayscale, denoise, deskew, threshold, contrast enhance
- Two preprocess modes driven by doc_type from classifier:
  - preprocess_digital(image): minimal processing, preserve text
  - preprocess_handwritten(image): full pipeline, denoising priority
- All parameters (kernel sizes, thresholds) from config.yaml

**services/ocr_service/engine.py**
- Tesseract wrapper
- Returns: { text, word_confidences[], mean_confidence, raw_data }
- Handles both image and PDF input
- PDF: extract text layer first (pdfplumber), fall back to Tesseract if no layer

**services/ocr_service/classifier.py**  ← MOVED from document_service
- DIGITAL: PDF with text layer (>50 chars extractable)
- HANDWRITTEN: everything else
- Uses OCR confidence variance to confirm classification
- Returns: { doc_type, confidence, variance }
- All thresholds from config.yaml

**New API endpoint:**
POST /ocr/extract
- Input: file upload
- Output: { doc_type, doc_type_confidence, text, ocr_confidence,
            word_confidences, processing_mode }

---

## PHASE 2 — EXTRACTION SERVICE  [services/extraction_service/]

New prompt: "Semantic field mapping, NLP-based entity extraction,
fuzzy matching, alias handling."
Currently in document_service/extractor.py — refactor into own service.

### Files to create:

**services/extraction_service/__init__.py**

**services/extraction_service/base_extractor.py**
- Abstract base class with shared find(), find_fuzzy(), find_number() methods
- Reads all synonyms from config.yaml field_synonyms
- No synonym lists in code

**services/extraction_service/digital_extractor.py**
- Extends BaseExtractor
- High fuzzy threshold (from config)
- ISO timestamp formats
- Expects explicit SB number
- Font consistency check possible

**services/extraction_service/handwritten_extractor.py**
- Extends BaseExtractor
- Lower fuzzy threshold (from config)
- Anchor-date inheritance for timestamps (FLAG_009)
- Time-no-colon pattern (0150, 0805)
- SB number optional (FLAG_010)

**services/extraction_service/normalizer.py**  ← NEW from new prompt
Normalizes all extracted values to standard formats:
- Timestamps: "1430", "14:30", "2:30 PM", "1430 HRS" → "14:30"
  All formats defined in config.yaml extraction.timestamp_formats
- Quantity: "1,175.25 MT", "1175.25", "1175" → 1175.25 (float)
- IMO: strip non-digits, validate 7-digit format
- Port: strip extra whitespace, title case

**services/extraction_service/extractor.py**
- Routes to DigitalExtractor or HandwrittenExtractor based on doc_type
- Runs normalizer on all output fields
- Returns full extracted fields dict including:
  vessel_name, imo, barge_name, barge_sb_number,
  alongside_vessel, start_time, end_time, port,
  supplier, quantity_mt, density, sulphur_content,
  flashpoint, gross_observed_volume, gross_standard_volume,
  seal_number_vessel, seal_number_marpol, seal_number_barge,
  fuel_type, remarks,
  ocr_confidence, extraction_confidence, doc_type, anchor_date_used

extraction_confidence = (fields_found / fields_expected) × mean_field_fuzzy_score

**New API endpoint:**
POST /extraction/extract
- Input: file upload
- Output: all extracted fields + extraction_confidence + doc_type

---

## PHASE 3 — CREDIBILITY SERVICE  [services/credibility_service/]

New prompt: fraud & consistency checks. Expand credibility into its own service.
Currently in document_service/credibility.py.

### Files:

**services/credibility_service/__init__.py**

**services/credibility_service/scorer.py**
Flags (all thresholds from config):
  - low_ocr_confidence
  - low_extraction_confidence       ← NEW from new prompt
  - missing_required_fields
  - invalid_imo_format
  - reversed_timestamps
  - suspicious_pumping_duration
  - font_inconsistency              (DIGITAL only)
  - contains_correction_keywords
  - missing_seal_numbers            (FLAG_012)
  - sb_number_absent                (DIGITAL only, FLAG_010)
  - duplicate_bdn_detected          ← NEW from new prompt
  - quantity_physically_impossible  ← NEW (pump rate bounds from config)

**services/credibility_service/duplicate_checker.py**  ← NEW
- Checks transactions table for same vessel + port + date combination
- Checks for reused BDN reference numbers
- Window and max reuse count from config
- Zero API cost — reads local DB only

Returns: { credibility_score, credibility_flags[], duplicate_detected,
           duplicate_transaction_ids[] }

---

## PHASE 4 — VESSEL VERIFICATION SERVICE  [services/vessel_verification_service/]

New prompt: modular vessel verification service.
Currently in identity_service/resolver.py — rename and expand.

### Files:

**services/vessel_verification_service/__init__.py**

**services/vessel_verification_service/resolver.py**
Same 5-step logic from FLAG_006.
Step A: Datalastic /vessel by IMO
Step B: rapidfuzz similarity
Step C: sentence-transformers embedding
Step D: reverse name lookup
Step E: conflict → HIGH_RISK

New additions from new prompt:
- Store verification evidence in output (what API returned, what matched)
- Flag: vessel_type_mismatch (BDN says tanker, Datalastic says cargo)
- Flag: vessel_flag_state_mismatch (optional cross-check)

Returns: {
  confirmed_imo, confirmed_mmsi, confirmed_name,
  registered_flag, vessel_type,
  resolution_method, identity_confidence,
  verification_evidence: { api_response, match_score, method_used },
  flags[]
}

**services/vessel_verification_service/datalastic_client.py**  ← NEW, shared
Centralised Datalastic API client used by ALL services.
All endpoints, timeouts, retry logic, rate limiting in one place.
API key injected from config (never hardcoded).
Graceful failure: returns None + logs error, never raises to caller.

```python
class DatalasticClient:
    def get_vessel_by_imo(self, imo: str) -> dict | None
    def find_vessel_by_name(self, name: str, type_specific: str = None) -> list | None
    def get_vessel_history(self, mmsi: str, date_from: str, date_to: str) -> list | None
    def get_vessels_in_radius(self, lat, lon, radius_km, type_specific=None, time=None) -> list | None
```

**New API endpoint:**
POST /verify/vessel
- Input: { imo, vessel_name }
- Output: full verification result + evidence

---

## PHASE 5 — BARGE VERIFICATION SERVICE  [services/barge_verification_service/]

New prompt: confidence-based barge verification using name, SB, aliases,
historical transactions. Currently in identity_service/barge_resolver.py.

### Files:

**services/barge_verification_service/__init__.py**

**services/barge_verification_service/resolver.py**
Full resolution chain from FLAG_010 + FLAG_011 + new additions:

Step 0: Historical transaction match (DB lookup, zero API cost)  ← NEW
Step 1: SB + name cross-validation (MPA registry)
Step 2: Datalastic /vessel_find + type filter
Step 3: /vessel_inradius fallback
Step 4: Unresolved → barge_ais_missing: true (FLAG_002)

Alias matching — new from prompt:
"MARINE STAR", "M STAR", "MARINESTAR" should match.
After fuzzy matching, run token-based normalization:
  - Remove common prefixes: "MT ", "MV ", "M/V ", "M/T "
  - Remove spaces and hyphens
  - Compare normalized forms
  - All normalization rules in config.yaml

Returns: {
  barge_confirmed_name, barge_mmsi, barge_imo,
  resolution_method, barge_confidence,
  barge_flags[], barge_ais_missing,
  resolution_evidence: { source, match_score }
}

**services/barge_verification_service/mpa_registry.py**
Local MPA registry loader + fuzzy searcher.
Reads data/mpa_barge_registry.json.
Path configurable in config.yaml.

**New API endpoint:**
POST /verify/barge
- Input: { barge_name, sb_number (optional), vessel_lat, vessel_lon,
           delivery_start, delivery_end }
- Output: full barge verification result

---

## PHASE 6 — LOCATION VERIFICATION SERVICE  [services/location_service/]

New prompt: geolocation validation as independent service.
Currently in validation_service/. Keep Isolation Forest (FLAG_005).
Do NOT add hardcoded distance verdict.

### Files:

**services/location_service/__init__.py**

**services/location_service/ais_fetcher.py**
Moved from ais_service/history.py.
Fetches vessel + barge AIS tracks via DatalasticClient.
Handles missing barge gracefully (FLAG_002).
Caches results in memory per session.

**services/location_service/timezone_converter.py**
Moved from timezone_service/converter.py.
Port name → UTC offset (pytz).
Port timezone map in config.yaml.

**services/location_service/feature_builder.py**
Moved from validation_service/features.py.
Builds 7-feature vector for Isolation Forest:
  1. mean vessel-barge distance (Haversine used here as INPUT FEATURE only)
  2. variance of vessel-barge distance
  3. vessel speed mean during window
  4. vessel speed variance during window
  5. heading correlation vessel vs barge
  6. co-location duration ratio
  7. port coordinate match distance (km)
  + quantity feasibility score (not a position feature, passed separately)

**services/location_service/ml_scorer.py**
Moved from validation_service/model.py.
Loads models_ml/isolation_forest.pkl.
All hyperparameters from config.yaml.
Returns: { anomaly_score, is_anomaly, feature_vector, anomaly_flags[] }

Display output (for dashboard) from new prompt:
  vessel_lat, vessel_lon (centroid during window)
  barge_lat, barge_lon (centroid during window)
  distance_m (mean)
  timestamp_range

**New API endpoint:**
POST /verify/geolocation
- Input: { confirmed_mmsi, barge_mmsi, start_time_utc, end_time_utc, port,
           quantity_mt }
- Output: { anomaly_score, is_anomaly, anomaly_flags,
            vessel_position, barge_position, distance_m,
            geolocation_confidence }

---

## PHASE 7 — FRAUD DETECTION SERVICE  [services/fraud_service/]

New addition from new prompt. Aggregates all flags into fraud alerts.
Takes outputs from all verification services and produces
human-readable explainable fraud alerts.

### Files:

**services/fraud_service/__init__.py**

**services/fraud_service/detector.py**
Input: all flags from credibility, vessel, barge, location services
Output: {
  fraud_alerts[]: [
    {
      alert_type: "IMO_MISMATCH",
      severity: "HIGH",           ← HIGH / MEDIUM / LOW from config
      explanation: "IMO 9876543 on BDN resolves to vessel STAR PHOENIX,
                    but BDN states OCEAN QUEEN. Identity unverified.",
      evidence: { bdn_value, verified_value, match_score }
    }
  ],
  overall_fraud_risk: "HIGH" / "MEDIUM" / "LOW",
  requires_human_review: bool
}

Alert types (all severities configurable):
  VESSEL_NOT_FOUND            ← HIGH
  IMO_MISMATCH                ← HIGH
  VESSEL_IDENTITY_UNRESOLVED  ← HIGH
  BARGE_IDENTITY_CONFLICT     ← HIGH
  BARGE_UNVERIFIED            ← MEDIUM
  EXCESSIVE_DISTANCE          ← HIGH  (from ML model output)
  INVALID_TIMESTAMPS          ← MEDIUM
  DUPLICATE_BDN               ← HIGH
  QUANTITY_INFEASIBLE         ← MEDIUM
  SUSPICIOUS_CORRECTIONS      ← MEDIUM
  MISSING_SEAL_NUMBERS        ← LOW
  BARGE_AIS_MISSING           ← LOW

---

## PHASE 8 — SCORING SERVICE  [services/scoring_service/]

New prompt: 6-dimensional confidence scoring.
Currently in validation_service/scoring.py.

### Scoring dimensions (all weights from config):

```
ocr_confidence          = from OCR service (0–100)
extraction_confidence   = from extraction service (0–100)
vessel_confidence       = from vessel verification (0–100)
barge_confidence        = from barge verification (0–100)
geolocation_confidence  = (1 - anomaly_score) × 100
overall_confidence      = weighted average of all above
```

### Final classification (terminology unchanged — FLAG):
  VALID         when overall_confidence ≥ valid_threshold
  SUSPICIOUS    when suspicious_threshold ≤ overall < valid_threshold
  HIGH_RISK     when overall < suspicious_threshold OR any HIGH fraud alert

### Audit trail (new from prompt):
Every decision logged as an entry:
```json
{
  "audit_trail": [
    {
      "step": "OCR",
      "result": "confidence 0.94",
      "threshold": "0.85",
      "passed": true
    },
    {
      "step": "VESSEL_IDENTITY",
      "result": "embedding match 0.84",
      "threshold": "0.72",
      "passed": true,
      "method": "sentence-transformers"
    },
    {
      "step": "BARGE_IDENTITY",
      "result": "registry name match 0.91",
      "threshold": "0.80",
      "passed": true
    },
    {
      "step": "GEOLOCATION_ML",
      "result": "anomaly_score 0.12",
      "threshold": "0.55",
      "passed": true,
      "model": "IsolationForest"
    }
  ]
}
```
Max entries from config. Step names and thresholds auto-populated from config.

---

## PHASE 9 — REPORT SERVICE  [services/report_service/]

New from prompt. Generates the full verification report object
that the dashboard and API both consume.

**services/report_service/generator.py**
Assembles output from all services into final report:
{
  transaction_id, classification, overall_confidence,
  doc_type, doc_type_confidence,
  extracted_fields: { all fields },
  confidence_scores: {
    ocr, extraction, vessel, barge, geolocation, overall
  },
  identity_resolution: { vessel + barge },
  fraud_alerts: [],
  anomaly_flags: [],
  credibility_flags: [],
  audit_trail: [],
  human_review_required: bool,
  verdict_reason: "plain English",
  evidence: { all evidence fields }
}

---

## PHASE 10 — API ROUTES  [main.py refactor]

Modular FastAPI routers, one per service:

```
POST /ocr/extract              ← OCR Service
POST /extraction/extract       ← Extraction Service
POST /verify/vessel            ← Vessel Verification Service
POST /verify/barge             ← Barge Verification Service
POST /verify/geolocation       ← Location Service
POST /validate                 ← Full pipeline (calls all above in order)
GET  /transactions             ← history list
GET  /transactions/{id}        ← full detail
GET  /vessels/{imo}            ← vessel detail
GET  /health                   ← system health
```

Each service independently testable via its own endpoint.
This matters for demo: if Datalastic is down, OCR and extraction
endpoints still work and can be demoed independently.

---

## PHASE 11 — DASHBOARD  [static/]

Single page application. Sections:

1. UPLOAD PANEL
   - Drag and drop or file picker
   - Mode selector: Auto Detect / Printed / Handwritten
     (Auto Detect routes to classifier; Printed = DIGITAL; Handwritten = HANDWRITTEN)
   - Upload button → POST /validate

2. DOCUMENT PANEL (side by side)
   - Left: uploaded BDN image preview
   - Right: extracted fields table with confidence indicator per field
   - Doc type badge (DIGITAL / HANDWRITTEN) + classification confidence
   - Highlight fields with low extraction confidence in amber

3. CONFIDENCE SCORES PANEL
   6 circular gauges or progress bars:
   OCR | Extraction | Vessel | Barge | Geolocation | Overall
   Color: green ≥75, amber ≥50, red <50

4. IDENTITY RESOLUTION CARD
   Vessel: BDN value → confirmed value, method, confidence
   Barge: BDN name + SB → confirmed name, method, confidence
   Both show resolution chain taken

5. GEOLOCATION MAP (folium embed)
   - Vessel AIS track (blue line)
   - Barge AIS track (orange line, if available)
   - Port marker (green pin)
   - Delivery window highlighted
   - Vessel centroid position shown
   - Barge centroid position shown
   - Distance annotation

6. FRAUD ALERTS PANEL
   Each alert: severity badge (HIGH/MEDIUM/LOW) + type + plain-English explanation
   Empty state: green "No fraud indicators detected"

7. VERDICT CARD
   VALID (green) / SUSPICIOUS (amber) / HIGH_RISK (red)
   Confidence percentage + verdict reason paragraph
   Human review badge if required

8. AUDIT TRAIL (collapsible)
   Each step: passed/failed badge, threshold, actual value, method used

9. TRANSACTIONS TABLE
   All past BDNs: date, vessel, port, verdict, confidence
   Sortable, filterable by verdict
   Click row → full detail

10. HUMAN REVIEW QUEUE
    Only HIGH_RISK + unresolved identity transactions
    Shows both candidate vessels when identity conflict

11. CONFIG PANEL (collapsible, operator use)
    Displays all current thresholds from config.yaml
    Allow edit + save (writes back to config.yaml)

---

## PHASE 12 — TESTING

**tests/test_ocr.py**
- Digital PDF extraction
- Handwritten image extraction
- Missing file handling

**tests/test_extraction.py**
- All timestamp formats (ISO, written date, time-only)
- Anchor date inheritance
- All synonym variants

**tests/test_identity.py**
- Correct IMO + matching name → CONFIRMED
- Correct IMO + fuzzy name → FUZZY_MATCH
- Correct IMO + embedding name → SOFT_MATCH
- Wrong IMO → reverse lookup
- Both wrong → UNRESOLVED
- SB + name agree → barge CONFIRMED
- SB + name conflict → barge CONFLICT

**tests/test_fraud.py**
- Duplicate BDN detection
- Reversed timestamps
- Quantity infeasible

**tests/test_pipeline.py**
- Full end-to-end with mock Datalastic responses
- VALID path
- HIGH_RISK path (identity unresolved)
- SUSPICIOUS path (barge AIS missing)

---

## FOLDER STRUCTURE AFTER ALL PHASES

```
BDN-Validation/
├── main.py                          ← FastAPI app + all routers
├── requirements.txt
├── alembic.ini
├── config/
│   ├── config.yaml                  ← complete v3 + new sections
│   └── settings.py                  ← NEW: unified config loader
├── core/                            ← existing, keep as-is
├── data/
│   └── mpa_barge_registry.json      ← NEW
├── db/                              ← existing ✅
├── migrations/                      ← existing ✅
├── models/
│   ├── database.py                  ← existing ✅
│   └── schemas.py                   ← update with new output fields
├── models_ml/
│   └── isolation_forest.pkl         ← generated by train script
├── persistence/                     ← existing, wire in phase 8
├── scripts/
│   ├── create_database.py           ← existing ✅
│   └── train_model.py               ← NEW
├── services/
│   ├── ocr_service/                 ← NEW (from document_service split)
│   │   ├── preprocessor.py
│   │   ├── engine.py
│   │   └── classifier.py
│   ├── extraction_service/          ← NEW (from extractor.py refactor)
│   │   ├── base_extractor.py
│   │   ├── digital_extractor.py
│   │   ├── handwritten_extractor.py
│   │   ├── normalizer.py
│   │   └── extractor.py
│   ├── credibility_service/         ← NEW (from credibility.py expand)
│   │   ├── scorer.py
│   │   └── duplicate_checker.py
│   ├── vessel_verification_service/ ← NEW (from identity_service expand)
│   │   ├── resolver.py
│   │   └── datalastic_client.py
│   ├── barge_verification_service/  ← NEW (from barge_resolver expand)
│   │   ├── resolver.py
│   │   └── mpa_registry.py
│   ├── location_service/            ← NEW (from validation_service refactor)
│   │   ├── ais_fetcher.py
│   │   ├── timezone_converter.py
│   │   ├── feature_builder.py
│   │   └── ml_scorer.py
│   ├── fraud_service/               ← NEW
│   │   └── detector.py
│   ├── scoring_service/             ← NEW
│   │   └── scorer.py
│   └── report_service/              ← NEW
│       └── generator.py
├── static/                          ← dashboard (single HTML file)
├── stub/
│   └── mock_pipeline.py             ← build first
└── tests/
    ├── test_ocr.py
    ├── test_extraction.py
    ├── test_identity.py
    ├── test_fraud.py
    └── test_pipeline.py
```

---

## BUILD ORDER (strict — always have something runnable)

Day 0 (today):
  Phase 0: config/settings.py + config.yaml + stub/mock_pipeline.py
  → POST /validate returns mock JSON, dashboard renders verdict

Day 1:
  Phase 1: ocr_service/ (preprocessor + engine + classifier)
  Phase 2: extraction_service/ (base + digital + handwritten + normalizer)
  → POST /ocr/extract and POST /extraction/extract working with real BDN

Day 2:
  Phase 3: credibility_service/ (scorer + duplicate checker)
  Phase 4: vessel_verification_service/ (resolver + datalastic_client)
  → POST /verify/vessel working with real Datalastic calls

Day 3:
  Phase 5: barge_verification_service/
  Phase 6: location_service/ (ais_fetcher + feature_builder + ml_scorer)
  → POST /verify/barge and POST /verify/geolocation working

Day 4:
  Phase 7: fraud_service/
  Phase 8: scoring_service/ with audit trail
  Phase 9: report_service/
  Phase 10: wire all routers in main.py
  → POST /validate full pipeline end-to-end

Day 5 (Friday):
  Phase 11: dashboard polish
  Phase 12: edge case testing
  Rotate GitHub token, push, pre-download models, README

---

## CONFLICTS EXCLUDED — REMINDER

These items from the mentor prompt are NOT implemented:
1. Haversine as verdict rule → replaced by Isolation Forest (FLAG_005)
2. Three upload modes as separate pipeline services → DIGITAL/HANDWRITTEN only (FLAG_007)
3. APPROVED/REJECTED/REVIEW REQUIRED terminology → VALID/SUSPICIOUS/HIGH_RISK
4. "Coordinates" as OCR-extracted field → port name extracted, coords from lookup table
5. "Available barge registries" vague reference → MPA JSON + Datalastic specifically

If mentor asks about any of these during demo, the answers are:
- "Geolocation uses ML anomaly detection, not a distance threshold, per your requirement"
- "Classification is DIGITAL vs HANDWRITTEN — the three-mode UI option is there as
   Auto Detect / Printed / Handwritten but they map to the same two pipelines"
- "Terminology follows maritime ops convention: VALID / SUSPICIOUS / HIGH_RISK"