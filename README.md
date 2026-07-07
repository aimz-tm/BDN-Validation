# 129Knots BDN Validation System

An automated fraud detection and compliance pipeline for maritime Bunker Delivery Notes (BDNs). The system ingests scanned or digital BDN documents, extracts all key fields via OCR, cross-references vessel and barge identities against external registries, verifies physical co-location using AIS telemetry, checks MARPOL Annex VI fuel compliance, and produces a structured verdict with a confidence score.

---

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Database Setup](#database-setup)
- [Running the App](#running-the-app)
- [Training the ML Model](#training-the-ml-model)
- [API Reference](#api-reference)
- [Dashboard](#dashboard)
- [Offline / Demo Mode](#offline--demo-mode)
- [Project Structure](#project-structure)
- [Verdict & Scoring Reference](#verdict--scoring-reference)

---

## How It Works

Every uploaded BDN passes through a 9-phase pipeline:

| Phase | Service | What it does |
|-------|---------|--------------|
| 1 | OCR Engine | Classifies as `DIGITAL` or `HANDWRITTEN`, applies doc-specific preprocessing (CLAHE, deskew, adaptive threshold), runs multi-PSM Tesseract ensemble |
| 2 | Field Extractor | Pulls vessel name, IMO, barge, dates, times, port, supplier, quantity, fuel specs (density, sulphur, flashpoint, viscosity), and seal numbers via regex + fuzzy matching |
| 3 | Credibility Scorer | Checks field completeness, timestamp logic, MARPOL limits, font consistency, and correction keywords |
| 4 | Vessel Resolver | Cross-references IMO and vessel name against the Datalastic registry |
| 5 | Barge Verifier | Matches barge name and SB number against the MPA registry with fuzzy matching |
| 6 | AIS Geolocation | Verifies vessel and barge were co-located at the declared port during the delivery window |
| 7 | Fraud Detector | Checks for duplicate BDNs (90-day window), identity conflicts, quantity infeasibility, AIS dark periods |
| 8 | Confidence Scorer | Blends document credibility (35%), vessel identity confidence (25%), and AIS anomaly score (40%) into a 0–100% score |
| 9 | Report Generator | Produces a structured verdict, audit trail, fraud alert list, and validation summary |

---

## Prerequisites

| Requirement | Version | Notes |
|------------|---------|-------|
| Python | 3.11+ | |
| PostgreSQL | 14+ | Or set `pipeline.use_mock: true` to skip DB entirely |
| Tesseract OCR | 5.x | Must be on `PATH` or set `TESSERACT_PATH` in `.env` |
| spaCy English model | `en_core_web_sm` | Fallback NER extractor |

### Install Tesseract

**Windows** — download the installer from [UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki), then either add its folder to `PATH` or set `TESSERACT_PATH` in `config/.env`:

```env
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe
```

**Linux / macOS**:

```bash
# Ubuntu / Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract
```

### Install spaCy model

```bash
python -m spacy download en_core_web_sm
```

---

## Installation

```bash
git clone <repo-url>
cd BDN-Validation

# Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Configuration

All tuneable parameters live in [`config/config.yaml`](config/config.yaml). The dashboard **Config** tab exposes a UI for live edits — no restart required.

Key sections:

### Scoring weights

```yaml
scoring:
  weights:
    document_credibility: 0.35   # OCR quality, completeness, MARPOL checks
    identity_confidence:  0.25   # Vessel registry match depth
    ais_anomaly_score:    0.40   # Geolocation co-location, speed, AIS gaps
```

### Verdict thresholds

```yaml
scoring:
  thresholds:
    valid_min_confidence:      0.75   # ≥75% → VALID
    suspicious_min_confidence: 0.45   # 45–74% → SUSPICIOUS, <45% → HIGH RISK
```

### MARPOL compliance limits

```yaml
credibility:
  marpol:
    density_min:        0.82     # kg/m³
    density_max:        1.01
    sulphur_max:        0.5      # % m/m global cap
    flashpoint_min:     60       # °C
    viscosity_max_50c:  700      # cSt
    water_content_max:  0.5      # % V/V
```

### Fraud detection

```yaml
fraud_detection:
  duplicate_bdn_window_days: 90   # Look-back window for duplicate BDN detection
  alert_severities:
    DUPLICATE_BDN:        HIGH
    IMO_MISMATCH:         HIGH
    EXCESSIVE_DISTANCE:   HIGH
    BARGE_UNVERIFIED:     MEDIUM
    MISSING_SEAL_NUMBERS: LOW
```

### AIS validation

```yaml
validation:
  max_distance_m:              200    # Max separation between vessel and barge
  min_overlap_percent:          70    # % of delivery window where both AIS tracks overlap
  max_speed_during_delivery:     3    # Knots — higher implies vessel was underway
  max_ais_gap_minutes:          60    # Acceptable AIS blackout gap
  port_coordinate_tolerance_km: 50   # Radius around declared port
```

### Environment variables (`config/.env`)

Copy `.env.example` to `config/.env` and fill in:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/bdn_db
POSTGRES_ADMIN_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres
DATALASTIC_API_KEY=your_key_here        # Optional — demo mode works without it
TESSERACT_PATH=C:\Program Files\Tesseract-OCR\tesseract.exe   # Windows only
```

---

## Database Setup

```bash
# 1. Create the database and user
python scripts/create_database.py

# 2. Apply schema migrations
alembic upgrade head
```

### Schema overview

| Table | Purpose |
|-------|---------|
| `vessels` | Vessel identity records (IMO, MMSI, name) |
| `ais_positions` | Timestamped AIS telemetry linked to vessels |
| `transactions` | BDN validation records — extracted fields, scores, verdict, audit trail |

---

## Running the App

```bash
# Development (auto-reload on file changes)
python -m uvicorn main:app --reload

# Production
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Open [http://localhost:8000](http://localhost:8000) for the dashboard.

The API docs (Swagger UI) are at [http://localhost:8000/docs](http://localhost:8000/docs).

---

## Training the ML Model

The anomaly detection layer uses a scikit-learn Isolation Forest. You do **not** need historical AIS data — the model trains on synthetic normal/anomalous bunkering behaviour.

```bash
# Optional: calibrate quantity/duration hints from your own sample BDNs
# Place PDF/image BDNs in fixtures/sample_bdns/ first
python scripts/calibrate_from_bdns.py

# Train the model (writes models_ml/isolation_forest.pkl)
python scripts/train_model.py

# Start the app
python -m uvicorn main:app --reload
```

If the model file is absent when the app starts, the pipeline falls back to rule-based scoring only (`pipeline.use_ml_when_model_missing: true` controls this).

---

## API Reference

### `POST /validate`

Upload a BDN document and run the full validation pipeline.

```
Content-Type: multipart/form-data
Field: file  (PDF, PNG, JPG)
```

**Response:**

```json
{
  "transaction_id": "uuid",
  "verdict": "SUSPICIOUS",
  "confidence_score": 0.61,
  "fraud_alerts": [
    { "type": "BARGE_UNVERIFIED", "severity": "MEDIUM", "message": "..." }
  ],
  "extracted_fields": {
    "vessel_name": "STAR ELIZABETH",
    "imo": "9876543",
    "quantity_mt": 850.5,
    "fuel_type": "VLSFO",
    "delivery_date": "2025-11-17"
  },
  "validation_result": { ... }
}
```

### `POST /extract`

Extract fields only — no AIS or registry checks. Useful for testing OCR quality.

```
Content-Type: multipart/form-data
Field: file  (PDF, PNG, JPG)
```

### `GET /transactions`

List all past validation transactions.

```
Query params:
  limit   int   (default 50)
  offset  int   (default 0)
```

### `PUT /transactions/{transaction_id}`

Update a transaction — used by the dashboard to save manual field corrections and reviewer decisions (approve / reject).

### `GET /config`

Return current `config.yaml` as JSON.

### `POST /config`

Update configuration values at runtime. Changes persist to `config/config.yaml`.

```json
{ "scoring.thresholds.valid_min_confidence": 0.80 }
```

---

## Dashboard

The single-page dashboard at `/` provides:

- **Scan** — upload a BDN and watch the 9-phase pipeline progress in real time
- **History** — table of all past validations with verdict badges and confidence scores
- **Review queue** — SUSPICIOUS and HIGH RISK documents awaiting a human decision; one-click approve or reject
- **Config** — live editor for all `config.yaml` parameters

### Verdict badges

| Badge | Meaning |
|-------|---------|
| `VALID` | Confidence ≥75%. All checks passed. |
| `SUSPICIOUS` | Confidence 45–74%. Minor flags — review recommended. |
| `HIGH RISK` | Confidence <45%. Serious anomalies detected. |
| `REJECTED` | Manually rejected by a reviewer. |

---

## Offline / Demo Mode

The system runs fully offline with no external API calls. Two levels of mock:

### Stub AIS (default)

Set in `config/config.yaml`:

```yaml
pipeline:
  mock_ais: false                  # false = try live Datalastic, fall back to synthetic
  synthetic_ais_fallback: true     # true = generate synthetic tracks at declared port if API unavailable
```

With `DATALASTIC_API_KEY` unset and `synthetic_ais_fallback: true`, the pipeline runs end-to-end using generated AIS tracks at the declared port. Confidence scores are realistic; only geolocation verification is synthetic.

### Full mock pipeline

```yaml
pipeline:
  use_mock: true    # Skip OCR and all external calls entirely; use seeded demo transactions
```

Use this for UI development and demoing without any documents.

### Seeding the AIS cache

```bash
# Pre-populate the local AIS cache with track data for a known vessel
python scripts/seed_cache.py
```

---

## Project Structure

```
BDN-Validation/
├── main.py                          # FastAPI app, all route handlers
├── config/
│   ├── config.yaml                  # All tuneable parameters
│   └── .env                         # Secrets (not committed)
├── core/
│   └── config_loader.py             # YAML loader, live reload
├── persistence/
│   ├── models.py                    # SQLAlchemy ORM models
│   ├── repository.py                # DB read/write helpers
│   └── memory_store.py              # In-memory fallback store
├── migrations/                      # Alembic migration scripts
├── services/
│   ├── ocr_service/
│   │   ├── engine.py                # Tesseract multi-PSM ensemble
│   │   ├── preprocessor.py          # CLAHE, deskew, adaptive threshold
│   │   └── classifier.py            # DIGITAL vs HANDWRITTEN classification
│   ├── extraction_service/
│   │   ├── base_extractor.py        # Fuzzy match, regex, garbage filter
│   │   ├── extractor.py             # Field-level extraction + validators
│   │   ├── digital_extractor.py     # Tuned for printed BDNs
│   │   └── handwritten_extractor.py # Tuned for handwritten BDNs
│   ├── credibility_service/         # MARPOL checks, timestamp logic, scoring
│   ├── vessel_verification_service/ # Datalastic registry lookup
│   ├── barge_verification_service/  # MPA registry fuzzy match
│   ├── location_service/            # AIS fetch, co-location checks
│   ├── fraud_service/               # Duplicate detection, alert generation
│   ├── scoring_service/             # Final confidence score blending
│   ├── report_service/              # Verdict report assembly
│   ├── validation_service/          # Orchestrator, ML model, geospatial
│   └── data_provider/               # Live / cached / stub AIS provider
├── stub/
│   ├── mock_pipeline.py             # Seeded demo transactions
│   └── mock_ais.py                  # Synthetic AIS track generator
├── scripts/
│   ├── create_database.py           # Create DB and user
│   ├── train_model.py               # Train Isolation Forest
│   ├── calibrate_from_bdns.py       # Calibrate model from sample BDNs
│   └── seed_cache.py                # Pre-populate AIS cache
├── static/
│   ├── index.html                   # Single-page dashboard
│   ├── js/dashboard.js              # All frontend logic
│   └── css/dashboard.css            # Styles
├── models_ml/                       # Trained model artifacts (git-ignored)
├── data/
│   ├── mpa_barge_registry.json      # MPA barge registry
│   └── ais_cache/                   # Cached AIS track files
└── requirements.txt
```

---

## Verdict & Scoring Reference

### Confidence score composition

| Component | Weight | Measures |
|-----------|--------|---------|
| Document credibility | 35% | OCR confidence, field completeness, timestamp integrity, MARPOL spec checks, font consistency |
| Vessel identity confidence | 25% | Registry match depth, IMO resolution, MMSI retrieval |
| AIS anomaly score | 40% | Vessel–barge co-location, speed during delivery, AIS gap duration, port proximity |

### Fraud alert types

| Alert | Severity | Trigger |
|-------|----------|---------|
| `DUPLICATE_BDN` | HIGH | Same BDN reference seen within 90 days |
| `IMO_MISMATCH` | HIGH | Extracted IMO doesn't match registry name |
| `VESSEL_NOT_FOUND` | HIGH | IMO not found in Datalastic registry |
| `EXCESSIVE_DISTANCE` | HIGH | Vessel/barge separation >200 m during delivery |
| `BARGE_IDENTITY_CONFLICT` | HIGH | Barge name conflicts with SB number record |
| `BARGE_UNVERIFIED` | MEDIUM | Barge not found in MPA registry |
| `QUANTITY_INFEASIBLE` | MEDIUM | Quantity vs pump rate vs duration inconsistent |
| `INVALID_TIMESTAMPS` | MEDIUM | End time before start time, or >12 h duration |
| `SUSPICIOUS_CORRECTIONS` | MEDIUM | "whiteout", "amended", "corrected" in document text |
| `MISSING_SEAL_NUMBERS` | LOW | One or more seal fields absent |
| `BARGE_AIS_MISSING` | LOW | No AIS track found for barge during delivery window |
