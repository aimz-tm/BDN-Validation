# BDN Validation System

FastAPI service for BDN document extraction and validation against AIS telemetry.

## Database

The database layer uses PostgreSQL, SQLAlchemy, and Alembic.

1. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

2. Install PostgreSQL and make sure the server is running.

3. Copy `.env.example` to `.env` or `config/.env`, then update the credentials:

   ```env
   DATABASE_URL=postgresql+psycopg://geoloc_user:geoloc_password@localhost:5432/geoloc
   POSTGRES_ADMIN_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres
   ```

4. Create the database:

   ```powershell
   python scripts/create_database.py
   ```

5. Apply migrations:

   ```powershell
   alembic upgrade head
   ```

### Tables

- `vessels`: vessel identity and registry data, keyed by UUID with IMO and optional MMSI uniqueness.
- `ais_positions`: timestamped AIS telemetry linked to vessels when known, with MMSI/time uniqueness and range checks for coordinates, course, heading, and speed.
- `transactions`: BDN validation records linked to the receiving vessel and optional barge, with extracted document values, validation payloads, and verdict fields.

## Train the Isolation Forest (no AIS dataset required)

The ML model learns **synthetic** normal bunkering behaviour (vessel + barge co-located, low speed, near port). You do **not** need historical AIS CSV files or fraud labels.

| What you have | What it's used for |
|---------------|-------------------|
| Sample BDN images | OCR testing; optional `scripts/calibrate_from_bdns.py` for quantity/duration hints |
| Datalastic API key | Live AIS tracks (optional; demo mode uses synthetic tracks at declared port) |
| No AIS history | OK — run `scripts/train_model.py` |

```powershell
# 1. Optional: put sample BDNs in fixtures/sample_bdns/
python scripts/calibrate_from_bdns.py

# 2. Train model (writes models_ml/isolation_forest.pkl)
python scripts/train_model.py

# 3. Run API
python -m uvicorn main:app --reload
```

Set `DATALASTIC_API_KEY` in `config/.env` for real AIS. With `pipeline.synthetic_ais_fallback: true` (default), the pipeline still runs ML using demo tracks at the declared port when the API is unavailable.

To force mock AIS only: set `pipeline.mock_ais: true` in `config/config.yaml`.
