# BDN Validation System (129Knots)

## Project Abstract
The **BDN Validation System** by 129Knots is an intelligent, automated pipeline designed to detect maritime fraud and verify compliance in Bunker Delivery Notes (BDNs). Using a combination of Optical Character Recognition (OCR), external AIS (Automatic Identification System) telemetry data, and a machine learning anomaly detection engine, the system ingests raw BDN documents (both handwritten and digital formats), extracts critical transaction data, and cross-references it against physical maritime tracking data to detect spoofing, illegal bunkering operations, and regulatory violations.

## Key Features

### 1. Intelligent Document Ingestion & Extraction (OCR)
- **Multi-format Support:** Processes both standard digital PDF templates and messy, handwritten physical scans.
- **Dynamic Routing:** Automatically classifies documents as `DIGITAL` or `HANDWRITTEN` and routes them to specialized extraction engines.
- **Fuzzy Matching & Regex:** Employs advanced regex patterns paired with fuzzy sequence matching to extract key entities like Vessel Names, IMO numbers, Delivery Dates, Timestamps, Quantities, and specific chemical properties (Viscosity, Water Content, Density).
- **Interactive Visual Verification:** Normalizes bounding box coordinates from the OCR engine to dynamically highlight extracted text directly on the scanned document in the UI.

### 2. Identity Resolution & AIS Geolocation Verification
- **Vessel & Barge Identity Verification:** Cross-references extracted names and IMO numbers against external vessel registries (e.g., Datalastic) to confirm identity and retrieve the MMSI (Maritime Mobile Service Identity).
- **Physical Proximity Checks (AIS Tracking):** Verifies that both the receiving vessel and the bunker barge were physically co-located at the declared delivery port during the exact pumping start and end times.
- **AIS Tampering Detection:** Flags transactions where the barge's AIS transponder was turned off (dark activity) or intermittent during the delivery window.

### 3. MARPOL Annex VI Compliance Engine
- Automatically checks extracted fuel chemistry data against global environmental limits.
- **Density:** Flags fuel density outside the standard 0.820–1.010 kg/m³ range.
- **Sulphur Content:** Flags transactions exceeding the 0.50% global sulphur cap.
- **Flashpoint:** Flags hazardous fuel with a flashpoint below the 60°C safety minimum.

### 4. Credibility & Fraud Scoring
- Generates a composite **Overall Confidence Score** based on three pillars:
  1. **Document Integrity (40%):** Evaluates OCR confidence, layout anomalies, and metadata spoofing.
  2. **Data Anomalies (35%):** Penalizes transactions for missing AIS telemetry, conflicting geolocation data, or mismatched vessel identities.
  3. **Compliance Gaps (25%):** Penalizes regulatory violations (e.g., MARPOL chemistry violations).
- Automatically categorizes transactions into risk tiers (`VALID`, `REVIEW_REQUIRED`, `SUSPICIOUS`, `HIGH_RISK`).

### 5. Interactive Investigation Dashboard
- **Real-time Processing Pipeline:** A visual stepper showing the document moving through Classification, Extraction, Rule Engine Checks, and AIS Verification.
- **Audit Trail & Changelog:** Allows operators to manually edit or correct extracted fields via inline inputs, automatically maintaining a detailed, timestamped revision history.
- **Flexible Grid Layout:** Dynamic dual-column interface organizing Verdicts, Confidence Tracks, Identity Resolution, Evidence Breakdowns, and Fraud Alerts seamlessly.
