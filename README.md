# 129Knots BDN Validation System

Fraud detection pipeline for maritime Bunker Delivery Notes (BDNs). Upload a scanned or
digital BDN and it runs OCR, extracts the fields, checks the vessel and barge against
external registries, verifies AIS co-location during the delivery window, checks MARPOL
fuel limits, and returns a confidence score and verdict.

## How it works

Each upload goes through nine stages: OCR, field extraction, credibility checks, vessel
verification (Datalastic registry), barge verification (MPA registry), AIS geolocation,
fraud detection, scoring, and report generation. The orchestrator that ties these together
is `app/services/validation_service/orchestrator.py`; each stage is its own package under
`app/services/`.

Tesseract, Datalastic and Postgres are all optional at runtime — see **Offline mode**
below if you don't have them set up.

## Requirements

- Python 3.11+
- PostgreSQL 14+ (optional — set `pipeline.use_mock: true` to skip it)
- Tesseract OCR 5.x
- spaCy model `en_core_web_sm`

## Setup

```bash
git clone <repo-url>
cd BDN-Validation

python -m venv .venv
.venv\Scripts\activate       # Windows
source .venv/bin/activate    # Linux/macOS

pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

Install Tesseract separately:

- Windows: [UB-Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki), then set
  `TESSERACT_PATH` in `config/.env`
- Linux: `sudo apt install tesseract-ocr`
- macOS: `brew install tesseract`

Copy `config/.env.example` to `config/.env` and fill in `DATABASE_URL` (and
`DATALASTIC_API_KEY` if you have one — the app runs fine without it, see below).

## Database

```bash
python scripts/create_database.py
alembic upgrade head
```

## Running

```bash
python -m uvicorn app.main:app --reload
```

- Dashboard: http://localhost:8000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Training the ML model

The AIS anomaly scorer is a scikit-learn Isolation Forest trained on synthetic bunkering
behaviour — no historical AIS data required.

```bash
python scripts/train_model.py
```

This writes `models_ml/isolation_forest.pkl`. If it's missing, the pipeline falls back to
rule-based scoring only. `scripts/calibrate_from_bdns.py` can tune quantity/duration
thresholds from a folder of real sample BDNs, if you have any.

## Offline / demo mode

Toggle these in `config/config.yaml`:

- `pipeline.use_mock: true` — skip OCR and every external call, serve seeded demo
  transactions. Good for frontend work.
- `pipeline.mock_ais: false` + `synthetic_ais_fallback: true` — real OCR and extraction,
  synthetic AIS tracks instead of a live Datalastic call. This is the default and needs no
  API key.

## API

- `POST /validate` — upload a BDN, run the full pipeline
- `GET /transactions`, `GET /transactions/{id}`, `PUT /transactions/{id}` — review queue
- `GET /vessels/{imo}` — vessel lookup
- `GET /config`, `PUT /config` — read/update `config.yaml` at runtime
- `POST /ocr/extract`, `POST /extraction/extract`, `POST /verify/vessel`,
  `POST /verify/barge`, `POST /verify/geolocation` — individual pipeline stages, useful for
  testing one phase in isolation

## Project structure

```
app/
  main.py            FastAPI app and routes
  core/               config loader
  db/, models/        SQLAlchemy engine/session and ORM models
  persistence/        DB-backed and in-memory transaction stores
  services/           one package per pipeline stage
  stub/               mock pipeline and AIS data for offline mode
config/                config.yaml, .env
migrations/            Alembic migrations
scripts/               DB setup, model training, cache seeding
static/                dashboard frontend
data/                  MPA barge registry, cached AIS responses
models_ml/             trained model artifact
```

## Configuration

Every threshold, scoring weight, and MARPOL limit lives in `config/config.yaml`. The
dashboard's Config tab edits it live — no restart needed.
